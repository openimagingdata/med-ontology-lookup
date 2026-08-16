"""Tests for input detection heuristics."""

from med_ontology_lookup.detect import InputKind, detect_input


def test_cui():
    d = detect_input("C0009044")
    assert d.kind == InputKind.CUI
    assert d.value == "C0009044"
    assert d.ontology_hint == "UMLS"


def test_cui_lowercase():
    d = detect_input("c0016644")
    assert d.kind == InputKind.CUI
    assert d.value == "C0016644"


def test_radlex():
    d = detect_input("RID43255")
    assert d.kind == InputKind.CODE
    assert d.ontology_hint == "RADLEX"


def test_fma_prefix():
    d = detect_input("FMA:7088")
    assert d.kind == InputKind.CODE
    assert d.value == "7088"
    assert d.ontology_hint == "FMA"


def test_snomed_numeric():
    d = detect_input("9468002")
    assert d.kind == InputKind.CODE
    assert d.ontology_hint == "SNOMEDCT"


def test_loinc_digit_leading():
    d = detect_input("8867-4")
    assert d.kind == InputKind.CODE
    assert d.value == "8867-4"
    assert d.ontology_hint == "LOINC"


def test_digit_compact_code():
    d = detect_input("12345-67")
    assert d.kind == InputKind.CODE


def test_free_text_phrase():
    d = detect_input("ground glass opacity")
    assert d.kind == InputKind.TERM
    assert d.ontology_hint is None


def test_single_word_term():
    d = detect_input("pneumothorax")
    assert d.kind == InputKind.TERM


def test_empty():
    d = detect_input("  ")
    assert d.kind == InputKind.TERM
