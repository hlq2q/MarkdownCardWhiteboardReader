"""Tests for the palette and the theme resolution (T-024 acceptance ②/③, D-021/D-030).

These assertions are the spec's own constraints expressed as code: every slot of
``docs/visual-spec.md`` §1 exists, the light theme has no pure white, the dark theme no pure
black, and the computed WCAG ratios still clear the thresholds the spec records. A palette
edit that breaks any of them fails here rather than in a screenshot nobody re-reads.
"""

from __future__ import annotations

from mcwr.domain.enums import CardKind
from mcwr.interfaces.gui.theme import (
    DARK,
    FONT_PX,
    LEVEL_BAR_TIERS,
    LEVEL_BAR_WIDTH,
    LIGHT,
    PALETTES,
    Theme,
    ThemeMode,
    card_fill,
    level_bar_colour,
    palette_for,
    points,
    resolve_theme,
    uses_shadow,
)
from mcwr.shared.contrast import MIN_RATIO_AA, MIN_RATIO_NON_TEXT, contrast_ratio

SLOTS = (
    "app_bg",
    "board_bg",
    "big_card_bg",
    "heading_card_bg",
    "card_bg",
    "code_bg",
    "table_bg",
    "text_primary",
    "text_secondary",
    "link",
    "card_edge",
    "border",
    "divider",
    "selected",
    "hover",
    "drag",
    "error_text",
    "error_bg",
)

TEXT_SLOTS = (
    "big_card_bg",
    "heading_card_bg",
    "card_bg",
    "code_bg",
    "table_bg",
)


def test_both_palettes_carry_every_semantic_slot() -> None:
    for palette in PALETTES.values():
        for slot in SLOTS:
            value = getattr(palette, slot)
            assert isinstance(value, str)
            assert len(value) == 7 and value.startswith("#"), (slot, value)
            assert value[1:] == value[1:].upper()


def test_the_light_theme_has_no_pure_white_and_the_dark_theme_no_pure_black() -> None:
    assert all(getattr(LIGHT, slot).upper() != "#FFFFFF" for slot in SLOTS)
    assert all(getattr(DARK, slot).upper() != "#000000" for slot in SLOTS)


def test_body_text_clears_wcag_aa_on_every_content_background() -> None:
    for palette in PALETTES.values():
        for slot in TEXT_SLOTS:
            ratio = contrast_ratio(palette.text_primary, getattr(palette, slot))
            assert ratio >= MIN_RATIO_AA, (palette.theme, slot, round(ratio, 2))


def test_secondary_text_links_and_errors_clear_wcag_aa() -> None:
    for palette in PALETTES.values():
        assert contrast_ratio(palette.text_secondary, palette.card_bg) >= MIN_RATIO_AA
        assert contrast_ratio(palette.link, palette.card_bg) >= MIN_RATIO_AA
        assert contrast_ratio(palette.link, palette.code_bg) >= MIN_RATIO_AA
        assert contrast_ratio(palette.error_text, palette.error_bg) >= MIN_RATIO_AA


def test_the_card_edge_and_the_selection_stay_recognisable_at_three_to_one() -> None:
    """"Clear but not harsh" (D-021) has a number: the edge clears 3:1, the fill only 1.2:1."""
    for palette in PALETTES.values():
        assert contrast_ratio(palette.card_edge, palette.card_bg) >= MIN_RATIO_NON_TEXT
        assert contrast_ratio(palette.selected, palette.card_bg) >= MIN_RATIO_NON_TEXT
        assert contrast_ratio(palette.card_bg, palette.board_bg) >= 1.2


def test_the_documented_ratios_are_the_computed_ones() -> None:
    """Pins the numbers ``docs/visual-spec.md`` §1.1 publishes, to two decimals."""
    published = {
        (Theme.LIGHT, "card_bg"): 14.79,
        (Theme.LIGHT, "code_bg"): 13.62,
        (Theme.DARK, "card_bg"): 11.02,
        (Theme.DARK, "code_bg"): 12.78,
        (Theme.LIGHT, "edge"): 3.69,
        (Theme.DARK, "edge"): 3.71,
    }
    for (theme, slot), expected in published.items():
        palette = palette_for(theme)
        background = palette.card_bg if slot in {"card_bg", "edge"} else palette.code_bg
        foreground = palette.card_edge if slot == "edge" else palette.text_primary
        assert round(contrast_ratio(foreground, background), 2) == expected


def test_follow_the_system_resolves_both_ways() -> None:
    assert resolve_theme(ThemeMode.SYSTEM, system_dark=False) is Theme.LIGHT
    assert resolve_theme(ThemeMode.SYSTEM, system_dark=True) is Theme.DARK
    assert resolve_theme(ThemeMode.LIGHT, system_dark=True) is Theme.LIGHT
    assert resolve_theme(ThemeMode.DARK, system_dark=False) is Theme.DARK


def test_card_fill_follows_the_spec_per_kind() -> None:
    for palette in PALETTES.values():
        assert card_fill(palette, CardKind.BIG_SECTION) == palette.big_card_bg
        assert card_fill(palette, CardKind.HEADING) == palette.heading_card_bg
        assert card_fill(palette, CardKind.CODE) == palette.code_bg
        assert card_fill(palette, CardKind.IMAGE) == palette.code_bg
        assert card_fill(palette, CardKind.TABLE) == palette.table_bg
        for kind in (CardKind.MATH_BLOCK, CardKind.MERMAID, CardKind.TASK_LIST, CardKind.TOC):
            assert card_fill(palette, kind) == palette.card_bg


def test_only_the_light_theme_draws_shadows() -> None:
    assert uses_shadow(Theme.LIGHT) is True
    assert uses_shadow(Theme.DARK) is False


def test_each_theme_pins_a_pygments_style() -> None:
    """T-029: the highlighter style is a palette slot, so it follows the theme."""
    assert LIGHT.pygments_style == "default"
    assert DARK.pygments_style == "monokai"


def test_the_depth_bar_uses_the_four_values_the_user_gave() -> None:
    """T-028 / visual spec §6.1: the values are pinned, not merely 'different'."""
    assert LIGHT.level_bar == ("#D0D7DE", "#AFB8C1", "#8C959F", "#6E7781")
    assert DARK.level_bar == ("#30363D", "#484F58", "#6E7681", "#8B949E")
    assert LIGHT.level_bar != DARK.level_bar
    for palette in (LIGHT, DARK):
        for tier in palette.level_bar:
            assert len(tier) == 7 and tier.startswith("#") and tier[1:] == tier[1:].upper()


def test_level_bar_colour_clamps_from_the_fourth_level_on() -> None:
    for palette in (LIGHT, DARK):
        assert level_bar_colour(palette, 0) == palette.level_bar[0]
        assert level_bar_colour(palette, 2) == palette.level_bar[2]
        assert level_bar_colour(palette, 3) == palette.level_bar[3]
        assert level_bar_colour(palette, 4) == palette.level_bar[3], "5th level reuses tier 4"
        assert level_bar_colour(palette, 99) == palette.level_bar[3]
        assert level_bar_colour(palette, -3) == palette.level_bar[0], "negative depth clamps"


def test_the_depth_bar_is_three_pixels_wide_and_has_four_tiers() -> None:
    assert LEVEL_BAR_WIDTH == 3.0
    assert LEVEL_BAR_TIERS == 4


def test_the_spec_pixel_sizes_convert_to_qt_points() -> None:
    assert points(FONT_PX["body"]) == 10.5
    assert points(FONT_PX["control"]) == 9.375
    assert points(0.0) == 0.0
