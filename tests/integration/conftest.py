"""Fixtures for the integration suite.

Every GUI/acceptance test opens windows, and a window with `renderer=None` lazily builds
the **real** WebEngine renderer. One renderer per process is the production design (each
window is its own process), so a test process that opens eleven windows used to create
eleven hidden WebEngine views: the body-render test then measured **200.7 s** for a cold
render that takes **17.2 s** alone (recorded in `ERRORS.md` E-016).

These tests do not exercise body rendering, so they get a null renderer. Body rendering
has its own module (`test_body_render.py`) that builds the real renderer directly — never
through `container.build_web_renderer`, which this fixture replaces.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class NullRenderer:
    """A renderer that never starts WebEngine and never returns an image."""

    last_error = "null renderer: body rendering is not exercised by this test"

    def render(
        self, *, kind: object, source: str, scale: float, theme: str = "light"
    ) -> Path | None:
        del kind, source, scale, theme
        return None


@pytest.fixture(autouse=True)
def no_webengine_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the container's renderer factory so no test window starts Chromium."""
    from mcwr import container

    monkeypatch.setattr(container, "build_web_renderer", lambda: NullRenderer())
