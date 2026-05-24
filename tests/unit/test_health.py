from fastapi.testclient import TestClient

from src.api.app import create_app

client = TestClient(create_app())


def test_liveness_returns_ok() -> None:
    response = client.get("/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
