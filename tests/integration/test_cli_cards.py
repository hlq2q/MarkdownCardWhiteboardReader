"""End-to-end slice: the CLI on a real Markdown file, with the read-only guarantee."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mcwr.interfaces.cli.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "spikes" / "samples" / "sample.md"
runner = CliRunner()


def output_of(result: object) -> str:
    """stdout plus stderr, tolerant of the click version running the CLI."""
    stdout = getattr(result, "output", "") or ""
    stderr = getattr(result, "stderr", "") or ""
    return stdout + stderr


def test_cards_json_runs_on_the_sample() -> None:
    result = runner.invoke(app, ["cards", str(SAMPLE), "--format", "json"])
    assert result.exit_code == 0, output_of(result)
    payload = json.loads(result.output)
    kinds = {card["kind"] for card in payload["cards"]}
    assert {"big_section", "heading", "code", "table", "mermaid", "math_block"} <= kinds
    assert payload["document"]["path_hash"]
    assert payload["cards"][0]["kind"] == "big_section"


def test_cards_outline_lists_sections_and_warnings() -> None:
    result = runner.invoke(app, ["cards", str(SAMPLE)])
    assert result.exit_code == 0, output_of(result)
    assert "[big_section] Section 1" in result.output
    assert "[mermaid]" in result.output


def test_missing_file_exits_with_an_error() -> None:
    result = runner.invoke(app, ["cards", str(REPO_ROOT / "does-not-exist.md")])
    assert result.exit_code == 1
    assert "error:" in output_of(result)


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.startswith("mcwr ")


def test_loading_never_touches_the_source_directory() -> None:
    """FR-8.2 acceptance: the app must not write next to the source Markdown."""
    before_listing = sorted(entry.name for entry in SAMPLE.parent.iterdir())
    before = SAMPLE.stat()
    runner.invoke(app, ["cards", str(SAMPLE), "--format", "json"])
    after = SAMPLE.stat()
    assert before_listing == sorted(entry.name for entry in SAMPLE.parent.iterdir())
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)
