from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def test_health_success(client: TestClient):
    """Test health check returns 200 and healthy status when database is reachable."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "helpdesk-api"
    assert data["database"] == "connected"


def test_health_database_failure():
    """Test health check returns 503 and formatted error when database is unreachable."""
    def broken_get_db():
        class BrokenSession:
            def execute(self, statement):
                raise ConnectionError("Could not connect to database")

            def close(self):
                pass

        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_get_db
    with TestClient(app) as test_client:
        response = test_client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert "error" in data
        assert data["error"]["message"] == "Database connection failed"
    app.dependency_overrides.clear()

def test_security_headers_present_and_docs_exempt_from_csp(client):
    """API responses carry baseline security headers; /docs is exempt from the CSP."""
    res = client.get("/api/v1/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]

    docs = client.get("/docs")
    assert docs.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in docs.headers
