"""Dependency assembly — the only place allowed to construct concrete adapters."""

from __future__ import annotations

import uuid
from pathlib import Path

from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.load_document.service import load_document as _load_document
from mcwr.application.features.parse_document.ports import BlockParser, MarkdownReader
from mcwr.application.features.persist_layout.ports import LayoutStore
from mcwr.application.features.render_card.ports import WebCardRenderer
from mcwr.infrastructure.app_paths import app_data_dir
from mcwr.infrastructure.json_layout_store import JsonLayoutStore
from mcwr.infrastructure.markdown_it_adapter import MarkdownItBlockParser
from mcwr.infrastructure.markdown_reader import FileMarkdownReader


def build_reader() -> MarkdownReader:
    return FileMarkdownReader()


def build_parser() -> BlockParser:
    return MarkdownItBlockParser()


def load(path: Path) -> LoadedDocument:
    """Open ``path`` with the production adapters."""
    return _load_document(path, reader=build_reader(), parser=build_parser())


def load_with(path: Path, *, reader: MarkdownReader, parser: BlockParser) -> LoadedDocument:
    """Open ``path`` with injected adapters (tests, spikes, future GUI sessions)."""
    return _load_document(path, reader=reader, parser=parser)


def build_layout_store(root: Path | None = None) -> LayoutStore:
    """The production layout store, rooted in the application data directory."""
    return JsonLayoutStore(root if root is not None else app_data_dir())


def new_session_id() -> str:
    """One session id per process: layouts are never shared between windows (D15)."""
    return uuid.uuid4().hex


def new_window_uuid() -> str:
    """One window id per process, used for the window state file."""
    return uuid.uuid4().hex


def build_web_renderer() -> WebCardRenderer:
    """The offscreen KaTeX/Mermaid rasterizer (decision D14).

    Constructing it does not start the web engine: the first render does, and every
    failure degrades to ``None`` so cards fall back to their text form.
    """
    from mcwr.infrastructure.app_paths import assets_dir, cache_dir
    from mcwr.infrastructure.web_renderer import QtWebCardRenderer

    return QtWebCardRenderer(assets_dir(), cache_dir() / "web")
