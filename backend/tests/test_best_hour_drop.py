import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import httpx


class Cursor:
    def __init__(self, items):
        self.items = deepcopy(items)

    def sort(self, fields, direction=None):
        fields = [(fields, direction)] if direction is not None else fields
        for key, order in reversed(fields):
            self.items.sort(key=lambda item: item[key], reverse=order == -1)
        return self

    async def to_list(self, limit):
        return self.items[:limit]

    def __aiter__(self):
        async def iterate():
            for item in self.items:
                yield item
        return iterate()


def test_best_drop_uses_the_whole_hour_and_excludes_expired_or_future_wins(isolated_server):
    server = isolated_server
    now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    server.now_utc = lambda: now
    def drop(item_id, seconds_ago, price):
        return {"id": item_id, "session_id": "winner", "nickname": "Old name", "item_name": "Typhon", "item_type": "AWP", "item_price": price, "chance": 0.5, "created_at": now - timedelta(seconds=seconds_ago)}
    rows = [drop(f"recent-{i}", i, 110) for i in range(40)]
    rows += [drop("winner", 1800, 3000), drop("old", 3601, 99999), drop("future", -1, 999999)]
    def find(query, projection):
        times = query.get("created_at")
        return Cursor([row for row in rows if not times or times["$gte"] <= row["created_at"] <= times["$lte"]])
    server.db.drops = SimpleNamespace(find=find)
    server.db.users = SimpleNamespace(find=lambda *args: Cursor([{"session_id": "winner", "nickname": "Winner now", "discord_id": "123", "avatar": "avatar.png"}]))
    async def fetch(include_best=True):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            return (await client.get("/api/live-drops", params={"limit": 30, "include_best": include_best})).json()
    feed = asyncio.run(fetch())
    assert len(feed["drops"]) == 30
    assert feed["best_drop"]["id"] == "winner"
    assert feed["best_drop"]["nickname"] == "Winner now"
    assert feed["best_drop"]["discord_id"] == "123"
    assert "session_id" not in feed["best_drop"]
    assert "session_id" not in feed["drops"][0]
    assert all(row["id"] != "winner" for row in feed["drops"])
    assert feed["best_drop_expires_at"].startswith("2026-09-12T12:30:00")
    assert isinstance(asyncio.run(fetch(False)), list)
    rows[:] = [drop("old-only", 3601, 99999)]
    assert asyncio.run(fetch())["best_drop"] is None
