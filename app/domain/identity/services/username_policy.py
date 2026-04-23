"""Username policy (GitHub-like) for CleverDocs.

Rules:
- 1..39 characters
- lowercase letters, digits, hyphen
- cannot start or end with hyphen
- cannot contain consecutive hyphens
"""

from __future__ import annotations

import re


_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")


def validate_username_github_like(username: str) -> str:
    u = (username or "").strip()
    if not u:
        raise ValueError("USERNAME_EMPTY")
    if len(u) > 39:
        raise ValueError("USERNAME_TOO_LONG")
    if not _USERNAME_RE.match(u):
        raise ValueError("USERNAME_INVALID")
    if "--" in u:
        raise ValueError("USERNAME_INVALID")
    return u

