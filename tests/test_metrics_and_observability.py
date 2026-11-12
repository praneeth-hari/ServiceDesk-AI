from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


@contextmanager
def _app_client(**overrides):
    """A TestClient for a fresh app, with settings overridden for the whole `with` block."""
    with patch.multiple(settings, **overrides):
        yield TestClient(create_app())


def test_metrics_endpoint_is_off_by_default(client: TestClient):
    res = client.get("/metrics")
    assert "helpdesk_http_requests_total" not in res.text


def test_metrics_count_requests_by_route_template():
    with _app_client(METRICS_ENABLED=True, METRICS_TOKEN=None) as app_client:
        app_client.get("/api/v1/health")
        app_client.get("/api/v1/tickets/123")  # 401, but the route template is still what is labelled
        app_client.get("/api/v1/does-not-exist-abc")
        body = app_client.get("/metrics").text
    assert 'helpdesk_http_requests_total{method="GET",route="/api/v1/health"' in body
    assert 'route="/api/v1/tickets/{id}",status="401"' in body
    # Raw ids and unknown URLs never become labels (keeps cardinality small)
    assert "/api/v1/tickets/123" not in body
    assert "does-not-exist-abc" not in body
    assert "helpdesk_http_request_duration_seconds_bucket" in body
    # The scrape itself is not counted
    assert 'route="/metrics"' not in body


def test_metrics_requires_bearer_token_when_configured():
    with _app_client(METRICS_ENABLED=True, METRICS_TOKEN="s3cret-token") as app_client:
        assert app_client.get("/metrics").status_code == 401
        assert app_client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = app_client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"})
        assert ok.status_code == 200
        assert "# HELP" in ok.text


def test_sentry_is_off_without_a_dsn():
    from app.core.observability import init_sentry

    with patch.object(settings, "SENTRY_DSN", None):
        assert init_sentry() is False


def test_sentry_without_the_package_logs_and_continues(caplog):
    import builtins

    from app.core.observability import init_sentry

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("no sentry")
        return real_import(name, *args, **kwargs)

    with patch.object(settings, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1"):
        with patch("builtins.__import__", side_effect=fake_import):
            with caplog.at_level("WARNING", logger="helpdesk_api"):
                assert init_sentry() is False
    assert "sentry-sdk is not installed" in caplog.text
