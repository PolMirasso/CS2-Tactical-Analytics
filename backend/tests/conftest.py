from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Configure the app before any app import triggers get_settings() caching.
_TMP = tempfile.mkdtemp(prefix="cs2-test-")
os.environ.update(
    CS2_DB_URL=f"sqlite:///{_TMP}/test.db",
    CS2_DATA_DIR=f"{_TMP}/data",
    CS2_MODEL_DIR=f"{_TMP}/models",
    CS2_USE_SAMPLE_DATA="true",
    CS2_BOOTSTRAP_ADMIN_EMAIL="admin@cs2.local",
    CS2_BOOTSTRAP_ADMIN_PASSWORD="admin",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def register_and_login(client: TestClient, email: str, password: str = "secret123") -> str:
    client.post("/auth/register", json={"email": email, "password": password})
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
