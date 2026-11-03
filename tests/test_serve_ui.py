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

        # 5. API routes are never intercepted
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 6. Unknown API routes return standard JSON 404, never index.html
        resp = client.get("/api/v1/nonexistent-route")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"error": {"message": "Not Found"}}

        # 7. Swagger docs & openapi.json are preserved
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


def test_serve_ui_when_dist_does_not_exist(tmp_path: Path):
    """When WEB_DIST_DIR does not exist, app functions as an API-only service."""
    non_existent = tmp_path / "does_not_exist"
    app = create_app(web_dist_dir=str(non_existent))

    with TestClient(app) as client:
        # Root returns 404 JSON because no UI is mounted
        resp = client.get("/")
        assert resp.status_code == 404
        assert resp.json() == {"error": {"message": "Not Found"}}

        # API health works normally
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

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

