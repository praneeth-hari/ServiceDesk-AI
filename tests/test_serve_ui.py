import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import create_app


def test_serve_ui_when_dist_exists(tmp_path: Path):
    """When WEB_DIST_DIR exists with index.html, FastAPI serves UI and SPA routes safely."""
    # Setup mock web/dist
    index_html_content = "<!DOCTYPE html><html><head><title>ServiceDesk</title></head><body><div id='root'>App</div></body></html>"
    (tmp_path / "index.html").write_text(index_html_content, encoding="utf-8")

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    (assets_dir / "app-bundle.js").write_text("console.log('test bundle');", encoding="utf-8")

    (tmp_path / "favicon.ico").write_text("fake-icon-content", encoding="utf-8")

    app = create_app(web_dist_dir=str(tmp_path))
    with TestClient(app) as client:
        # 1. Root route returns index.html with no-cache headers
        resp = client.get("/")
        assert resp.status_code == 200
        assert "ServiceDesk" in resp.text
        assert resp.headers.get("content-type", "").startswith("text/html")
        assert "no-cache" in resp.headers.get("cache-control", "")

        # 2. Client-side SPA routes fallback to index.html with no-cache headers
        resp = client.get("/tickets/36")
        assert resp.status_code == 200
        assert "ServiceDesk" in resp.text
        assert "no-cache" in resp.headers.get("cache-control", "")

        resp = client.get("/reports")
        assert resp.status_code == 200
        assert "ServiceDesk" in resp.text

        # 3. Static assets served from /assets
        resp = client.get("/assets/app-bundle.js")
        assert resp.status_code == 200
        assert "test bundle" in resp.text

        # 4. Top-level static asset served from dist root
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert resp.text == "fake-icon-content"

        # 5. API routes are never intercepted by the SPA fallback
        # (health checks the DB so may return 503 in CI; we only care it returns JSON, not index.html)
        resp = client.get("/api/v1/health")
        assert resp.status_code in (200, 503)
        assert resp.headers["content-type"].startswith("application/json")
        assert "ServiceDesk" not in resp.text  # index.html was NOT returned

        # 6. Unknown API routes return standard JSON 404, never index.html
        resp = client.get("/api/v1/nonexistent-route")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"error": {"message": "Not Found"}}

        # 7. Swagger docs & openapi.json are preserved (no DB required)
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "html" in resp.headers.get("content-type", "").lower()

        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "openapi" in resp.json()

        # 8. Path traversal attempts are blocked and return 404
        resp = client.get("/../.env")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"message": "Not Found"}}

        resp = client.get("/assets/../../app/main.py")
        assert resp.status_code in (404, 400)

        # 9. HEAD requests accept root and SPA routes, but never intercept API routes
        resp_head_root = client.head("/")
        assert resp_head_root.status_code == 200
        assert resp_head_root.headers.get("content-type", "").startswith("text/html")

        resp_head_ticket = client.head("/tickets/1")
        assert resp_head_ticket.status_code == 200
        assert resp_head_ticket.headers.get("content-type", "").startswith("text/html")

        resp_head_nonexistent_api = client.head("/api/v1/nonexistent")
        assert resp_head_nonexistent_api.status_code == 404
        assert not resp_head_nonexistent_api.headers.get("content-type", "").startswith("text/html")
        assert resp_head_nonexistent_api.headers.get("content-type", "").startswith("application/json")


def test_serve_ui_when_dist_does_not_exist(tmp_path: Path):
    """When WEB_DIST_DIR does not exist, app functions as an API-only service."""
    non_existent = tmp_path / "does_not_exist"
    app = create_app(web_dist_dir=str(non_existent))

    with TestClient(app) as client:
        # Root returns 404 JSON because no UI is mounted
        resp = client.get("/")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"message": "Not Found"}}

        # API health works normally (may return 503 in CI if DB is unavailable; we only care it returns JSON)
        resp = client.get("/api/v1/health")
        assert resp.status_code in (200, 503)
        assert resp.headers["content-type"].startswith("application/json")

        # /openapi.json is served regardless of DB state
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert "openapi" in resp.json()

        # Client route returns 404 JSON
        resp = client.get("/tickets/1")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"message": "Not Found"}}


def test_serve_ui_when_index_html_missing(tmp_path: Path):
    """When WEB_DIST_DIR exists but index.html is missing, app does not serve UI."""
    # tmp_path exists but is empty
    app = create_app(web_dist_dir=str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"message": "Not Found"}}

