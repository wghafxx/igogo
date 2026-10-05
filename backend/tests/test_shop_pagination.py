"""Pagination boundaries and filtering through the real catalog API."""

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest


class Cursor:
    def __init__(self, rows):
        self.rows = list(rows)

    def sort(self, fields):
        for key, direction in reversed(fields):
            self.rows.sort(key=lambda row: row[key], reverse=direction == -1)
        return self

    def skip(self, offset):
        self.rows = self.rows[offset:]
        return self

    async def to_list(self, limit):
        return self.rows[:limit]


@pytest.fixture
def catalog(isolated_server):
    # More than the old 60-item limit, with tied prices and shuffled insertion order.
    rows = [{"id": f"skin-{i:03}", "type": "AWP", "name": f"Skin {i}", "price": 100 + i // 2, "rarity": "pink"} for i in reversed(range(76))]

    def matching(query):
        result = rows
        for key, value in query.items():
            if key == "price":
                result = [r for r in result if value.get("$gte", 0) <= r["price"] <= value.get("$lte", float("inf"))]
            elif key == "$or":
                result = [r for r in result if any(re.search(rule["$regex"], r[field], re.I) for entry in value for field, rule in entry.items())]
            else:
                result = [r for r in result if r[key] == value]
        return result

    isolated_server.db.shop_items = SimpleNamespace(
        count_documents=AsyncMock(side_effect=lambda query: len(matching(query))),
        find=lambda query, projection: Cursor(matching(query)),
    )

    def get(**params):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=isolated_server.app), base_url="http://test") as client:
                return await client.get("/api/shop", params=params)
        return asyncio.run(send())

    return SimpleNamespace(rows=rows, get=get)


@pytest.mark.parametrize("sort", ["price_asc", "price_desc"])
def test_pages_cover_the_whole_catalog_without_duplicates(catalog, sort):
    collected = []
    for page in range(1, 7):
        response = catalog.get(page=page, limit=15, sort=sort)
        assert response.status_code == 200
        data = response.json()
        assert (data["page"], data["pages"], data["total"]) == (page, 6, 76)
        assert len(data["items"]) == (15 if page < 6 else 1)
        collected.extend(data["items"])
    expected = sorted(catalog.rows, key=lambda r: (r["price"] if sort == "price_asc" else -r["price"], r["id"]))
    assert collected == expected


def test_filters_apply_before_pagination(catalog):
    response = catalog.get(page=2, limit=3, min_price=105, max_price=110, q="AWP", rarity="pink", sort="price_asc")
    assert response.status_code == 200
    data = response.json()
    assert (data["total"], data["pages"], data["page"]) == (12, 4, 2)
    assert [item["id"] for item in data["items"]] == ["skin-013", "skin-014", "skin-015"]


def test_empty_catalog_has_no_items(catalog):
    data = catalog.get(page=5, limit=15, max_price=0).json()
    assert data == {"items": [], "total": 0, "page": 1, "pages": 1}


def test_out_of_range_page_returns_last_available_page(catalog):
    data = catalog.get(page=100, limit=15).json()
    assert (data["page"], data["pages"], len(data["items"])) == (6, 6, 1)


@pytest.mark.parametrize("page", [0, -1])
def test_invalid_page_is_rejected(catalog, page):
    assert catalog.get(page=page, limit=15).status_code == 422
