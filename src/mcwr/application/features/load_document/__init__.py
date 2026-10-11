"""Feature slice: load one Markdown file end to end (parse -> card tree)."""

from __future__ import annotations

from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.load_document.service import load_document

__all__ = ["LoadedDocument", "load_document"]
