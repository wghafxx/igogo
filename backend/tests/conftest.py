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
