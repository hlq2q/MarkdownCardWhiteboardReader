"""Use case: open a Markdown file and produce its card tree."""

from __future__ import annotations

from pathlib import Path

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.load_document.models import LoadedDocument
from mcwr.application.features.parse_document.ports import BlockParser, MarkdownReader
from mcwr.application.features.parse_document.service import parse_document
from mcwr.domain.errors import TreeInvariantError
from mcwr.domain.invariants import required_block_indexes, tree_problems


def load_document(
    path: Path,
    *,
    reader: MarkdownReader,
    parser: BlockParser,
    check_invariants: bool = True,
) -> LoadedDocument:
    """Read ``path``, parse it and build the card tree.

    Raises:
        DocumentMissingError | DocumentDecodeError: the file cannot be read.
        TreeInvariantError: the builder produced an inconsistent tree (a bug; surfacing
            it here keeps a silent content loss from reaching the user).
    """
    parsed = parse_document(path, reader=reader, parser=parser)
    tree = build_card_tree(parsed.blocks, path_hash=parsed.document.path_hash)
    warnings = list(parsed.warnings)

    if check_invariants:
        problems = tree_problems(tree, required_indexes=required_block_indexes(parsed.blocks))
        if problems:
            raise TreeInvariantError(problems)

    return LoadedDocument(
        document=parsed.document,
        blocks=parsed.blocks,
        tree=tree,
        warnings=tuple(warnings),
    )
