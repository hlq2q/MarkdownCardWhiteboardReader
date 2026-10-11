"""Spike 1: can markdown-it-py expose every block kind the card builder needs?

Run:  python -m uv run python spikes/spike_md_blocks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

SAMPLE_PATH = Path(__file__).parent / "samples" / "sample.md"


def build_parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    md.use(dollarmath_plugin, allow_space=True)
    md.use(tasklists_plugin)
    return md


def describe(token: object, indent: str = "  ") -> str:
    attrs = getattr(token, "attrs", {}) or {}
    info = getattr(token, "info", "") or ""
    content = (getattr(token, "content", "") or "").replace("\n", "\\n")[:44]
    return (
        f"{indent}{getattr(token, 'type', '?'):<20} tag={getattr(token, 'tag', ''):<6} "
        f"nest={getattr(token, 'nesting', 0)} level={getattr(token, 'level', 0)} "
        f"map={getattr(token, 'map', None)} markup={getattr(token, 'markup', '')!r} "
        f"info={info!r} attrs={attrs} content={content!r}"
    )


def main() -> int:
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    tokens = build_parser().parse(text)
    print(f"# tokens={len(tokens)}  sample={SAMPLE_PATH.name}\n")
    for index, token in enumerate(tokens):
        print(f"{index:3d} {describe(token, indent='')}")
        for child in token.children or []:
            print(describe(child))

    print("\n# classification-relevant token types")
    kinds: dict[str, int] = {}
    for token in tokens:
        kinds[token.type] = kinds.get(token.type, 0) + 1
        for child in token.children or []:
            kinds[f"inline:{child.type}"] = kinds.get(f"inline:{child.type}", 0) + 1
    for name, count in sorted(kinds.items()):
        print(f"  {name:<24} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
