from fastapi.testclient import TestClient

from app.main import app


def test_health():
    assert TestClient(app).get("/health").json() == {"status": "ok", "version": "dev"}


def test_route_protegee_sans_jeton():
    response = TestClient(app).get("/auth/me")
    assert response.status_code == 401
