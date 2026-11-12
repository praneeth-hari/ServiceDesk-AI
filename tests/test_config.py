import logging
import os
from unittest import mock
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app


def test_settings_default_values():
    """Test default values of Settings."""
    with mock.patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.PROJECT_NAME == "HelpDesk API"
        assert settings.VERSION == "0.1.0"
        assert settings.API_V1_STR == "/api/v1"
        assert "mysql+pymysql" in settings.DATABASE_URL
        assert settings.SECRET_KEY == "change-me"


def test_settings_custom_env_override():
    """Test that environment variables override defaults."""
    custom_db_url = "mysql+pymysql://user:pass@remote:3306/custom_db"
    custom_secret = "custom_secret_key_at_least_32_chars_long"
    with mock.patch.dict(os.environ, {"DATABASE_URL": custom_db_url, "SECRET_KEY": custom_secret}):
        custom_settings = Settings(_env_file=None)
        assert custom_settings.DATABASE_URL == custom_db_url
        assert custom_settings.SECRET_KEY == custom_secret


def test_startup_warning_when_placeholder_secret_used(caplog):
    """Test that startup logs a warning when the placeholder SECRET_KEY is used."""
    from app.core.config import settings

    original_secret = settings.SECRET_KEY
    try:
        settings.SECRET_KEY = "change-me"
        with caplog.at_level(logging.WARNING, logger="helpdesk_api"):
            with TestClient(app):
                pass
        warning_records = [rec for rec in caplog.records if "SECURITY WARNING" in rec.message]
        assert len(warning_records) >= 1
        # Crucial security check: the warning MUST NOT leak the key value
        assert "change-me" not in warning_records[0].message
        assert "SECRET_KEY is set to a placeholder" in warning_records[0].message
    finally:
        settings.SECRET_KEY = original_secret


def test_sla_settings_defaults_and_validation():
    """Test SLA configuration defaults and startup validation checks."""
    settings = Settings(_env_file=None)
    assert settings.WORK_TIMEZONE == "Asia/Kolkata"
    assert settings.WORK_DAY_START == "09:00"
    assert settings.WORK_DAY_END == "18:00"
    assert settings.WORK_DAYS == [0, 1, 2, 3, 4]

    # Test invalid timezone
    with pytest.raises(ValueError, match="Invalid WORK_TIMEZONE"):
        Settings(_env_file=None, WORK_TIMEZONE="Invalid/Timezone")

    # Test empty working days
    with pytest.raises(ValueError, match="WORK_DAYS must contain at least one working day"):
        Settings(_env_file=None, WORK_DAYS=[])

    # Test start time not before end time
    with pytest.raises(ValueError, match="must be strictly before WORK_DAY_END"):
        Settings(_env_file=None, WORK_DAY_START="18:00", WORK_DAY_END="09:00")


def test_production_secret_refuses_placeholder():
    """In production, using a placeholder SECRET_KEY fails startup and validation."""
    # 1. Direct Settings validation
    with pytest.raises(ValueError, match="cannot be a placeholder in production"):
        Settings(_env_file=None, APP_ENV="production", SECRET_KEY="change-me")

    # 2. App startup lifespan check
    from app.core.config import settings
    orig_env = settings.APP_ENV
    orig_key = settings.SECRET_KEY
    try:
        settings.APP_ENV = "production"
        settings.SECRET_KEY = "change-me"
        with pytest.raises(ValueError, match="cannot be a placeholder in production"):
            with TestClient(app):
                pass
    finally:
        settings.APP_ENV = orig_env
        settings.SECRET_KEY = orig_key


def test_production_secret_refuses_short_key():
    """In production, using a SECRET_KEY shorter than 32 characters fails."""
    # 1. Direct Settings validation
    with pytest.raises(ValueError, match="too short for production"):
        Settings(_env_file=None, APP_ENV="production", SECRET_KEY="too-short-secret-key")

    # 2. App startup lifespan check
    from app.core.config import settings
    orig_env = settings.APP_ENV
    orig_key = settings.SECRET_KEY
    try:
        settings.APP_ENV = "production"
        settings.SECRET_KEY = "short-key-12345"
        with pytest.raises(ValueError, match="too short for production"):
            with TestClient(app):
                pass
    finally:
        settings.APP_ENV = orig_env
        settings.SECRET_KEY = orig_key


def test_production_secret_good_48_char_key_starts():
    """In production, a strong 48-character key allows normal startup without errors."""
    from app.core.config import settings
    good_secret = "a" * 48
    s = Settings(_env_file=None, APP_ENV="production", SECRET_KEY=good_secret)
    assert s.SECRET_KEY == good_secret

    orig_env = settings.APP_ENV
    orig_key = settings.SECRET_KEY
    try:
        settings.APP_ENV = "production"
        settings.SECRET_KEY = good_secret
        with TestClient(app) as client:
            resp = client.get("/openapi.json")
            assert resp.status_code == 200
    finally:
        settings.APP_ENV = orig_env
        settings.SECRET_KEY = orig_key


def test_development_secret_placeholder_only_warns(caplog):
    """In development, a placeholder SECRET_KEY only logs a warning and allows startup."""
    from app.core.config import settings
    orig_env = settings.APP_ENV
    orig_key = settings.SECRET_KEY
    try:
        settings.APP_ENV = "development"
        settings.SECRET_KEY = "change-me"
        with caplog.at_level(logging.WARNING, logger="helpdesk_api"):
            with TestClient(app) as client:
                resp = client.get("/openapi.json")
                assert resp.status_code == 200
        warning_records = [rec for rec in caplog.records if "SECURITY WARNING" in rec.message]
        assert len(warning_records) >= 1
        assert "change-me" not in warning_records[0].message
    finally:
        settings.APP_ENV = orig_env
        settings.SECRET_KEY = orig_key


def test_database_connect_args_no_ca():
    """(a) When no CA is configured, connect_args is empty (behaviour unchanged)."""
    from app.db.session import get_database_connect_args
    args = get_database_connect_args(
        url="mysql+pymysql://user:pass@localhost:3306/db",
        ssl_ca=None,
        ssl_ca_pem=None,
    )
    assert args == {}


def test_database_connect_args_ca_path_mysql():
    """(b) When a CA path is configured with a MySQL URL, ssl={'ca': path} is returned."""
    from app.db.session import get_database_connect_args
    ca_path = "/etc/ssl/certs/custom-ca.pem"
    args = get_database_connect_args(
        url="mysql+pymysql://user:pass@remotedb:3306/db",
        ssl_ca=ca_path,
    )
    assert args == {"ssl": {"ca": ca_path}}


def test_database_connect_args_pem_text():
    """(c) When PEM text is provided, it is written to a temp file and passed in ssl={'ca': path}."""
    from pathlib import Path
    from app.db.session import get_database_connect_args
    pem_content = "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAgIJALTestCert\n-----END CERTIFICATE-----"
    args = get_database_connect_args(
        url="mysql+pymysql://user:pass@remotedb:3306/db",
        ssl_ca_pem=pem_content,
    )
    assert "ssl" in args
    assert "ca" in args["ssl"]
    temp_ca_path = args["ssl"]["ca"]
    assert Path(temp_ca_path).exists()
    assert Path(temp_ca_path).read_text(encoding="utf-8") == pem_content


def test_database_connect_args_sqlite_with_ca_set():
    """(d) When a CA is configured but the URL is SQLite, no ssl args are applied (returns {})."""
    from app.db.session import get_database_connect_args
    args = get_database_connect_args(
        url="sqlite:////tmp/test.db",
        ssl_ca="/etc/ssl/certs/custom-ca.pem",
    )
    assert args == {}

    args_memory = get_database_connect_args(
        url="sqlite:///:memory:",
        ssl_ca_pem="-----BEGIN CERTIFICATE-----\n...",
    )
    assert args_memory == {}



def test_demo_mode_refused_in_production():
    """DEMO_MODE (passwordless admin sign-in) must prevent startup in production."""
    from app.core.config import settings
    orig = (settings.APP_ENV, settings.SECRET_KEY, settings.DEMO_MODE)
    try:
        settings.APP_ENV = "production"
        settings.SECRET_KEY = "x" * 48
        settings.DEMO_MODE = True
        with pytest.raises(ValueError, match="DEMO_MODE cannot be enabled"):
            with TestClient(app):
                pass
    finally:
        settings.APP_ENV, settings.SECRET_KEY, settings.DEMO_MODE = orig
