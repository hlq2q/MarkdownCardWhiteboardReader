"""Feature slice: decide which cards need an offscreen web-rendered image (D14)."""

from __future__ import annotations

from mcwr.application.features.render_card.ports import WebCardRenderer
from mcwr.application.features.render_card.service import (
    WEB_RENDER_KINDS,
    card_image,
    needs_web_render,
    web_source,
)

__all__ = [
    "WEB_RENDER_KINDS",
    "WebCardRenderer",
    "card_image",
    "needs_web_render",
    "web_source",
]
