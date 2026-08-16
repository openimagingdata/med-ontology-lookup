"""Semantic type name/TUI resolution tests."""

import pytest

from med_ontology_lookup.semantic_types import (
    display_semantic_types,
    hit_matches_types,
    list_shorthand_types,
    resolve_semantic_types,
)


def test_tui_passthrough_still_works_internally():
    assert resolve_semantic_types(["T047", "t033"]) == ["T047", "T033"]


def test_official_name():
    assert resolve_semantic_types(["Disease or Syndrome"]) == ["T047"]


def test_aliases():
    assert resolve_semantic_types(["disease"]) == ["T047"]
    assert resolve_semantic_types(["finding"]) == ["T033"]
    assert resolve_semantic_types(["anatomy"]) == ["T023"]
    assert resolve_semantic_types(["procedure"]) == ["T061"]


def test_mixed_list_dedupes():
    assert resolve_semantic_types(["disease", "T047", "Finding"]) == ["T047", "T033"]


def test_unknown_raises():
    with pytest.raises(ValueError, match="Unknown semantic type"):
        resolve_semantic_types(["not-a-real-type-xyz"])


def test_none_and_empty():
    assert resolve_semantic_types(None) is None
    assert resolve_semantic_types([]) is None


def test_shorthand_table_has_no_t_codes_in_labels():
    rows = list_shorthand_types()
    assert rows
    primaries = {r[0] for r in rows}
    assert "disease" in primaries
    assert "finding" in primaries
    for primary, shorthands, name in rows:
        assert not primary.upper().startswith("T") or not primary[1:].isdigit()
        assert name
        assert primary in shorthands


def test_display_semantic_types_maps_tui_to_name():
    assert display_semantic_types(["T047"]) == "Disease or Syndrome"
    assert display_semantic_types(["Disease or Syndrome"]) == "Disease or Syndrome"
    assert display_semantic_types(["T047", "Disease or Syndrome"]) == "Disease or Syndrome"
    assert display_semantic_types([]) == ""
    assert display_semantic_types(["T047"], prefer="shorthand") == "disease"


def test_hit_matches_types_allow_empty():
    wanted = ["T047"]
    assert hit_matches_types([], wanted, strict=False) is True
    assert hit_matches_types(None, wanted, strict=False) is True
    assert hit_matches_types(["T047"], wanted, strict=False) is True
    assert hit_matches_types(["Disease or Syndrome"], wanted, strict=False) is True
    assert hit_matches_types(["T033"], wanted, strict=False) is False


def test_hit_matches_types_strict():
    wanted = ["T047"]
    assert hit_matches_types([], wanted, strict=True) is False
    assert hit_matches_types(["T047"], wanted, strict=True) is True
    assert hit_matches_types(["T033"], wanted, strict=True) is False
