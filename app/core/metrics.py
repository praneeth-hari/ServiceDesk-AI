"""
Prometheus metrics: request counts and latency per route.

Enabled with METRICS_ENABLED=true, which exposes /metrics. If METRICS_TOKEN is set, scrapers must
send 'Authorization: Bearer <token>'. Labels use the route template (for example /api/v1/tickets/{id}),
never the raw path, so the number of label values stays small.
"""
import hmac
import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app.core.config import settings

REQUESTS = Counter(
    "helpdesk_http_requests_total",
    "HTTP requests handled",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "helpdesk_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

_SKIP_ROUTES = {"/metrics"}


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if not path:
        return "unmatched"
    if path.startswith("/{"):
        # The web UI / static catch-all, which also answers unknown URLs
        return "frontend"
    if request.url.path.startswith(settings.API_V1_STR):
        # Included routers report their path without the API prefix
        return f"{settings.API_V1_STR}{path}"
    return path


async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = _route_label(request)
    if route not in _SKIP_ROUTES:
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
    return response


def metrics_endpoint(request: Request) -> Response:
    token = settings.METRICS_TOKEN
    if token:
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
