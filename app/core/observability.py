"""Optional error tracking with Sentry (off unless SENTRY_DSN is set)."""
import logging

from app.core.config import settings

logger = logging.getLogger("helpdesk_api")


def init_sentry() -> bool:
    """Start Sentry if SENTRY_DSN is set and sentry-sdk is installed. Returns True if it started."""
    if not settings.SENTRY_DSN:
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed (pip install -r requirements-optional.txt)"
        )
        return False

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Never attach user details, request bodies or cookies to error reports
        send_default_pii=False,
    )
    logger.info("Sentry error tracking enabled")
    return True
