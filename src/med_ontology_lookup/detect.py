"""Detect whether a query is a free-text term, ontology code, or UMLS CUI."""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class InputKind(str, Enum):
    TERM = "term"
    CODE = "code"
    CUI = "cui"


class DetectedInput(NamedTuple):
    kind: InputKind
    value: str
    """Normalized value (e.g. uppercase CUI)."""
    ontology_hint: str | None
    """Best-guess ontology acronym when a code pattern implies one."""


# UMLS Concept Unique Identifier: C followed by 7+ digits
_CUI_RE = re.compile(r"^C\d{7,}$", re.IGNORECASE)

# RadLex IDs: RID + digits (sometimes with suffix letters)
_RADLEX_RE = re.compile(r"^RID\d+[A-Z0-9]*$", re.IGNORECASE)

# FMA IDs often appear as FMA:12345 or fma_12345 or pure digits in FMA context;
# prefer explicit prefix forms for auto-detect.
_FMA_PREFIX_RE = re.compile(r"^FMA[:_]?(\d+)$", re.IGNORECASE)

# SNOMED CT concept IDs are 6–18 digit integers (not starting with 0 in practice)
_SNOMED_CODE_RE = re.compile(r"^\d{6,18}$")

# LOINC: digit-leading codes like 8867-4 (1–7 digits, hyphen, 1–2 digits)
_LOINC_RE = re.compile(r"^\d{1,7}-\d{1,2}$")

# Generic compact codes (letter-leading): RID-style already handled; CPT/ICD-like
_LETTER_COMPACT_CODE_RE = re.compile(r"^[A-Z]{1,10}[:_\-.]?\d+[A-Z0-9.\-]*$", re.IGNORECASE)

# Digit-leading compact codes with an internal separator (not pure integers)
# e.g. 8867-4, 12345.6 — pure digit strings are handled as SNOMED above
_DIGIT_COMPACT_CODE_RE = re.compile(r"^\d+[A-Z0-9]*[.\-][A-Z0-9.\-]+$", re.IGNORECASE)


def detect_input(query: str) -> DetectedInput:
    """Classify *query* as free text, a source code, or a UMLS CUI.

    Heuristics are intentionally conservative: ambiguous strings stay terms
    so search still works.
    """
    raw = query.strip()
    if not raw:
        return DetectedInput(InputKind.TERM, raw, None)

    # Multi-word → almost always free text
    if any(c.isspace() for c in raw):
        return DetectedInput(InputKind.TERM, raw, None)

    if _CUI_RE.match(raw):
        return DetectedInput(InputKind.CUI, raw.upper(), "UMLS")

    if _RADLEX_RE.match(raw):
        return DetectedInput(
            InputKind.CODE, raw.upper() if raw.upper().startswith("RID") else raw, "RADLEX"
        )

    fma = _FMA_PREFIX_RE.match(raw)
    if fma:
        return DetectedInput(InputKind.CODE, fma.group(1), "FMA")

    if _LOINC_RE.match(raw):
        return DetectedInput(InputKind.CODE, raw, "LOINC")

    if _SNOMED_CODE_RE.match(raw):
        return DetectedInput(InputKind.CODE, raw, "SNOMEDCT")

    if _LETTER_COMPACT_CODE_RE.match(raw) and not raw.isalpha():
        return DetectedInput(InputKind.CODE, raw, None)

    if _DIGIT_COMPACT_CODE_RE.match(raw):
        return DetectedInput(InputKind.CODE, raw, None)

    return DetectedInput(InputKind.TERM, raw, None)
