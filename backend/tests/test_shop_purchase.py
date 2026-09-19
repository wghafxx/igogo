import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest


@pytest.fixture
def shop_api(isolated_server):
    server = isolated_server
    account = {"session_id": "buyer", "nickname": "Buyer", "balance": 1000.0, "skins": []}
    catalog = deepcopy(server.SHOP_ITEMS)
    history = {}

    async def atomic_debit(query, pipeline, **kwargs):
        order_id = query["shop_receipts.id"]["$ne"]
        if account["balance"] < query["balance"]["$gte"] or any(r["id"] == order_id for r in account.get("shop_receipts", [])):
            return None
        update = pipeline[0]["$set"]
        account["balance"] = round(account["balance"] - update["balance"]["$round"][0]["$subtract"][1], 2)
        account["skins"].extend(deepcopy(update["skins"]["$concatArrays"][1]["$literal"]))
        account.setdefault("shop_receipts", []).extend(deepcopy(update["shop_receipts"]["$concatArrays"][1]["$literal"]))
        return deepcopy(account)

    async def history_write(query, update, **kwargs):
        history.setdefault(query["id"], deepcopy(update["$setOnInsert"]))

    server.db.users = SimpleNamespace(
        find_one=AsyncMock(side_effect=lambda query, projection: deepcopy(account) if query.get("session_id") == "buyer" else None),
        find_one_and_update=AsyncMock(side_effect=atomic_debit),
    )
    server.db.shop_items = SimpleNamespace(find=lambda query, projection: SimpleNamespace(to_list=AsyncMock(return_value=[item for item in catalog if item["id"] in query["id"]["$in"]])))
    server.db.item_history = SimpleNamespace(update_one=AsyncMock(side_effect=history_write))
    token = server.make_token("buyer", role="user")

    async def post(body, authenticated=True):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return await client.post("/api/shop/buy", json=body, headers={"Authorization": f"Bearer {token}"} if authenticated else {})

    def basket(quantity=1, total=110):
        return {"request_id": str(uuid.uuid4()), "items": [{"id": "awp-typhon", "quantity": quantity}], "expected_total": total}

    return SimpleNamespace(server=server, account=account, catalog=catalog, history=history, post=post, basket=basket, history_write=history_write)


def test_purchase_uses_catalog_and_issues_unique_skins(shop_api):
    api = shop_api
    body = api.basket(2, 372)
    body["items"].append({"id": "awp-railgun", "quantity": 1})
    response = asyncio.run(api.post(body))
    assert response.status_code == 200
    result = response.json()
    assert (result["total"], result["count"], result["user"]["balance"]) == (372, 3, 628)
    skins = result["user"]["skins"]
    assert len({skin["uid"] for skin in skins}) == 3
    assert sorted(skin["price"] for skin in skins) == [110, 110, 152]
    assert all(skin["rarity"] == "pink" and skin["image"].startswith("https://bloxstrike.net/") for skin in skins)
    assert "shop_receipts" not in result["user"]
    assert len(api.history) == 3


def test_insufficient_balance_leaves_inventory_unchanged(shop_api):
    shop_api.account["balance"] = 109.99
    assert asyncio.run(shop_api.post(shop_api.basket())).status_code == 400
    assert shop_api.account["balance"] == 109.99
    assert not shop_api.account["skins"] and not shop_api.history


def test_retry_is_not_charged_twice_and_cannot_change_basket(shop_api):
    body = shop_api.basket()
    assert asyncio.run(shop_api.post(body)).status_code == 200
    assert asyncio.run(shop_api.post(body)).status_code == 200
    assert shop_api.account["balance"] == 890
    assert len(shop_api.account["skins"]) == len(shop_api.history) == 1
    body["items"][0]["quantity"] = 2
    body["expected_total"] = 220
    assert asyncio.run(shop_api.post(body)).status_code == 409
    assert shop_api.account["balance"] == 890


def test_parallel_purchases_cannot_overspend(shop_api):
    async def buy_both():
        return await asyncio.gather(shop_api.post(shop_api.basket(6, 660)), shop_api.post(shop_api.basket(6, 660)))
    responses = asyncio.run(buy_both())
    assert sorted(r.status_code for r in responses) == [200, 400]
    assert shop_api.account["balance"] == 340
    assert len(shop_api.account["skins"]) == 6


def test_history_failure_is_repaired_on_retry_without_another_debit(shop_api):
    body = shop_api.basket()
    shop_api.server.db.item_history.update_one.side_effect = RuntimeError("interrupted history write")
    with pytest.raises(RuntimeError):
        asyncio.run(shop_api.post(body))
    shop_api.server.db.item_history.update_one.side_effect = shop_api.history_write
    assert asyncio.run(shop_api.post(body)).status_code == 200
    assert shop_api.account["balance"] == 890
    assert len(shop_api.account["skins"]) == len(shop_api.history) == 1


def test_fractional_purchases_preserve_cents(shop_api):
    next(item for item in shop_api.catalog if item["id"] == "awp-typhon")["price"] = 0.1
    shop_api.account["balance"] = 0.3
    assert asyncio.run(shop_api.post(shop_api.basket(2, 0.2))).status_code == 200
    assert asyncio.run(shop_api.post(shop_api.basket(1, 0.1))).status_code == 200
    assert shop_api.account["balance"] == 0


@pytest.mark.parametrize("quantity", [0, -1, 101, 1.5, True])
def test_invalid_quantities_are_rejected(shop_api, quantity):
    assert asyncio.run(shop_api.post(shop_api.basket(quantity))).status_code == 422
    assert shop_api.account["balance"] == 1000


def test_prices_and_items_cannot_be_forged(shop_api):
    body = shop_api.basket(total=1)
    body["items"][0]["price"] = 1
    assert asyncio.run(shop_api.post(body)).status_code == 409
    body = shop_api.basket()
    body["items"][0]["id"] = "invented-skin"
    assert asyncio.run(shop_api.post(body)).status_code == 400
    body = shop_api.basket(1, 220)
    body["items"].append(dict(body["items"][0]))
    assert asyncio.run(shop_api.post(body)).status_code == 400
    assert shop_api.account["balance"] == 1000


def test_purchase_requires_login(shop_api):
    assert asyncio.run(shop_api.post(shop_api.basket(), authenticated=False)).status_code == 401
    assert shop_api.account["balance"] == 1000
