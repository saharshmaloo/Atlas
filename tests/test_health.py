import pytest
from fastapi.testclient import TestClient

from atlas.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok_json(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_health_rejects_mutating_methods(client, method):
    response = client.request(method, "/health")

    assert response.status_code == 405
    assert "GET" in response.headers["allow"]


def test_unknown_route_returns_not_found(client):
    assert client.get("/missing").status_code == 404
