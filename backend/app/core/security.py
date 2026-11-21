"""
Cryptographic security module for SmartCart 2.0.
Provides Argon2id password hashing and JWT access token creation/verification.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import argon2
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import ExpiredSignatureError, JWTError, jwt

from app.config import settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

# Argon2id hasher configured to match PostgreSQL seed credentials exactly:
# $argon2id$v=19$m=65536,t=3,p=4
_hasher = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=argon2.Type.ID,
)


def get_password_hash(password: str) -> str:
    """
    Hash a plaintext password using Argon2id with production parameters:
    m=65536 (64 MB), t=3 iterations, p=4 parallelism.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    return _hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against an Argon2id hash in constant time.
    Returns True if valid, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """Check if the given hash was created with outdated Argon2 parameters."""
    return _hasher.check_needs_rehash(hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> str:
    """
    Create a signed JWT access token.
    Token subject ('sub') must be present.
    Expiry defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    key = secret_key if secret_key is not None else settings.JWT_SECRET_KEY
    if not key or not key.strip():
        raise ValueError("JWT_SECRET_KEY must be configured and non-empty")

    algo = algorithm or settings.JWT_ALGORITHM

    to_encode = data.copy()
    if "sub" not in to_encode or not str(to_encode["sub"]).strip():
        raise ValueError("JWT payload must include a non-empty 'sub' (subject) claim")

    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, key, algorithm=algo)


def decode_access_token(
    token: str,
    secret_key: Optional[str] = None,
    algorithm: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Decode, verify signature, and validate claims of a JWT access token.
    Raises TokenExpiredError if expired.
    Raises InvalidTokenError if signature, format, or required claims are invalid.
    """
    key = secret_key if secret_key is not None else settings.JWT_SECRET_KEY
    if not key or not key.strip():
        raise ValueError("JWT_SECRET_KEY must be configured and non-empty")

    algo = algorithm or settings.JWT_ALGORITHM

    try:
        payload = jwt.decode(token, key, algorithms=[algo])
    except ExpiredSignatureError as e:
        raise TokenExpiredError("Access token has expired") from e
    except JWTError as e:
        raise InvalidTokenError("Could not validate access token signature or format") from e

    sub = payload.get("sub")
    if sub is None or not str(sub).strip():
        raise InvalidTokenError("Access token missing valid subject ('sub') claim")

    return payload
