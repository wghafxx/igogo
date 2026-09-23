"""Isolated server fixture: no live database or external services."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_server(monkeypatch):
    for key, value in {
        "MONGO_URL": "mongodb://127.0.0.1:27017",
        "DB_NAME": "isolated_api_test",
        "PUBLIC_APP_URL": "http://test",
        "DISCORD_CLIENT_ID": "test",
        "DISCORD_CLIENT_SECRET": "test",
        "JWT_SECRET": "test-only-secret",
        "ADMIN_SEED_HASH": "test",
        "CORS_ORIGINS": "http://test",
    }.items():
        monkeypatch.setenv(key, value)
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(backend))
    spec = importlib.util.spec_from_file_location("isolated_test_server", backend / "server.py")
    server = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, server)
    spec.loader.exec_module(server)
    server.db = SimpleNamespace()
    try:
        yield server
    finally:
        server.client.close()


LIVE_HINTS = ("REACT_APP_BACKEND_URL", "/app/backend/.env", "/app/frontend/.env", "BASE_URL")


def pytest_collection_modifyitems(config, items):
    # Suites that talk to a running server / shared MongoDB are marked so they can be excluded: -m "not live".
    cache = {}
    for item in items:
        path = Path(str(item.fspath))
        if path not in cache:
            cache[path] = any(h in path.read_text(errors="ignore") for h in LIVE_HINTS)
        if cache[path]:
            item.add_marker(pytest.mark.live)


# Shared isolated `api` fixture (ASGI app + disposable Mongo) for suites that do not define their own.
from test_admin_tools import api  # noqa: E402,F401
