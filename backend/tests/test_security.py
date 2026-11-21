from datetime import timedelta
from pathlib import Path
import pytest
from app.config import settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    password_needs_rehash,
    verify_password,
)


def test_password_hashing_and_verification():
    """Verify password hashing creates valid Argon2id hash and verifies correctly."""
    plain = "SecurePassword@2026"
    hashed = get_password_hash(plain)

    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert verify_password(plain, hashed) is True


def test_wrong_password_rejection():
    """Verify wrong password returns False without raising exceptions."""
    hashed = get_password_hash("CorrectPassword@123")
    assert verify_password("WrongPassword@123", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password("CorrectPassword@123", "") is False


def test_empty_password_hash_raises_value_error():
    """Verify empty plaintext password cannot be hashed."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        get_password_hash("")


def test_verify_against_seed_sql_argon2id_hash():
    """
    Verify the existing demo hash in database/02_seed_and_test.sql.
    Seed accounts use Demo@123 with hash parameters:
    $argon2id$v=19$m=65536,t=3,p=4
    """
    sql_file = Path(__file__).resolve().parent.parent.parent / "database" / "02_seed_and_test.sql"
    assert sql_file.exists(), "02_seed_and_test.sql must exist"

    # Extract the seed hash directly from the SQL file without modifying it
    seed_hash = None
    with open(sql_file, "r", encoding="utf-8") as f:
        for line in f:
            if "$argon2id$" in line and not line.strip().startswith("--"):
                start_idx = line.find("$argon2id$")
                end_idx = line.find("'", start_idx)
                seed_hash = line[start_idx:end_idx] if end_idx != -1 else line[start_idx:].strip("', \n\r")
                break


    assert seed_hash is not None, "Seed Argon2id hash must be present in 02_seed_and_test.sql"
    assert seed_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")

    # Verify seed credentials: Demo@123 against the extracted hash
    assert verify_password("Demo@123", seed_hash) is True
    assert verify_password("IncorrectPassword", seed_hash) is False
    assert password_needs_rehash(seed_hash) is False


def test_jwt_creation_and_successful_decoding():
    """Verify JWT access token creation and decoding with claims."""
    claims = {
        "sub": "b2c1a0e5-7e89-4b67-9301-123456789abc",
        "email": "demo@smartcart.in",
        "role": "CUSTOMER",
    }
    token = create_access_token(data=claims)
    assert isinstance(token, str)

    decoded = decode_access_token(token)
    assert decoded["sub"] == claims["sub"]
    assert decoded["email"] == claims["email"]
    assert decoded["role"] == claims["role"]
    assert "exp" in decoded
    assert "iat" in decoded


def test_jwt_custom_expiration_delta():
    """Verify custom expires_delta overrides the default expiry."""
    claims = {"sub": "user-uuid-123"}
    short_delta = timedelta(seconds=120)
    token = create_access_token(data=claims, expires_delta=short_delta)

    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-uuid-123"
    # Expiry difference should be approximately 120 seconds
    diff = decoded["exp"] - decoded["iat"]
    assert 118 <= diff <= 122


def test_expired_token_rejection():
    """Verify decode_access_token raises TokenExpiredError on expired tokens."""
    claims = {"sub": "user-uuid-expired"}
    negative_delta = timedelta(seconds=-10)
    expired_token = create_access_token(data=claims, expires_delta=negative_delta)

    with pytest.raises(TokenExpiredError, match="Access token has expired"):
        decode_access_token(expired_token)


def test_invalid_signature_rejection():
    """Verify tokens signed with a different key are rejected with InvalidTokenError."""
    claims = {"sub": "user-uuid-tampered"}
    foreign_key = "a-different-secret-key-that-does-not-match-settings"
    token = create_access_token(data=claims, secret_key=foreign_key)

    with pytest.raises(InvalidTokenError, match="Could not validate access token signature"):
        decode_access_token(token)


def test_malformed_token_rejection():
    """Verify malformed token strings are rejected with InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        decode_access_token("this.is.not.a.valid.jwt")


def test_missing_or_empty_sub_claim_rejection():
    """Verify token creation and decoding require a non-empty 'sub' claim."""
    # Creation rejects missing sub
    with pytest.raises(ValueError, match="JWT payload must include a non-empty 'sub'"):
        create_access_token(data={"email": "no-sub@example.com"})

    with pytest.raises(ValueError, match="JWT payload must include a non-empty 'sub'"):
        create_access_token(data={"sub": "   "})


def test_missing_jwt_secret_configuration():
    """Verify ValueError is raised if JWT_SECRET_KEY is empty."""
    claims = {"sub": "user-123"}
    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be configured"):
        create_access_token(data=claims, secret_key="")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY must be configured"):
        decode_access_token("some.token.here", secret_key="")
