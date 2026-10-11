"""Read-only file access: encoding detection and newline bookkeeping (FR-1.6, FR-8)."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.parse_document.models import SourceText
from mcwr.domain.errors import DocumentDecodeError, DocumentMissingError

_CANDIDATES: tuple[str, ...] = ("utf-8-sig", "utf-8", "gbk", "cp1252")
_UTF8_BOM: bytes = b"\xef\xbb\xbf"


class FileMarkdownReader:
    """Decodes Markdown bytes without ever opening the file for writing."""

    def __init__(self, candidates: tuple[str, ...] = _CANDIDATES) -> None:
        self._candidates = candidates

    def read(self, path: Path) -> SourceText:
        """Return the decoded text of ``path``.

        Raises:
            DocumentMissingError: the path is not a readable file.
            DocumentDecodeError: no candidate codec could decode the bytes.
        """
        if path.is_dir():
            raise DocumentMissingError(f"{path} is a directory, not a Markdown file")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise DocumentMissingError(f"cannot read {path}: {exc}") from exc

        text, encoding, warning = _decode(raw, self._candidates, path)
        stat = path.stat()
        warnings = (warning,) if warning else ()
        return SourceText(
            text=text,
            encoding=encoding,
            newline=_detect_newline(text),
            size=stat.st_size,
            mtime=stat.st_mtime,
            warnings=warnings,
        )


def _decode(raw: bytes, candidates: tuple[str, ...], path: Path) -> tuple[str, str, str]:
    """Decode bytes, labelling BOM-prefixed UTF-8 distinctly from plain UTF-8.

    Last resort: decode with replacement characters rather than refusing to open the
    file (FR-1.6 / NFR-4 — a bad encoding degrades to a readable plain-text card with a
    warning, it never blocks the window).
    """
    if raw.startswith(_UTF8_BOM):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig", ""
        except UnicodeDecodeError:  # pragma: no cover - a BOM followed by invalid bytes
            pass
    for encoding in candidates:
        if encoding == "utf-8-sig":  # only meaningful when a BOM is present
            continue
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        warning = "" if encoding == "utf-8" else f"decoded as {encoding} (not UTF-8)"
        return text, encoding, warning
    if not candidates:
        raise DocumentDecodeError(str(path), candidates)
    fallback = candidates[0]
    warning = f"decoded as {fallback} with replacement characters; the file is not valid text"
    return raw.decode(fallback, errors="replace"), fallback, warning


def _detect_newline(text: str) -> str:
    """Dominant newline sequence, used only for reporting (parsing normalises anyway)."""
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"
