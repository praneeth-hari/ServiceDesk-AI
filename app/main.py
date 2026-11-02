from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, health, holidays, reports, tickets, triage, users
from app.core.config import settings
from app.core.logging import RequestIDLoggingMiddleware, setup_logging

# Configure logging using standard library
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("helpdesk_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Checks whether SECRET_KEY is using a default placeholder and logs a warning.
    """
    if settings.SECRET_KEY in ("change-me", "change_this_to_a_super_secret_key_at_least_32_chars_long") or "change-me" in settings.SECRET_KEY.lower():
        logger.warning(
            "SECURITY WARNING: SECRET_KEY is set to a placeholder. "
            "Please generate and set a strong, random SECRET_KEY in your .env file for production."
        )
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Add Request ID and logging middleware
app.add_middleware(RequestIDLoggingMiddleware)



@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Standardize all HTTP error responses into {"error": {"message": "..."}} format.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Standardize request validation errors into {"error": {"message": "..."}} format.
    """
    messages = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": {"message": "; ".join(messages)}},
    )


# Include API routers under /api/v1
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(tickets.router, prefix=settings.API_V1_STR)
app.include_router(holidays.router, prefix=settings.API_V1_STR)
app.include_router(reports.router, prefix=settings.API_V1_STR)
app.include_router(triage.router, prefix=settings.API_V1_STR)