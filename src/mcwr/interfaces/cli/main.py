"""Typer CLI entry point — the first vertical slice, runnable without any GUI."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from mcwr import container
from mcwr.domain.errors import McwrError
from mcwr.interfaces.cli.views import render_outline, tree_to_dict

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Markdown Card Whiteboard Reader — read-only CLI tools.",
)


class OutputFormat(StrEnum):
    """How ``mcwr cards`` prints the card tree."""

    OUTLINE = "outline"
    JSON = "json"


@app.command()
def version() -> None:
    """Print the application version."""
    from mcwr import __version__

    typer.echo(f"mcwr {__version__}")


@app.command()
def cards(
    path: Annotated[Path, typer.Argument(help="Markdown file to inspect (read-only).")],
    output: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="outline or json.")
    ] = OutputFormat.OUTLINE,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Hide warnings.")] = False,
) -> None:
    """Parse a Markdown file and print its card tree."""
    try:
        loaded = container.load(path)
    except McwrError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if output is OutputFormat.JSON:
        typer.echo(json.dumps(tree_to_dict(loaded), ensure_ascii=False, indent=2))
    else:
        typer.echo(render_outline(loaded))

    if not quiet:
        for warning in loaded.warnings:
            typer.echo(f"warning: {warning}", err=True)


@app.command()
def gui(
    path: Annotated[
        Path | None, typer.Argument(help="Markdown file to open (optional, read-only).")
    ] = None,
) -> None:
    """Open the whiteboard window (one window per process)."""
    from mcwr.interfaces.gui.app import run

    raise typer.Exit(code=run(path))


def main() -> None:
    """Console-script entry point (``mcwr``)."""
    app()


if __name__ == "__main__":
    main()
