from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        alias_domain="example.org",
        admin_username="admin",
        admin_password="test-password-for-tests-123",
        app_secret="a" * 48,
        database_path=str(tmp_path / "test.sqlite3"),
        cookie_secure=False,
        enable_smtp=False,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def authed(client):
    response = client.post("/api/login", json={"username":"admin", "password":"test-password-for-tests-123"})
    assert response.status_code == 200
    token = client.get("/api/me").json()["csrf"]
    client.headers.update({"X-CSRF-Token": token})
    return client
