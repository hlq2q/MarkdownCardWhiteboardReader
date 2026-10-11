"""Domain errors. Infrastructure translates low-level failures into these."""

from __future__ import annotations


class McwrError(Exception):
    """Base class for every error raised by this application."""


class DocumentMissingError(McwrError):
    """The Markdown file does not exist or cannot be read."""


class DocumentDecodeError(McwrError):
    """The file bytes cannot be decoded with any supported codec."""

    def __init__(self, path: str, tried: tuple[str, ...]) -> None:
        super().__init__(f"cannot decode {path!r}; tried: {', '.join(tried)}")
        self.path = path
        self.tried = tried


class ParseError(McwrError):
    """The block parser failed for a whole document (single blocks degrade instead)."""


class LayoutCorruptedError(McwrError):
    """A persisted layout snapshot is unreadable or fails validation."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"layout snapshot {path!r} is unusable: {reason}")
        self.path = path
        self.reason = reason


class TreeInvariantError(McwrError):
    """The card tree violates a domain invariant (a bug, never user input)."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("card tree invariant violated: " + "; ".join(problems))
        self.problems = problems
