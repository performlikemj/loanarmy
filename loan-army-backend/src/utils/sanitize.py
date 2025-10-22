"""Utility helpers to sanitize user-provided text before storage or rendering."""

from __future__ import annotations

import bleach

# Allow only very basic formatting; expand if richer markup is desired later.
_COMMENT_ALLOWED_TAGS: list[str] = []
_COMMENT_ALLOWED_ATTRS: dict[str, list[str]] = {}


def sanitize_comment_body(value: str) -> str:
    """Strip dangerous HTML from comment bodies while preserving whitespace."""
    return bleach.clean(value, tags=_COMMENT_ALLOWED_TAGS, attributes=_COMMENT_ALLOWED_ATTRS, strip=True)


def sanitize_plain_text(value: str) -> str:
    """Remove HTML tags from simple text fields such as author names."""
    return bleach.clean(value, tags=[], attributes={}, strip=True)


__all__ = ["sanitize_comment_body", "sanitize_plain_text"]
