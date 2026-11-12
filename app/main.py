from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import assist, auth, health, holidays, reports, tickets, triage, users
from app.core.config import settings
from app.core.logging import RequestIDLoggingMiddleware, setup_logging

# Configure logging using standard library
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("helpdesk_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Checks whether SECRET_KEY is valid for production or logs a warning in development.
    """
    is_prod = getattr(settings, "APP_ENV", "development").strip().lower() == "production"
    is_placeholder = (
        settings.SECRET_KEY in ("change-me", "change_this_to_a_super_secret_key_at_least_32_chars_long")
        or "change-me" in settings.SECRET_KEY.lower()
    )
    is_short = len(settings.SECRET_KEY) < 32

    if is_prod:
        if is_placeholder:
            raise ValueError(
                "SECRET_KEY cannot be a placeholder in production. "
                "Please configure a secure random SECRET_KEY of at least 32 characters."
            )
        if is_short:
            raise ValueError(
                f"SECRET_KEY is too short for production (must be at least 32 characters, got {len(settings.SECRET_KEY)}). "
                "Please configure a secure random SECRET_KEY of at least 32 characters."
            )
    else:
        if is_placeholder:
            logger.warning(
                "SECURITY WARNING: SECRET_KEY is set to a placeholder. "
                "Please generate and set a strong, random SECRET_KEY in your .env file for production."
            )

    if settings.DEMO_MODE:
        if is_prod:
            raise ValueError(
                "DEMO_MODE cannot be enabled when APP_ENV=production: demo accounts "
                "allow passwordless sign-in (including admin)."
            )
        logger.warning(
            "SECURITY WARNING: DEMO_MODE is enabled. Demo accounts allow passwordless sign-in "
            "(including admin) and must never be enabled on a real deployment."
        )

    yield


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Standardize all HTTP error responses into {"error": {"message": "..."}} format.
    Supports structured error dictionaries with error codes, rate limit responses, and preserves headers.
    """
    headers = getattr(exc, "headers", None)
    if isinstance(exc.detail, dict):
        if "retry_after_seconds" in exc.detail:
            detail_msg = str(exc.detail.get("detail", "Too many requests"))
            content: dict[str, Any] = {
                "detail": detail_msg,
                "retry_after_seconds": exc.detail.get("retry_after_seconds"),
                "error": {"message": detail_msg},
            }
            return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

        message = str(exc.detail.get("message", ""))
        code = exc.detail.get("code") or exc.detail.get("error")
        content = {"error": {"message": message}}
        if code:
            content["code"] = code
            content["error"]["code"] = code
        return JSONResponse(status_code=exc.status_code, content=content, headers=headers)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": str(exc.detail)}},
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Standardize request validation errors into {"error": {"message": "..."}} format.
    """
    messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": {"message": "; ".join(messages)}},
    )


def mount_frontend(app: FastAPI, dist_dir_override: str | None = None) -> None:
    """
    Mount the built frontend distribution if WEB_DIST_DIR exists and contains index.html.
    Serves static assets, index.html at root, and falls back to index.html for client-side routes.
    Never intercepts /api/*, /docs, /redoc, or /openapi.json.
    """
    dist_setting = dist_dir_override if dist_dir_override is not None else settings.WEB_DIST_DIR
    dist_path = Path(dist_setting)
    if not dist_path.is_absolute():
        repo_root = Path(__file__).resolve().parent.parent
        # Check cwd first, then relative to repo root
        if not (dist_path.is_dir() and (dist_path / "index.html").is_file()):
            dist_path = repo_root / dist_setting

    index_file = dist_path / "index.html"
    if not (dist_path.is_dir() and index_file.is_file()):
        logger.info("Web dist directory not found or index.html missing at '%s'. Web UI will not be served.", dist_path)
        return

    logger.info("Serving web UI from '%s'", dist_path)

    # 1. Mount /assets directory if it exists (hashed static bundles)
    assets_dir = dist_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # 2. Serve index.html at "/" with no-cache
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_root() -> FileResponse:
        return FileResponse(
            str(index_file),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    # 3. SPA catch-all for client-side routing & top-level static assets (e.g. favicon.ico, vite.svg)
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_spa_or_static(full_path: str) -> FileResponse:
        norm_path = full_path.lstrip("/")

        # Never intercept API, docs, openapi, or redoc paths
        if (
            norm_path.startswith("api/")
            or norm_path == "api"
            or norm_path.startswith("docs")
            or norm_path.startswith("redoc")
            or norm_path == "openapi.json"
        ):
            raise StarletteHTTPException(status_code=404, detail="Not Found")

        # Reject path traversal and hidden dotfile attempts immediately
        if ".." in norm_path or norm_path.startswith(".") or "/." in norm_path or "\\." in norm_path:
            raise StarletteHTTPException(status_code=404, detail="Not Found")

        # Check if an actual static file exists in dist_path
        try:
            target = (dist_path / norm_path).resolve()
            if not target.is_relative_to(dist_path.resolve()):
                raise StarletteHTTPException(status_code=404, detail="Not Found")
            if target.is_file():
                return FileResponse(str(target))
        except (ValueError, RuntimeError):
            raise StarletteHTTPException(status_code=404, detail="Not Found") from None

        # If a path has a file extension and was not found, return 404 (not an SPA client route)
        if Path(norm_path).suffix:
            raise StarletteHTTPException(status_code=404, detail="Not Found")

        # Return index.html for client-side routes (e.g., /tickets/36, /reports)
        return FileResponse(
            str(index_file),
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )


# Content-Security-Policy for the web UI. The API docs pages (/docs, /redoc) load assets
# from a CDN and use inline scripts, so they are left without this policy.
_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
_DOCS_PREFIXES = ("/docs", "/redoc")


async def security_headers_middleware(request: Request, call_next):
    """Add baseline browser security headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if not request.url.path.startswith(_DOCS_PREFIXES):
        response.headers.setdefault("Content-Security-Policy", _CSP)
    return response


def create_app(web_dist_dir: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # Add Request ID and logging middleware
    application.add_middleware(RequestIDLoggingMiddleware)
    application.middleware("http")(security_headers_middleware)

    # Exception handlers
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Include API routers under /api/v1
    application.include_router(health.router, prefix=settings.API_V1_STR)
    application.include_router(auth.router, prefix=settings.API_V1_STR)
    application.include_router(users.router, prefix=settings.API_V1_STR)
    application.include_router(tickets.router, prefix=settings.API_V1_STR)
    application.include_router(holidays.router, prefix=settings.API_V1_STR)
    application.include_router(reports.router, prefix=settings.API_V1_STR)
    application.include_router(triage.router, prefix=settings.API_V1_STR)
    application.include_router(assist.router, prefix=settings.API_V1_STR)

    # Mount built frontend
    mount_frontend(application, dist_dir_override=web_dist_dir)

    return application


app = create_app()
