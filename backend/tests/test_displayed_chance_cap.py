import asyncio
from types import SimpleNamespace
from mongomock.collection import Collection

import pytest


run = asyncio.run


@pytest.mark.parametrize("rtp", [.75, .85, .87, 1.0])
def test_game_config_caps_total_stake_at_displayed_75_percent(api, rtp):
    async def check():
        await api.db.bank_settings.insert_one({"id": "main", "rtp_target": rtp})
        result = (await api.request("/game-config")).json()
        assert result["max_bet_ratio"] == result["max_chance"] == .75
        assert api.s.win_chance(1500, 2000, rtp) == pytest.approx(.75 * rtp)
    run(check())


@pytest.mark.parametrize("cash", [205.01, 217.61, 429.13])
def test_excess_stake_rejected_before_any_debit(api, cash):
    async def check():
        a = api
        a.s.read_token = lambda _: "player"
        await a.db.users.update_one({"session_id": "player"}, {"$set": {"balance": 1000, "skins": [{"uid": "sakura", "price": 1295}]}})
        await a.db.shop_items.insert_one({"id": "rusted", "price": 2000})
        await a.db.bank_settings.insert_one({"id": "main", "rtp_target": .87})
        r = await a.request("/upgrade", "POST", json={"session_id": "player", "bet_amount": cash, "bet_items": [{"uid": "sakura"}], "target_item": {"id": "rusted"}})
        assert r.status_code == 400 and "75%" in r.json()["detail"]
        user = await a.db.users.find_one({"session_id": "player"})
        assert user["balance"] == 1000 and len(user["skins"]) == 1
        assert await a.db.upgrades.count_documents({}) == 0
        assert (await a.db.bank_state.find_one({"id": "main"}))["pool"] == 5
    run(check())


def test_exact_cap_is_accepted_and_rtp_stays_unchanged(api, monkeypatch):
    original = Collection.find_one_and_update
    def keep_id_for_mock_after_lookup(self, *args, **kwargs):
        # mongomock re-queries the pre-update filter if the projection removes _id.
        # A skin debit changes that filter; real MongoDB returns the updated row.
        projection = kwargs.get("projection")
        if projection:
            kwargs["projection"] = {**projection, "_id": 1}
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Collection, "find_one_and_update", keep_id_for_mock_after_lookup)
    async def check():
        a = api
        a.s.read_token = lambda _: "player"
        a.s._rng = SimpleNamespace(random=lambda: .999, uniform=lambda lo, hi: lo)
        await a.db.users.update_one({"session_id": "player"}, {"$set": {"balance": 1000, "skins": [{"uid": "sakura", "price": 1295}]}})
        await a.db.shop_items.insert_one({"id": "rusted", "price": 2000})
        await a.db.bank_settings.insert_one({"id": "main", "rtp_target": .87})
        r = await a.request("/upgrade", "POST", json={"session_id": "player", "bet_amount": 205, "bet_items": [{"uid": "sakura"}], "target_item": {"id": "rusted"}})
        assert r.status_code == 200, r.text
        assert r.json()["display_chance"] == .75
        assert r.json()["chance"] == pytest.approx(.6525)
        assert r.json()["upgrades_total"] == 1
    run(check())


def test_fractional_price_rounds_maximum_down_to_cents(api):
    async def check():
        a = api
        a.s.read_token = lambda _: "player"
        await a.db.users.update_one({"session_id": "player"}, {"$set": {"balance": 1000, "skins": []}})
        await a.db.shop_items.insert_one({"id": "fractional", "price": 99.99})
        r = await a.request("/upgrade", "POST", json={"session_id": "player", "bet_amount": 75, "target_item": {"id": "fractional"}})
        assert r.status_code == 400
        assert (await a.db.users.find_one({"session_id": "player"}))["balance"] == 1000
    run(check())
