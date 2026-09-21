"""Password hashing helpers using stdlib PBKDF2-HMAC."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os


_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "210000"))
_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), salt, _ITERATIONS)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_{_ALGORITHM}${_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_raw, salt_b64, digest_b64 = password_hash.split("$", 3)
        if scheme != f"pbkdf2_{_ALGORITHM}":
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False
