"""Private file primitives of the layout store: plain names and atomic writes.

A rejected name here is a programming error (a session uuid is not user input), so these
helpers raise ``ValueError``. ``write_text_atomic`` never leaves the temp file behind:
it is replaced on success and unlinked on failure.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

TEMP_PREFIX: Final[str] = "."
TEMP_SUFFIX: Final[str] = ".tmp"
"""Both halves of the temp-file name, so ``.s1.json.tmp`` never looks like a snapshot."""

PLAIN_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9._-]+")
"""A session name or window uuid becomes a file name, so it may not escape the root."""


def check_plain_name(value: str, what: str) -> str:
    """Return ``value`` when it is a safe single path component, else raise ``ValueError``."""
    if not value or PLAIN_NAME_RE.fullmatch(value) is None:
        raise ValueError(f"invalid {what}: {value!r} is not a plain file name")
    return value


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` through a sibling temp file and an atomic replace.

    The temp file lives in the *same* directory as the target (a cross-volume replace
    would not be atomic), is flushed and ``fsync``-ed before the replace, and is removed
    again if anything fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{TEMP_PREFIX}{path.name}{TEMP_SUFFIX}")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    except OSError:
        temp.unlink(missing_ok=True)
        raise
