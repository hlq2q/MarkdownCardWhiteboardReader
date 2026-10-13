"""Tests for the refresh slice: structure signature, matching and layout merge (FR-5)."""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest

from mcwr.application.features.build_card_tree.service import build_card_tree
from mcwr.application.features.refresh_document import (
    CardMapping,
    RefreshPlan,
    is_major_change,
    major_change_warnings,
    match_cards,
    merge_layouts,
    plan_refresh,
    structure_signature,
)
from mcwr.domain.enums import BlockKind, CardKind
from mcwr.domain.ids import normalize_text
from mcwr.domain.models import Block, Card, CardLayout, CardTree

PATH_HASH = "deadbeef0000"


# ---------------------------------------------------------------------------- helpers


def blk(
    index: int,
    kind: BlockKind,
    text: str,
    *,
    level: int | None = None,
    lang: str | None = None,
) -> Block:
    return Block(
        index=index,
        kind=kind,
        raw_text=text,
        text_normalized=normalize_text(text),
        level=level,
        lang=lang,
    )


def heading(index: int, text: str, level: int) -> Block:
    return blk(index, BlockKind.HEADING, text, level=level)


def para(index: int, text: str) -> Block:
    return blk(index, BlockKind.PARAGRAPH, text)


def code(index: int, text: str, lang: str = "python") -> Block:
    return blk(index, BlockKind.CODE, text, lang=lang)


def divider(index: int) -> Block:
    return blk(index, BlockKind.THEMATIC_BREAK, "---")


def build(blocks: list[Block]) -> CardTree:
    return build_card_tree(blocks, path_hash=PATH_HASH)


def titled(tree: CardTree, title: str) -> Card:
    matches = [card for card in tree.cards.values() if card.title == title]
    assert len(matches) == 1, f"expected exactly one card titled {title!r}, got {len(matches)}"
    return matches[0]


def card_under(
    tree: CardTree, path: tuple[str, ...], kind: CardKind, *, title: str | None = None
) -> Card:
    matches = [
        card
        for card in tree.cards.values()
        if card.heading_path == path
        and card.kind is kind
        and (title is None or card.title == title)
    ]
    assert len(matches) == 1, f"expected one {kind} under {path}, got {len(matches)}"
    return matches[0]


def laid_out(card: Card) -> CardLayout:
    """A layout with a visibly non-default rectangle, so a lost merge is unmistakable."""
    layout = CardLayout(card_id=card.card_id)
    layout.x = (card.block_index or 0) * 40.0 + 5.0
    layout.y = (card.block_index or 0) * 30.0 + 3.0
    layout.width = 320.0
    layout.height = 180.0
    layout.z = 7
    layout.collapsed = True
    layout.detached = True
    layout.manual_size = True
    return layout


def layouts_for(tree: CardTree) -> dict[str, CardLayout]:
    return {card_id: laid_out(card) for card_id, card in tree.cards.items()}


def assert_geometry(old: CardLayout, new: CardLayout) -> None:
    assert new.x == old.x
    assert new.y == old.y
    assert new.width == old.width
    assert new.height == old.height
    assert new.z == old.z
    assert new.collapsed == old.collapsed
    assert new.detached == old.detached
    assert new.manual_size == old.manual_size


def assert_partition(mapping: CardMapping, old_tree: CardTree, new_tree: CardTree) -> None:
    """Every new card exactly once in kept values + added; every old card in kept keys + removed."""
    covered_new = list(mapping.kept.values()) + list(mapping.added)
    assert len(covered_new) == len(set(covered_new))
    assert set(covered_new) == set(new_tree.cards)
    covered_old = list(mapping.kept) + list(mapping.removed)
    assert len(covered_old) == len(set(covered_old))
    assert set(covered_old) == set(old_tree.cards)


# ------------------------------------------------------------------- document fixtures

BASE = [heading(0, "Intro", 1), code(1, "answer = 1")]
EDITED = [heading(0, "Intro", 1), code(1, "answer = 2")]
EXTENDED = [heading(0, "Intro", 1), code(1, "answer = 1"), code(2, "extra = 3", lang="bash")]
DIVIDER_ADDED = [heading(0, "Intro", 1), code(1, "answer = 1"), divider(2), heading(3, "More", 2)]
DIVIDER_REMOVED = [heading(0, "Intro", 1), code(1, "answer = 1"), divider(2), heading(3, "More", 1)]
LEVELS_CHANGED = [heading(0, "Intro", 1), code(1, "answer = 1"), heading(2, "Extra", 3)]
RENAMED_HEADING = [heading(0, "Renamed", 1), code(1, "answer = 1")]
HEADING_INSERTED_FIRST = [heading(0, "Middle", 1), heading(1, "Intro", 2), code(2, "answer = 1")]
FIRST_SECTION_ONLY = [
    code(0, "lead = 0", lang="bash"),
    heading(1, "Intro", 1),
    code(2, "answer = 1"),
]
HEADING_REMOVED = [heading(0, "Intro", 1), heading(1, "Extra", 2), code(2, "answer = 1")]
CARD_REMOVED = [heading(0, "Intro", 1), code(1, "answer = 1"), code(2, "stays", lang="bash")]
CARD_ADDED_AMONG_SIBLINGS = [
    heading(0, "Intro", 1),
    code(1, "lead = 0", lang="bash"),
    code(2, "answer = 1"),
]
PARAGRAPHS_ONLY = [para(0, "Intro"), para(1, "same text")]
CODE_ONLY = [code(0, "same text")]


@dataclass(frozen=True)
class _Case:
    name: str
    old: CardTree
    new: CardTree


MAJOR_CASES = (
    _Case("divider added", build(BASE), build(DIVIDER_ADDED)),
    _Case("divider removed", build(DIVIDER_ADDED), build(DIVIDER_REMOVED)),
    _Case("heading level changed", build(BASE), build(LEVELS_CHANGED)),
    _Case("heading removed", build(HEADING_REMOVED), build(BASE)),
    _Case("card added at the top level", build(BASE), build(FIRST_SECTION_ONLY)),
)

NOT_MAJOR_CASES = (
    _Case("content edited", build(BASE), build(EDITED)),
    _Case("card added inside a heading", build(BASE), build(EXTENDED)),
    _Case("card removed", build(CARD_REMOVED), build(BASE)),
    _Case("card added among siblings", build(BASE), build(CARD_ADDED_AMONG_SIBLINGS)),
    _Case("heading renamed", build(BASE), build(RENAMED_HEADING)),
)


# --------------------------------------------------------------- structure signature


def test_signature_counts_top_cards_and_heading_levels_in_document_order() -> None:
    blocks = [
        heading(0, "A", 2),
        heading(1, "B", 3),
        divider(2),
        code(3, "x = 1"),
        heading(4, "C", 1),
    ]
    signature = structure_signature(build(blocks))
    assert signature.top_cards == 2
    assert signature.heading_levels == (2, 3, 1)
    assert signature.parts == (2, 2, 3, 1)
    assert signature.part_count == 5


def test_signature_ignores_body_text_and_card_count() -> None:
    before = build([heading(0, "A", 1), code(1, "x = 1")])
    after = build([heading(0, "A", 1), code(1, "x = 2"), code(2, "y = 3")])
    assert structure_signature(before) == structure_signature(after)


def test_signature_does_not_depend_on_the_dict_order_of_cards() -> None:
    tree = build(BASE)
    shuffled = CardTree(cards=dict(reversed(list(tree.cards.items()))), root_ids=tree.root_ids)
    assert structure_signature(shuffled) == structure_signature(tree)
    assert match_cards(tree, shuffled) == match_cards(tree, tree)


def test_signature_distinguishes_top_card_count_from_heading_count() -> None:
    one_top = build([heading(0, "A", 1)])
    two_tops = build([code(0, "lead = 0", lang="bash"), heading(1, "A", 1)])
    assert (
        structure_signature(one_top).heading_levels == structure_signature(two_tops).heading_levels
    )
    assert structure_signature(one_top).top_cards == 1
    assert structure_signature(two_tops).top_cards == 2
    assert structure_signature(one_top).parts != structure_signature(two_tops).parts


# --------------------------------------------------------------------- major verdict


@pytest.mark.parametrize("case", MAJOR_CASES, ids=lambda case: case.name)
def test_major_cases_are_reported_as_major(case: _Case) -> None:
    assert is_major_change(case.old, case.new) is True


@pytest.mark.parametrize("case", NOT_MAJOR_CASES, ids=lambda case: case.name)
def test_body_edits_and_card_changes_are_not_major(case: _Case) -> None:
    assert is_major_change(case.old, case.new) is False
    assert major_change_warnings(case.old, case.new) == ()


def test_major_warnings_name_the_changed_number_of_top_cards() -> None:
    old = build(BASE)
    new = build([code(0, "lead = 0", lang="bash"), divider(1), *BASE])
    assert structure_signature(new).top_cards == 2
    assert structure_signature(new).heading_levels == (1,)
    assert major_change_warnings(old, new) == (
        "Major structure change: the number of top-level cards changed from 1 to 2.",
    )


def test_major_warnings_name_the_changed_heading_level_sequence() -> None:
    old, new = build(BASE), build(LEVELS_CHANGED)
    assert major_change_warnings(old, new) == (
        "Major structure change: the sequence of heading levels changed from [1] to [1, 3].",
    )


def test_major_warnings_report_both_reasons() -> None:
    old = build(BASE)
    new = build([code(0, "lead = 0", lang="bash"), *DIVIDER_ADDED, heading(5, "Deep", 4)])
    warnings = major_change_warnings(old, new)
    assert len(warnings) == 2
    assert "top-level cards" in warnings[0]
    assert "heading levels" in warnings[1]


# -------------------------------------------------------------------------- matching


def test_content_only_edit_keeps_every_card_id_and_its_geometry() -> None:
    old, new = build(BASE), build(EDITED)
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    assert plan.mapping.added == ()
    assert plan.mapping.removed == ()
    assert set(plan.mapping.kept) == set(old.cards)
    assert all(old_id == new_id for old_id, new_id in plan.mapping.kept.items())
    assert set(plan.layouts) == set(new.cards)

    edited_old, edited_new = titled(old, "python"), titled(new, "python")
    assert edited_new.content_hash != edited_old.content_hash
    assert_geometry(old_layouts[edited_old.card_id], plan.layouts[edited_new.card_id])
    assert_partition(plan.mapping, old, new)


def test_collapsed_detached_and_manual_size_survive_a_non_major_refresh() -> None:
    old, new = build(BASE), build(EDITED)
    plan = plan_refresh(old, new, layouts_for(old))
    assert plan.layouts
    for layout in plan.layouts.values():
        assert layout.collapsed is True
        assert layout.detached is True
        assert layout.manual_size is True


def test_new_heading_plus_new_code_block_is_major_and_keeps_no_geometry() -> None:
    old, new = build(BASE), build(HEADING_INSERTED_FIRST)
    plan = plan_refresh(old, new, layouts_for(old))

    assert plan.major is True, "the new heading extends the heading level sequence"
    assert plan.layouts == {}, "a major change rebuilds the board from scratch"
    assert plan.warnings[0] == (
        "Major structure change: the sequence of heading levels changed from [1] to [1, 2]."
    )
    assert [new.cards[card_id].title for card_id in plan.mapping.added] == ["Middle"]
    intro_old, intro_new = titled(old, "Intro"), titled(new, "Intro")
    assert plan.mapping.kept[intro_old.card_id] == intro_new.card_id
    code_old, code_new = titled(old, "python"), titled(new, "python")
    assert code_old.card_id not in new.cards, "a new parent heading moved the card's key"
    assert plan.mapping.kept[code_old.card_id] == code_new.card_id, (
        "pass 2 relocates it by content hash instead"
    )
    assert len(plan.mapping.kept) == 2, "the whole old document is still accounted for"
    assert_partition(plan.mapping, old, new)


def test_new_card_gets_a_default_layout_and_a_note_while_positions_survive() -> None:
    old, new = build(BASE), build(EXTENDED)
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    assert len(plan.mapping.added) == 1
    added = new.cards[plan.mapping.added[0]]
    assert added.title == "bash"
    assert added.parent_id == titled(new, "Intro").card_id

    for old_id, new_id in plan.mapping.kept.items():
        assert_geometry(old_layouts[old_id], plan.layouts[new_id])

    fresh = plan.layouts[added.card_id]
    assert (fresh.x, fresh.y, fresh.width, fresh.height, fresh.z) == (0.0, 0.0, 0.0, 0.0, 0)
    assert fresh.collapsed is False
    assert fresh.detached is False
    assert fresh.manual_size is False
    assert any("new card" in warning for warning in plan.warnings)
    assert_partition(plan.mapping, old, new)


def test_renamed_heading_is_recovered_by_the_content_hash_fallback() -> None:
    old, new = build(BASE), build(RENAMED_HEADING)
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False, "a rename changes neither the section count nor the levels"
    old_code, new_code = titled(old, "python"), titled(new, "python")
    assert old_code.card_id not in new.cards
    assert plan.mapping.kept[old_code.card_id] == new_code.card_id
    assert_geometry(old_layouts[old_code.card_id], plan.layouts[new_code.card_id])

    assert titled(new, "Renamed").card_id in plan.mapping.added
    assert titled(old, "Intro").card_id in plan.mapping.removed
    assert titled(new, "Renamed").heading_path == ("Renamed",)
    assert_partition(plan.mapping, old, new)


def test_shifted_ordinal_of_a_heading_is_relocated_by_content_hash() -> None:
    old, new = build(BASE), build(HEADING_INSERTED_FIRST)
    old_intro, new_intro = titled(old, "Intro"), titled(new, "Intro")

    assert old_intro.card_id not in new.cards, "the inserted sibling shifted the ordinal"
    assert old_intro.content_hash == new_intro.content_hash
    mapping = match_cards(old, new)
    assert mapping.kept[old_intro.card_id] == new_intro.card_id
    assert [new.cards[card_id].title for card_id in mapping.added] == ["Middle"]
    assert_partition(mapping, old, new)


def test_relocated_twins_do_not_cross_match_across_paragraphs() -> None:
    """Two identical twin cards, one moved out of its paragraph: no geometry may be swapped.

    The moved card loses its ``stable_key`` (its ordinal and heading path both change), so it
    is relocated by ``(kind, content_hash)``; the free candidate closest to its own former
    position has to be claimed instead of its twin's.
    """
    old = build(
        [
            heading(0, "Alpha", 1),
            code(1, "same text", lang="python"),
            code(2, "same text", lang="bash"),
            heading(3, "Beta", 1),
        ]
    )
    new = build(
        [
            heading(0, "Alpha", 1),
            code(1, "same text", lang="python"),
            heading(2, "Beta", 1),
            code(3, "same text", lang="bash"),
        ]
    )
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    moved_old = card_under(old, ("Alpha",), CardKind.CODE, title="bash")
    moved_new = card_under(new, ("Beta",), CardKind.CODE, title="bash")
    assert moved_old.card_id not in new.cards, "the card left its paragraph"
    assert plan.mapping.kept[moved_old.card_id] == moved_new.card_id
    assert_geometry(old_layouts[moved_old.card_id], plan.layouts[moved_new.card_id])
    twin = card_under(old, ("Alpha",), CardKind.CODE, title="python")
    assert plan.mapping.kept[twin.card_id] == twin.card_id, (
        "the twin that stayed put keeps its key and must not inherit the other geometry"
    )
    assert_geometry(old_layouts[twin.card_id], plan.layouts[twin.card_id])
    assert_partition(plan.mapping, old, new)


def test_removed_card_does_not_leak_into_the_result() -> None:
    old = build([heading(0, "Intro", 1), code(1, "answer = 1"), code(2, "stays", lang="bash")])
    new = build([heading(0, "Intro", 1), code(1, "answer = 1")])
    gone = titled(old, "bash")
    plan = plan_refresh(old, new, layouts_for(old))

    assert plan.major is False, "removing a card does not change the heading structure"
    assert gone.card_id not in new.cards
    assert plan.mapping.removed == (gone.card_id,)
    assert gone.card_id not in plan.layouts
    assert gone.card_id not in set(plan.mapping.kept.values())
    assert set(plan.layouts) == set(new.cards)
    assert set(plan.mapping.kept) == {
        titled(old, "Intro").card_id,
        titled(old, "python").card_id,
    }, "only the cards whose keys survived are kept"
    assert any("no longer in the document" in warning for warning in plan.warnings)
    assert_partition(plan.mapping, old, new)


def test_a_card_replaced_in_place_is_an_edit_not_a_removal() -> None:
    """Card identity is structural (spec §2.4): new content in the same slot keeps the layout."""
    old = build([heading(0, "Intro", 1), code(1, "going away")])
    new = build(BASE)
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    kept_code = titled(old, "python")
    assert kept_code.content_hash != titled(new, "python").content_hash
    assert plan.mapping.removed == ()
    assert plan.mapping.kept[kept_code.card_id] == titled(new, "python").card_id
    assert_geometry(old_layouts[kept_code.card_id], plan.layouts[titled(new, "python").card_id])
    assert_partition(plan.mapping, old, new)


def test_removed_trailing_card_never_leaks_into_the_result() -> None:
    old = build(
        [
            heading(0, "Intro", 1),
            code(1, "answer = 1"),
            code(2, "going away", lang="bash"),
        ]
    )
    new = build(BASE)
    plan = plan_refresh(old, new, layouts_for(old))

    assert plan.major is False, "a pure removal can leave the level sequence untouched"
    assert structure_signature(old) == structure_signature(new)
    gone = titled(old, "bash")
    assert gone.card_id not in set(plan.mapping.kept.values())
    assert plan.mapping.removed == (gone.card_id,)
    assert gone.card_id not in plan.layouts
    assert set(plan.layouts) == set(new.cards)
    assert plan.mapping.kept[titled(old, "python").card_id] == titled(new, "python").card_id
    assert_partition(plan.mapping, old, new)


def test_removing_a_nested_heading_is_major_and_reports_the_level_sequence() -> None:
    old, new = build(HEADING_REMOVED), build(BASE)
    plan = plan_refresh(old, new, layouts_for(old))

    assert plan.major is True
    assert plan.layouts == {}
    assert plan.warnings[0] == (
        "Major structure change: the sequence of heading levels changed from [1, 2] to [1]."
    )
    assert titled(old, "Extra").card_id in plan.mapping.removed
    assert_partition(plan.mapping, old, new)


def test_removals_and_additions_are_both_reported() -> None:
    old, new = build(HEADING_REMOVED), build(EXTENDED)
    mapping = match_cards(old, new)
    assert [old.cards[card_id].title for card_id in mapping.removed] == ["Extra"]
    assert [new.cards[card_id].title for card_id in mapping.added] == ["bash"]
    assert_partition(mapping, old, new)


def test_identical_cards_relocate_by_document_order_without_cross_matching() -> None:
    blocks = [
        heading(0, "Left", 1),
        code(1, "shared = 1"),
        heading(2, "Right", 1),
        code(3, "shared = 1"),
    ]
    old = build(blocks)
    new = build([heading(0, "Renamed left", 1), *blocks[1:]])
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    assert len(old.cards) == len(new.cards) == 4
    assert len(plan.mapping.added) == 1
    assert len(plan.mapping.removed) == 1
    assert plan.mapping.added[0] == titled(new, "Renamed left").card_id
    assert plan.mapping.removed[0] == titled(old, "Left").card_id

    old_code, new_code = (
        card_under(old, ("Left",), CardKind.CODE),
        card_under(new, ("Renamed left",), CardKind.CODE),
    )
    assert plan.mapping.kept[old_code.card_id] == new_code.card_id
    assert_geometry(old_layouts[old_code.card_id], plan.layouts[new_code.card_id])
    right_code, new_right = (
        card_under(old, ("Right",), CardKind.CODE),
        card_under(new, ("Right",), CardKind.CODE),
    )
    assert plan.mapping.kept[right_code.card_id] == new_right.card_id
    assert_geometry(old_layouts[right_code.card_id], plan.layouts[new_right.card_id])
    assert_partition(plan.mapping, old, new)


def test_tied_candidates_prefer_the_closest_heading_path() -> None:
    old = build(
        [
            heading(0, "Alpha", 1),
            code(1, "shared = 1"),
            heading(2, "Beta", 1),
            code(3, "shared = 1"),
        ]
    )
    new = build(
        [
            heading(0, "Renamed alpha", 1),
            code(1, "shared = 1"),
            heading(2, "Beta", 1),
            code(3, "shared = 1"),
        ]
    )
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    alpha_old = card_under(old, ("Alpha",), CardKind.CODE)
    alpha_new = card_under(new, ("Renamed alpha",), CardKind.CODE)
    assert plan.mapping.kept[alpha_old.card_id] == alpha_new.card_id, (
        "the heading path distance must beat the document-order distance"
    )
    assert_geometry(old_layouts[alpha_old.card_id], plan.layouts[alpha_new.card_id])
    beta_old = card_under(old, ("Beta",), CardKind.CODE)
    beta_new = card_under(new, ("Beta",), CardKind.CODE)
    assert plan.mapping.kept[beta_old.card_id] == beta_new.card_id
    assert_geometry(old_layouts[beta_old.card_id], plan.layouts[beta_new.card_id])
    assert_partition(plan.mapping, old, new)


def test_heading_path_distance_beats_a_single_shared_name() -> None:
    """A card that kept its ancestor heading beats one that only shares its leaf name.

    For the old card under ``("Red", "Green", "Blue")`` the two free candidates are
    ``("Red", "Green", "Renamed blue")`` (shares two names, one rename) and
    ``("Renamed blue",)`` (shares one name): the symmetric difference alone cannot tell
    them apart, the depth difference decides.
    """
    old = build(
        [
            heading(0, "Red", 1),
            heading(1, "Green", 2),
            heading(2, "Blue", 3),
            code(3, "shared = 1"),
            heading(4, "Red", 1),
            heading(5, "Renamed blue", 3),
            code(6, "shared = 1"),
        ]
    )
    new = build(
        [
            heading(0, "Red", 1),
            heading(1, "Green", 2),
            heading(2, "Renamed blue", 3),
            code(3, "shared = 1"),
            heading(4, "Red", 1),
            heading(5, "Renamed blue", 3),
            code(6, "shared = 1"),
        ]
    )
    old_layouts = layouts_for(old)
    plan = plan_refresh(old, new, old_layouts)

    assert plan.major is False
    deep_old = card_under(old, ("Red", "Green", "Blue"), CardKind.CODE)
    deep_new = card_under(new, ("Red", "Green", "Renamed blue"), CardKind.CODE)
    assert deep_old.card_id not in new.cards
    assert plan.mapping.kept[deep_old.card_id] == deep_new.card_id, (
        "staying under the same ancestors is closer than a same-named shallower heading"
    )
    assert_geometry(old_layouts[deep_old.card_id], plan.layouts[deep_new.card_id])
    shallow_old = card_under(old, ("Red", "Renamed blue"), CardKind.CODE)
    shallow_new = card_under(new, ("Red", "Renamed blue"), CardKind.CODE)
    assert plan.mapping.kept[shallow_old.card_id] == shallow_new.card_id
    assert_geometry(old_layouts[shallow_old.card_id], plan.layouts[shallow_new.card_id])
    assert_partition(plan.mapping, old, new)


def test_mapping_is_a_partition_of_both_trees_in_every_case() -> None:
    for case in (*MAJOR_CASES, *NOT_MAJOR_CASES):
        assert_partition(match_cards(case.old, case.new), case.old, case.new)
        assert_partition(match_cards(case.new, case.old), case.new, case.old)
    unchanged = build(BASE)
    identity = match_cards(unchanged, unchanged)
    assert identity.added == ()
    assert identity.removed == ()
    assert all(old_id == new_id for old_id, new_id in identity.kept.items())


def test_matching_is_independent_of_card_insertion_order() -> None:
    old, new = build(BASE), build(HEADING_INSERTED_FIRST)
    baseline = match_cards(old, new)
    items = list(old.cards.items())
    random.Random(7).shuffle(items)
    shuffled_old = CardTree(cards=dict(items), root_ids=old.root_ids)
    assert match_cards(shuffled_old, new) == baseline


def test_content_hash_fallback_never_matches_across_card_kinds() -> None:
    """A deleted code card must not hand its layout to the paragraph-bearing section."""
    old = build(CODE_ONLY)
    new = build(PARAGRAPHS_ONLY)
    assert structure_signature(old) == structure_signature(new)

    mapping = match_cards(old, new)
    loose = titled(new, "text")
    assert mapping.added == (loose.card_id,), "a paragraph card must not inherit a code card's key"
    assert mapping.removed == (titled(old, "python").card_id,)
    assert_partition(mapping, old, new)


def test_a_content_derived_card_never_absorbs_a_deleted_card_layout() -> None:
    """With no container left, a card whose hash matches nothing is added, not paired."""
    old = build(CODE_ONLY)
    new = build([para(0, "different text")])
    loose = new.cards[new.root_ids[0]]

    mapping = match_cards(old, new)
    assert mapping.added == (loose.card_id,)
    assert mapping.removed == (titled(old, "python").card_id,)
    assert_partition(mapping, old, new)


def test_card_mapping_rejects_a_new_card_that_is_both_mapped_and_added() -> None:
    with pytest.raises(ValueError, match="both mapped and added"):
        CardMapping(kept={"a": "b"}, added=("b",), removed=())


def test_card_mapping_rejects_a_new_card_claimed_twice() -> None:
    with pytest.raises(ValueError, match="claimed twice"):
        CardMapping(kept={"a": "c", "b": "c"}, added=(), removed=())


# --------------------------------------------------------------------- merge + plan


def test_major_change_returns_an_empty_layout_dict_with_a_warning() -> None:
    old, new = build(BASE), build(FIRST_SECTION_ONLY)
    plan = plan_refresh(old, new, layouts_for(old))

    assert isinstance(plan, RefreshPlan)
    assert plan.major is True
    assert plan.layouts == {}, "a major change must never silently reuse the old geometry"
    assert plan.warnings[0] == (
        "Major structure change: the number of top-level cards changed from 1 to 2."
    )
    assert any("rebuilt from the new document" in warning for warning in plan.warnings)
    assert set(plan.mapping.kept.values()).isdisjoint(plan.mapping.added)
    assert_partition(plan.mapping, old, new)


def test_kept_card_without_a_stored_layout_gets_a_default_and_a_note() -> None:
    old, new = build(BASE), build(EDITED)
    first_id = next(iter(old.cards))
    layouts, notes = merge_layouts(
        {first_id: CardLayout(card_id=first_id)}, match_cards(old, new), new
    )

    assert set(layouts) == set(new.cards)
    assert any("no stored position" in note for note in notes)


def test_layouts_for_an_empty_document_are_empty_without_notes() -> None:
    old = build(BASE)
    empty = build([])
    layouts, notes = merge_layouts(layouts_for(old), match_cards(old, empty), empty)
    assert layouts == {}
    assert notes == ("2 card(s) are no longer in the document and were removed from the board.",)


def test_merge_layouts_refuses_a_mapping_that_misses_a_card() -> None:
    old, new = build(BASE), build(EDITED)
    mapping = match_cards(old, new)
    decoy = CardTree(cards={}, root_ids=())
    with pytest.raises(ValueError, match="does not partition the new tree"):
        merge_layouts(layouts_for(old), mapping, decoy)
