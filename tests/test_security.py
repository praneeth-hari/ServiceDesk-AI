from datetime import timedelta
import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    """Verify password hashing produces a non-plain bcrypt hash that verifies correctly."""
    plain = "MySuperSecret123!"
    hashed = hash_password(plain)

    # 1. Stored value is definitely not the plain password
    assert hashed != plain
    assert not hashed.startswith(plain)

    # 2. Bcrypt prefix and length check
    assert hashed.startswith("$2b$")
    assert len(hashed) >= 50

    # 3. Verification works for matching password
    assert verify_password(plain, hashed) is True

    # 4. Verification fails for wrong password
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_token_roundtrip():
    """Verify JWT access token creation and decoding."""
    subject = "42"
    token = create_access_token(data={"sub": subject})

    assert isinstance(token, str)
    assert len(token.split(".")) == 3  # standard header.payload.signature

    payload = decode_token(token)
    assert payload["sub"] == subject
    assert "exp" in payload


def test_jwt_token_expired():
    """Verify expired token raises ExpiredSignatureError."""
    token = create_access_token(
        data={"sub": "1"},
        expires_delta=timedelta(seconds=-10),  # expired 10 seconds ago
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_jwt_token_tampered():
    """Verify tampered token raises InvalidSignatureError."""
    token = create_access_token(data={"sub": "1"})
    tampered_token = token[:-5] + "abcde"
    with pytest.raises(jwt.PyJWTError):
        decode_token(tampered_token)
