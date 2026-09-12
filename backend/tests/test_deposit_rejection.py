"""Deposit rejection API checks using an isolated in-memory collection."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException


@pytest.fixture
def rejection_api(isolated_server):
    server = isolated_server

    deposit = {"id": "deposit-1", "session_id": "player-1", "status": "pending"}
    collection = MagicMock()

    async def update(query, change):
        matched = all(deposit.get(key) == value for key, value in query.items())
        if matched:
            deposit.update(change["$set"])
        return SimpleNamespace(matched_count=int(matched))

    def find(query, projection):
        cursor = MagicMock()
        rows = [dict(deposit)] if all(deposit.get(key) == value for key, value in query.items()) else []
        cursor.sort.return_value.to_list = AsyncMock(return_value=rows)
        return cursor

    collection.update_one = AsyncMock(side_effect=update)
    collection.find.side_effect = find
    server.db = SimpleNamespace(deposits=collection)
    server.require_admin = AsyncMock(return_value={"jti": "test-admin"})
    server.require_user = AsyncMock(return_value={"session_id": "player-1"})

    def request(method, path, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(send())

    yield SimpleNamespace(request=request, deposit=deposit, collection=collection, server=server)


@pytest.mark.parametrize("reason", ["illiquid_skin", "yellow_tag", "no_reason"])
def test_reason_is_saved_and_visible_to_admin_and_player(rejection_api, reason):
    api = rejection_api
    result = api.request("POST", "/api/admin/deposits/deposit-1/reject", json={"reason": reason})
    assert result.status_code == 200
    assert api.deposit["status"] == "rejected"
    assert api.deposit["resolved_at"] is not None
    for path in ("/api/admin/deposits?status=rejected", "/api/deposits/my"):
        response = api.request("GET", path)
        assert response.status_code == 200
        assert response.json()[0]["rejection_reason"] == reason
    again = api.request("POST", "/api/admin/deposits/deposit-1/reject", json={"reason": "no_reason"})
    assert again.status_code == 404
    assert api.deposit["rejection_reason"] == reason


@pytest.mark.parametrize("body", [None, {}, {"reason": ""}, {"reason": None}, {"reason": "custom"}])
def test_reason_must_be_explicit_and_supported(rejection_api, body):
    result = rejection_api.request("POST", "/api/admin/deposits/deposit-1/reject", json=body)
    assert result.status_code == 422
    rejection_api.collection.update_one.assert_not_awaited()
    assert rejection_api.deposit["status"] == "pending"


@pytest.mark.parametrize("status", ["processing", "confirmed", "cancelled", "rejected"])
def test_processed_deposit_cannot_be_rejected(rejection_api, status):
    rejection_api.deposit["status"] = status
    result = rejection_api.request("POST", "/api/admin/deposits/deposit-1/reject", json={"reason": "illiquid_skin"})
    assert result.status_code == 404
    assert rejection_api.deposit == {"id": "deposit-1", "session_id": "player-1", "status": status}


def test_rejection_requires_admin(rejection_api):
    rejection_api.server.require_admin.side_effect = HTTPException(403, "Forbidden")
    result = rejection_api.request("POST", "/api/admin/deposits/deposit-1/reject", json={"reason": "no_reason"})
    assert result.status_code == 403
    rejection_api.collection.update_one.assert_not_awaited()


def test_unknown_deposit_is_not_updated(rejection_api):
    result = rejection_api.request("POST", "/api/admin/deposits/missing/reject", json={"reason": "no_reason"})
    assert result.status_code == 404
    assert rejection_api.deposit["status"] == "pending"
