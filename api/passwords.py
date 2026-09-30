"""Password hashing for owner accounts (Phase G).

Uses stdlib scrypt — no extra dependencies. Legacy ``demo:{plaintext}``
hashes from Phase D are still accepted at login and transparently upgraded
on the next successful authentication.
"""

from __future__ import annotations

import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt:{salt}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("demo:"):
        return stored == f"demo:{password}"
    if not stored.startswith("scrypt:"):
        return False
    try:
        _, salt, expected_hex = stored.split(":", 2)
    except ValueError:
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return secrets.compare_digest(digest.hex(), expected_hex)


def needs_rehash(stored: str) -> bool:
    return stored.startswith("demo:")
