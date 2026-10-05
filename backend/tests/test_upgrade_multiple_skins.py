"""Multi-skin stakes use real owned prices and debit the entire selection once."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from mongomock.collection import Collection


run = asyncio.run


@pytest.fixture
def multi_stake(api, monkeypatch):
    original = Collection.find_one_and_update

    def keep_id_for_mock_after_lookup(self, *args, **kwargs):
        # Real MongoDB returns the updated row even after the skin filter changes.
        if kwargs.get("projection"):
            kwargs["projection"] = {**kwargs["projection"], "_id": 1}
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Collection, "find_one_and_update", keep_id_for_mock_after_lookup)
    api.s.read_token = lambda _: "player"
    monkeypatch.setattr(api.s, "upgrade_rate_ok", lambda _: True)
    api.s._rng = SimpleNamespace(random=lambda: .5, uniform=lambda lo, hi: lo)
    skins = [{"id": "source", "uid": f"copy-{i}", "name": "Source", "price": 100} for i in range(7)]

    async def setup():
        await api.db.users.update_one({"session_id": "player"}, {"$set": {"balance": 1000, "skins": skins}})
        await api.db.shop_items.insert_one({"id": "target", "name": "Target", "price": 1000})
        await api.db.bank_settings.insert_one({"id": "main", "rtp_target": .87})
        await api.db.bank_state.update_one({"id": "main"}, {"$set": {"bank": 100000, "pool": 10000}})
        await api.db.bank_lock.insert_one({"id": "main", "locked_until": api.s.now_utc() - timedelta(seconds=1)})

    run(setup())
    return api


def stake(count=6):
    return {"session_id": "player", "bet_amount": 50,
            "bet_items": [{"uid": f"copy-{i}", "price": .01} for i in range(count)],
            "target_item": {"id": "target", "price": 999999}}


def test_six_owned_skins_and_cash_win_one_target_and_cannot_be_spent_again(multi_stake):
    async def check():
        a = multi_stake
        response = await a.request("/upgrade", "POST", json=stake())
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["win"] is True
        assert result["display_chance"] == .65
        assert result["chance"] == pytest.approx(.65 * .87)
        user = await a.db.users.find_one({"session_id": "player"})
        assert user["balance"] == 950
        assert len(user["skins"]) == 2
        assert any(s["uid"] == "copy-6" for s in user["skins"])
        assert sum(s.get("id") == "target" for s in user["skins"]) == 1
        upgrade = await a.db.upgrades.find_one({})
        assert len(upgrade["bet_items"]) == 6
        assert upgrade["items_total"] == 600
        assert upgrade["target_item"]["price"] == 1000
        pool = (await a.db.bank_state.find_one({"id": "main"}))["pool"]
        replay = await a.request("/upgrade", "POST", json=stake())
        assert replay.status_code == 400
        assert await a.db.upgrades.count_documents({}) == 1
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 950
        assert (await a.db.bank_state.find_one({"id": "main"}))["pool"] == pool
    run(check())


def test_seventh_skin_is_rejected_before_any_balance_inventory_or_pool_changes(multi_stake):
    async def check():
        a = multi_stake
        response = await a.request("/upgrade", "POST", json=stake(7))
        assert response.status_code == 422
        assert any(error["loc"] == ["body", "bet_items"] for error in response.json()["detail"])
        user = await a.db.users.find_one({"session_id": "player"})
        assert user["balance"] == 1000 and len(user["skins"]) == 7
        assert await a.db.upgrades.count_documents({}) == 0
        assert (await a.db.bank_state.find_one({"id": "main"}))["pool"] == 10000
    run(check())


@pytest.mark.parametrize("invalid_uid", ["copy-0", "someone-elses-skin"])
def test_duplicate_or_unowned_skin_rejects_entire_stake(multi_stake, invalid_uid):
    async def check():
        a = multi_stake
        payload = stake()
        payload["bet_items"][-1]["uid"] = invalid_uid
        response = await a.request("/upgrade", "POST", json=payload)
        assert response.status_code == 400
        user = await a.db.users.find_one({"session_id": "player"})
        assert user["balance"] == 1000 and len(user["skins"]) == 7
        assert await a.db.upgrades.count_documents({}) == 0
        assert (await a.db.bank_state.find_one({"id": "main"}))["pool"] == 10000
    run(check())
