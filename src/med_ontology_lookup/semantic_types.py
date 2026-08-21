"""UMLS semantic type names and TUI resolution for human-friendly filters.

BioPortal expects TUIs (e.g. T047). UMLS accepts TUIs, tree-number prefixes,
or full semantic type names. Callers should pass readable names; we normalize.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Core UMLS semantic types (TUI → preferred name). Not every type in the network,
# but the ones people actually filter medical lookups by.
SEMANTIC_TYPES: dict[str, str] = {
    "T005": "Virus",
    "T007": "Bacterium",
    "T017": "Anatomical Structure",
    "T018": "Embryonic Structure",
    "T019": "Congenital Abnormality",
    "T020": "Acquired Abnormality",
    "T021": "Fully Formed Anatomical Structure",
    "T022": "Body System",
    "T023": "Body Part, Organ, or Organ Component",
    "T024": "Tissue",
    "T025": "Cell",
    "T026": "Cell Component",
    "T028": "Gene or Genome",
    "T029": "Body Location or Region",
    "T030": "Body Space or Junction",
    "T031": "Body Substance",
    "T032": "Organism Attribute",
    "T033": "Finding",
    "T034": "Laboratory or Test Result",
    "T037": "Injury or Poisoning",
    "T038": "Biologic Function",
    "T039": "Physiologic Function",
    "T040": "Organism Function",
    "T041": "Mental Process",
    "T042": "Organ or Tissue Function",
    "T043": "Cell Function",
    "T044": "Molecular Function",
    "T045": "Genetic Function",
    "T046": "Pathologic Function",
    "T047": "Disease or Syndrome",
    "T048": "Mental or Behavioral Dysfunction",
    "T049": "Cell or Molecular Dysfunction",
    "T050": "Experimental Model of Disease",
    "T051": "Event",
    "T052": "Activity",
    "T053": "Behavior",
    "T054": "Social Behavior",
    "T055": "Individual Behavior",
    "T056": "Daily or Recreational Activity",
    "T057": "Occupational Activity",
    "T058": "Health Care Activity",
    "T059": "Laboratory Procedure",
    "T060": "Diagnostic Procedure",
    "T061": "Therapeutic or Preventive Procedure",
    "T062": "Research Activity",
    "T063": "Molecular Biology Research Technique",
    "T064": "Governmental or Regulatory Activity",
    "T065": "Educational Activity",
    "T066": "Machine Activity",
    "T067": "Phenomenon or Process",
    "T068": "Human-caused Phenomenon or Process",
    "T069": "Environmental Effect of Humans",
    "T070": "Natural Phenomenon or Process",
    "T074": "Medical Device",
    "T075": "Research Device",
    "T077": "Conceptual Entity",
    "T078": "Idea or Concept",
    "T079": "Temporal Concept",
    "T080": "Qualitative Concept",
    "T081": "Quantitative Concept",
    "T082": "Spatial Concept",
    "T083": "Geographic Area",
    "T085": "Molecular Sequence",
    "T086": "Nucleotide Sequence",
    "T087": "Amino Acid Sequence",
    "T088": "Carbohydrate Sequence",
    "T089": "Regulation or Law",
    "T090": "Occupation or Discipline",
    "T091": "Biomedical Occupation or Discipline",
    "T092": "Organization",
    "T093": "Health Care Related Organization",
    "T094": "Professional Society",
    "T095": "Self-help or Relief Organization",
    "T096": "Group",
    "T097": "Professional or Occupational Group",
    "T098": "Population Group",
    "T099": "Family Group",
    "T100": "Age Group",
    "T101": "Patient or Disabled Group",
    "T102": "Group Attribute",
    "T103": "Chemical",
    "T104": "Chemical Viewed Structurally",
    "T109": "Organic Chemical",
    "T114": "Nucleic Acid, Nucleoside, or Nucleotide",
    "T116": "Amino Acid, Peptide, or Protein",
    "T120": "Chemical Viewed Functionally",
    "T121": "Pharmacologic Substance",
    "T122": "Biomedical or Dental Material",
    "T123": "Biologically Active Substance",
    "T125": "Hormone",
    "T126": "Enzyme",
    "T127": "Vitamin",
    "T129": "Immunologic Factor",
    "T130": "Indicator, Reagent, or Diagnostic Aid",
    "T131": "Hazardous or Poisonous Substance",
    "T167": "Substance",
    "T168": "Food",
    "T169": "Functional Concept",
    "T170": "Intellectual Product",
    "T171": "Language",
    "T184": "Sign or Symptom",
    "T185": "Classification",
    "T190": "Anatomical Abnormality",
    "T191": "Neoplastic Process",
    "T192": "Receptor",
    "T194": "Antibiotic",
    "T196": "Element, Ion, or Isotope",
    "T197": "Inorganic Chemical",
    "T200": "Clinical Drug",
    "T201": "Clinical Attribute",
    "T203": "Drug Delivery Device",
    "T204": "Eukaryote",
}

# Short aliases users type instead of full names or TUIs.
_ALIASES: dict[str, str] = {
    "disease": "T047",
    "diseases": "T047",
    "disorder": "T047",
    "disorders": "T047",
    "syndrome": "T047",
    "dx": "T047",
    "finding": "T033",
    "findings": "T033",
    "sign": "T184",
    "symptom": "T184",
    "signs": "T184",
    "symptoms": "T184",
    "anatomy": "T023",
    "anatomical": "T023",
    "body part": "T023",
    "organ": "T023",
    "structure": "T017",
    "location": "T029",
    "region": "T029",
    "procedure": "T061",
    "procedures": "T061",
    "therapy": "T061",
    "therapeutic": "T061",
    "treatment": "T061",
    "diagnostic": "T060",
    "diagnosis procedure": "T060",
    "lab": "T059",
    "laboratory": "T059",
    "lab procedure": "T059",
    "lab result": "T034",
    "test result": "T034",
    "injury": "T037",
    "poisoning": "T037",
    "neoplasm": "T191",
    "cancer": "T191",
    "tumor": "T191",
    "drug": "T121",
    "drugs": "T121",
    "medication": "T121",
    "pharmacologic": "T121",
    "device": "T074",
    "medical device": "T074",
    "gene": "T028",
    "protein": "T116",
    "chemical": "T103",
    "abnormality": "T190",
    "congenital": "T019",
    "pathologic": "T046",
    "pathology": "T046",
}

_TUI_RE = re.compile(r"^T\d{3}$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _name_to_tui() -> dict[str, str]:
    """Map casefolded preferred name → TUI."""
    return {name.casefold(): tui for tui, name in SEMANTIC_TYPES.items()}


def list_semantic_types() -> list[tuple[str, str]]:
    """Return (TUI, name) pairs sorted by TUI (internal / API use)."""
    return sorted(SEMANTIC_TYPES.items(), key=lambda kv: kv[0])


def list_shorthand_types() -> list[tuple[str, list[str], str]]:
    """Return shorthand groups for user-facing display (no T-codes).

    Each row is ``(primary, all_shorthands, official_name)`` sorted by primary.
    """
    by_tui: dict[str, list[str]] = {}
    for alias, tui in _ALIASES.items():
        by_tui.setdefault(tui, []).append(alias)

    rows: list[tuple[str, list[str], str]] = []
    for tui, aliases in by_tui.items():
        aliases_sorted = sorted(aliases)
        # Prefer a readable single-word short-hand (disease over dx/disorders).
        primary = min(
            aliases_sorted,
            key=lambda a: (
                a.count(" "),  # single-word first
                0 if len(a) >= 4 else 1,  # avoid ultra-short abbrevs as primary
                len(a),
                a,
            ),
        )
        ordered = [primary] + [a for a in aliases_sorted if a != primary]
        rows.append((primary, ordered, SEMANTIC_TYPES.get(tui, "")))

    rows.sort(key=lambda r: r[0])
    return rows


@lru_cache(maxsize=1)
def _tui_to_primary_shorthand() -> dict[str, str]:
    """Map TUI → preferred short-hand when we have one."""
    out: dict[str, str] = {}
    by_tui: dict[str, list[str]] = {}
    for alias, tui in _ALIASES.items():
        by_tui.setdefault(tui, []).append(alias)
    for tui, aliases in by_tui.items():
        primary = min(
            aliases,
            key=lambda a: (
                a.count(" "),
                0 if len(a) >= 4 else 1,
                len(a),
                a,
            ),
        )
        out[tui] = primary
    return out


def normalize_type_token_to_tui(token: str) -> str | None:
    """Map a single type token (TUI, name, or short-hand) to a TUI, if possible."""
    token = token.strip()
    if not token:
        return None
    if _TUI_RE.match(token):
        return token.upper()
    key = token.casefold()
    if key in _ALIASES:
        return _ALIASES[key]
    return _name_to_tui().get(key)


def hit_matches_types(
    hit_types: list[str] | None,
    wanted_tuis: list[str] | set[str],
    *,
    strict: bool,
) -> bool:
    """Whether a hit should be kept under a type filter.

    *strict=False* (``-t`` / ``--types``): keep hits with a matching type **or**
    with no types at all (e.g. many RadLex classes).

    *strict=True* (``-T`` / ``--types-strict``): keep only hits that have at least
    one matching type; untyped hits are dropped.
    """
    wanted = {t.upper() for t in wanted_tuis}
    if not wanted:
        return True

    types = [str(t).strip() for t in (hit_types or []) if str(t).strip()]
    if not types:
        return not strict

    for token in types:
        tui = normalize_type_token_to_tui(token)
        if tui and tui in wanted:
            return True
        # raw TUI not in our catalog but matches wanted
        if _TUI_RE.match(token) and token.upper() in wanted:
            return True
    return False


def display_semantic_types(types: list[str] | None, *, prefer: str = "name") -> str:
    """Format semantic types for CLI tables.

    *prefer*:
      - ``name`` — official UMLS type names (default)
      - ``shorthand`` — short-hands when known, else name
    """
    if not types:
        return ""
    name_by_tui = SEMANTIC_TYPES
    shorthand_by_tui = _tui_to_primary_shorthand()
    parts: list[str] = []
    for raw in types:
        token = str(raw).strip()
        if not token:
            continue
        tui = token.upper() if _TUI_RE.match(token) else None
        if tui and tui in name_by_tui:
            if prefer == "shorthand" and tui in shorthand_by_tui:
                parts.append(shorthand_by_tui[tui])
            else:
                parts.append(name_by_tui[tui])
            continue
        # Already a name (UMLS search) — optionally map to shorthand
        if prefer == "shorthand":
            tui_from_name = _name_to_tui().get(token.casefold())
            if tui_from_name and tui_from_name in shorthand_by_tui:
                parts.append(shorthand_by_tui[tui_from_name])
                continue
        parts.append(token)
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return ", ".join(out)


def resolve_semantic_types(values: list[str] | None) -> list[str] | None:
    """Resolve user-facing semantic type tokens to BioPortal-friendly TUIs.

    Accepts:
      - TUIs: ``T047``, ``t047``
      - Official names: ``Disease or Syndrome``
      - Short aliases: ``disease``, ``anatomy``, ``finding``, ``procedure``

    Raises:
        ValueError: if any token cannot be resolved (message lists suggestions).
    """
    if not values:
        return None

    name_index = _name_to_tui()
    resolved: list[str] = []
    unknown: list[str] = []

    for raw in values:
        token = raw.strip()
        if not token:
            continue
        if _TUI_RE.match(token):
            tui = token.upper()
            if tui not in SEMANTIC_TYPES:
                # Still pass through unknown official-looking TUIs (network may grow)
                resolved.append(tui)
            else:
                resolved.append(tui)
            continue

        key = token.casefold()
        if key in _ALIASES:
            resolved.append(_ALIASES[key])
            continue
        if key in name_index:
            resolved.append(name_index[key])
            continue

        # Substring match on official names (e.g. "Disease" → Disease or Syndrome)
        partial = [
            (tui, name)
            for tui, name in SEMANTIC_TYPES.items()
            if key in name.casefold()
        ]
        if len(partial) == 1:
            resolved.append(partial[0][0])
            continue
        if len(partial) > 1:
            # Prefer exact word boundary-ish: shortest name containing the key
            partial.sort(key=lambda p: len(p[1]))
            # If alias-like uniqueness fails, error with options
            opts = ", ".join(f"{n} ({t})" for t, n in partial[:8])
            raise ValueError(
                f"Ambiguous semantic type {token!r}. Did you mean one of: {opts}?"
            )

        unknown.append(token)

    if unknown:
        # Suggest close names by simple prefix/containment
        suggestions: list[str] = []
        for u in unknown:
            uk = u.casefold()
            hits = [
                f"{name} ({tui})"
                for tui, name in SEMANTIC_TYPES.items()
                if uk[:4] in name.casefold() or name.casefold().startswith(uk[:3])
            ][:5]
            # Suggest short-hands, not T-codes
            short_hits = [
                primary
                for primary, _, name in list_shorthand_types()
                if uk[:4] in name.casefold() or primary.startswith(uk[:3])
            ][:5]
            if short_hits:
                suggestions.append(f"{u!r} → try {', '.join(short_hits)}")
            elif hits:
                # fall back to official names only
                name_only = [h.split(" (")[0] for h in hits]
                suggestions.append(f"{u!r} → try {', '.join(name_only)}")
            else:
                suggestions.append(
                    f"{u!r} (run `molu search --print-types` for short-hands)"
                )
        raise ValueError(
            "Unknown semantic type(s): "
            + "; ".join(suggestions)
            + ". Examples: disease, finding, anatomy, procedure."
        )

    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for tui in resolved:
        if tui not in seen:
            seen.add(tui)
            out.append(tui)
    return out
