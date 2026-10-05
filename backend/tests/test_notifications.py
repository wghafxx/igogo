"""Notification history, ownership and read-state checks without live services."""
import asyncio
from datetime import timedelta

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def notification_api(isolated_server):
    server = isolated_server
    server.db = AsyncMongoMockClient().test

    async def setup():
        await server.db.users.insert_many([
            {"session_id": "owner", "balance": 100, "skins": []},
            {"session_id": "other", "balance": 200, "skins": []},
        ])
    asyncio.run(setup())
    # Exercise the real authentication/ownership lookup, bypassing only JWT parsing.
    server.read_token = lambda request: request.headers.get("X-Test-User")
    return server


async def request(server, method="GET", *, user="owner", body=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
        return await client.request(method, "/api/notifications" + ("/read" if method == "POST" else ""),
                                    headers={"X-Test-User": user} if user else {}, json=body)


@pytest.mark.parametrize("kind,status,event", [
    ("deposits", "pending", "deposit_requested"),
    ("deposits", "confirmed", "deposit_confirmed"),
    ("deposits", "cancelled", "deposit_cancelled"),
    ("deposits", "rejected", "deposit_rejected"),
    ("deposits", "expired", "deposit_expired"),
    ("withdrawals", "pending", "withdrawal_requested"),
    ("withdrawals", "done", "withdrawal_done"),
    ("withdrawals", "cancelled", "withdrawal_cancelled"),
])
def test_operation_events_and_private_details(notification_api, kind, status, event):
    async def check():
        server = notification_api
        created = server.now_utc() - timedelta(hours=1)
        doc = {"id": "request-1", "session_id": "owner", "status": status, "created_at": created,
               "resolved_at": created + timedelta(minutes=5) if status != "pending" else None,
               "expected_rap": 100, "credited": 120, "item": {"name": "Skin", "price": 75},
               "rejection_reason": "illiquid_skin", "cancellation_reason": "Скин недоступен",
               "provider_invoice_id": "private-provider-value", "discord_id": "private-discord-id"}
        await server.db[kind].insert_one(doc)
        first = (await request(server)).json()
        second = (await request(server)).json()
        assert first == second  # polling does not create duplicate events
        assert first["items"][0]["type"] == event
        assert first["unread_count"] == (1 if status == "pending" else 2)
        assert all("private" not in str(item) for item in first["items"])
        if status == "confirmed":
            assert first["items"][0]["amount"] == 120
        if status == "rejected":
            assert first["items"][0]["reason"] == "illiquid_skin"
        if kind == "withdrawals":
            assert first["items"][0]["item_name"] == "Skin"
            assert first["items"][0]["amount"] == 75
        assert (await request(server, user="other")).json()["items"] == []
        assert (await server.db.users.find_one({"session_id": "owner"}))["balance"] == 100
    asyncio.run(check())


def test_recent_resolution_of_old_request_is_in_bounded_feed(notification_api):
    async def check():
        server = notification_api
        now = server.now_utc()
        await server.db.deposits.insert_many([
            {"id": f"recent-{i}", "session_id": "owner", "status": "pending", "created_at": now - timedelta(minutes=i + 1)}
            for i in range(70)
        ] + [{"id": "old", "session_id": "owner", "status": "confirmed", "credited": 50,
              "created_at": now - timedelta(days=30), "resolved_at": now}])
        feed = (await request(server)).json()
        assert len(feed["items"]) == 50
        assert feed["items"][0]["id"] == "deposit:old:confirmed"
        assert len({item["id"] for item in feed["items"]}) == 50
    asyncio.run(check())


def test_read_state_persists_and_new_resolution_stays_unread(notification_api):
    async def check():
        server = notification_api
        created = server.now_utc() - timedelta(hours=1)
        await server.db.deposits.insert_one({"id": "d", "session_id": "owner", "status": "pending", "created_at": created})
        snapshot = (await request(server)).json()
        result = await request(server, "POST", body={"read_through": snapshot["read_through"]})
        assert result.status_code == 200
        assert (await request(server)).json()["unread_count"] == 0
        await server.db.deposits.update_one({"id": "d"}, {"$set": {"status": "confirmed", "credited": 100, "resolved_at": server.now_utc()}})
        # A stale tab cannot move the read marker backwards or read the new result.
        await request(server, "POST", body={"read_through": (created - timedelta(minutes=1)).isoformat()})
        feed = (await request(server)).json()
        assert feed["unread_count"] == 1
        assert feed["items"][0]["type"] == "deposit_confirmed"
        assert not feed["items"][0]["read"] and feed["items"][1]["read"]
        assert "notifications_read_at" not in await server.db.users.find_one({"session_id": "other"})
    asyncio.run(check())


def test_authentication_validation_and_future_read_timestamp(notification_api):
    async def check():
        server = notification_api
        assert (await request(server, user=None)).status_code == 401
        assert (await request(server, "POST", user=None, body={"read_through": server.now_utc().isoformat()})).status_code == 401
        assert (await request(server, "POST", body={"read_through": "bad-date"})).status_code == 422
        future = server.now_utc() + timedelta(days=365)
        assert (await request(server, "POST", body={"read_through": future.isoformat()})).status_code == 200
        owner = await server.db.users.find_one({"session_id": "owner"})
        assert server.as_utc(owner["notifications_read_at"]) <= server.now_utc()
    asyncio.run(check())


def test_unfinished_processing_is_not_reported_as_success(notification_api):
    async def check():
        server = notification_api
        for collection, status in (("deposits", "processing"), ("withdrawals", "cancelling"), ("deposits", "payment_error")):
            await server.db[collection].insert_one({"id": status, "session_id": "owner", "status": status, "created_at": server.now_utc()})
        assert {item["type"] for item in (await request(server)).json()["items"]} == {"deposit_requested", "withdrawal_requested"}
    asyncio.run(check())
