"""Typer CLI for medical ontology lookups."""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from med_ontology_lookup.errors import ProviderError, ProviderFailureError
from med_ontology_lookup.http_util import format_http_error, redact_secrets
from med_ontology_lookup.models import (
    Concept,
    CrosswalkResult,
    HierarchyNode,
    SearchResults,
)
from med_ontology_lookup.semantic_types import display_semantic_types, list_shorthand_types
from med_ontology_lookup.service import OntologyLookup

app = typer.Typer(
    name="molu",
    help="Medical ontology lookup (RadLex, SNOMED-CT, FMA, LOINC, UMLS).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


class BackendOpt(str, Enum):
    auto = "auto"
    bioportal = "bioportal"
    umls = "umls"
    both = "both"


def _print_types_table(*, output: OutputFormat = OutputFormat.table) -> None:
    """Show short-hand semantic types (no T-codes)."""
    rows = list_shorthand_types()
    if output == OutputFormat.json:
        _print_json(
            [
                {
                    "primary": primary,
                    "shorthands": shorthands,
                    "name": name,
                }
                for primary, shorthands, name in rows
            ]
        )
        return

    table = Table(title="Semantic type short-hands (for -t / -T)")
    table.add_column("Short-hands", style="cyan")
    table.add_column("Meaning")
    for _primary, shorthands, name in rows:
        table.add_row(", ".join(shorthands), name)
    console.print(table)
    console.print(
        "[dim]-t / --types keeps untyped hits; "
        "-T / --types-strict requires a matching type.\n"
        "Example: uv run molu search fever -t disease[/dim]"
    )


def _parse_list(value: str | None) -> list[str] | None:
    if value is None or value.strip() == "":
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def _print_json(model: Any) -> None:
    if hasattr(model, "model_dump"):
        payload = model.model_dump(mode="json")
    elif isinstance(model, list):
        payload = [m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in model]
    else:
        payload = model
    console.print_json(json.dumps(payload, indent=2, default=str))


def _print_search_table(results: SearchResults) -> None:
    table = Table(title=f"Search: {results.query}", show_lines=False)
    table.add_column("Code", style="cyan")
    table.add_column("Ontology")
    table.add_column("Label")
    table.add_column("Type", overflow="fold")
    table.add_column("Exact", justify="center")
    table.add_column("Backend")
    table.add_column("CUI")
    for hit in results.results:
        table.add_row(
            hit.code,
            hit.ontology,
            hit.pref_label,
            display_semantic_types(hit.semantic_types),
            "✓" if hit.exact_match else "",
            hit.backend.value,
            hit.cui or "",
        )
    console.print(table)
    if results.total_count is not None:
        console.print(f"[dim]{len(results.results)} shown (total≈{results.total_count})[/dim]")
    for warning in results.warnings:
        err_console.print(f"[yellow]Warning:[/yellow] {warning}")


def _print_concept(concept: Concept) -> None:
    table = Table(title=f"{concept.ontology}:{concept.code}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Label", concept.pref_label)
    table.add_row("ID", concept.concept_id)
    table.add_row("Ontology", concept.ontology)
    table.add_row("Backend", concept.backend.value)
    if concept.definition:
        table.add_row("Definition", concept.definition)
    if concept.synonyms:
        table.add_row("Synonyms", "; ".join(concept.synonyms[:12]))
    if concept.semantic_types:
        table.add_row("Semantic types", display_semantic_types(concept.semantic_types))
    if concept.cuis:
        table.add_row("CUIs", ", ".join(concept.cuis))
    if concept.ui_link:
        table.add_row("UI", concept.ui_link)
    if concept.obsolete is not None:
        table.add_row("Obsolete", str(concept.obsolete))
    console.print(table)


def _print_crosswalk(result: CrosswalkResult) -> None:
    console.print(
        f"[bold]{result.preferred_name or result.query}[/bold]  "
        f"CUI={result.cui or '—'}  "
        f"types={', '.join(result.semantic_types) or '—'}"
    )
    table = Table(title="Source codes")
    table.add_column("Source", style="cyan")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("TTY")
    for sc in result.source_codes:
        table.add_row(sc.source, sc.code, sc.name, sc.term_type or "")
    console.print(table)
    if not result.source_codes:
        console.print("[yellow]No source codes found.[/yellow]")


def _print_hierarchy(nodes: list[HierarchyNode], title: str) -> None:
    table = Table(title=title)
    table.add_column("Code", style="cyan")
    table.add_column("Ontology")
    table.add_column("Label")
    for n in nodes:
        table.add_row(n.code, n.ontology, n.pref_label)
    console.print(table)
    if not nodes:
        console.print("[yellow]No nodes returned.[/yellow]")


def _handle_errors(
    exc: BaseException,
    *,
    output: OutputFormat = OutputFormat.table,
) -> None:
    if isinstance(exc, ProviderFailureError):
        if output == OutputFormat.json:
            payload = {
                "error": {
                    "code": "provider_failure",
                    "message": str(exc),
                    "failures": [failure.model_dump(mode="json") for failure in exc.failures],
                }
            }
            err_console.print_json(json.dumps(payload))
        elif isinstance(exc, ProviderError):
            err_console.print(f"[red]Provider error:[/red] {exc}")
        else:
            err_console.print(f"[red]Provider errors:[/red] {exc}")
            for failure in exc.failures:
                err_console.print(f"[dim]{failure.summary()}[/dim]")
        raise typer.Exit(code=1) from None
    if isinstance(exc, ValueError):
        err_console.print(f"[red]Error:[/red] {redact_secrets(str(exc))}")
        raise typer.Exit(code=2) from None
    response = getattr(exc, "response", None)
    if response is not None:
        err_console.print(f"[red]HTTP {format_http_error(exc)}[/red]")
        raise typer.Exit(code=1) from None
    err_console.print(f"[red]{type(exc).__name__}[/red]")
    raise typer.Exit(code=1) from None


@app.command("search", rich_help_panel="Lookups")
def search_cmd(
    query: Annotated[
        str | None,
        typer.Argument(help="Free-text term or phrase (not required with --print-types)"),
    ] = None,
    ontologies: Annotated[
        str | None,
        typer.Option(
            "--ontologies",
            "-o",
            help="Comma-separated ontology acronyms (default: RADLEX,SNOMEDCT,FMA,LOINC)",
        ),
    ] = None,
    backend: Annotated[BackendOpt, typer.Option("--backend", "-b")] = BackendOpt.auto,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=200)] = 25,
    exact: Annotated[bool, typer.Option("--exact", help="Require exact match")] = False,
    types: Annotated[
        str | None,
        typer.Option(
            "--types",
            "-t",
            help=(
                "Filter by semantic type short-hand (comma-separated), "
                "e.g. disease, finding, anatomy. Keeps hits with no type "
                "(common for RadLex). List short-hands: --print-types"
            ),
        ),
    ] = None,
    types_strict: Annotated[
        str | None,
        typer.Option(
            "--types-strict",
            "-T",
            help=(
                "Like --types, but drop hits with missing/empty types. "
                "Only results that match the given type(s) are kept."
            ),
        ),
    ] = None,
    # Backward-compatible alias for --types
    semantic_types: Annotated[str | None, typer.Option("--semantic-types", hidden=True)] = None,
    print_types: Annotated[
        bool,
        typer.Option("--print-types", help="Print a table of semantic type short-hands and exit"),
    ] = False,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """Search ontology terms across RadLex, SNOMED, FMA, LOINC, and UMLS."""
    if print_types:
        _print_types_table(output=output)
        return

    if not query:
        err_console.print(
            "[red]Error:[/red] Missing argument 'QUERY'. "
            "Or pass --print-types to list semantic type short-hands."
        )
        raise typer.Exit(code=2)

    if types and types_strict:
        err_console.print(
            "[red]Error:[/red] Use either -t/--types (allow untyped) "
            "or -T/--types-strict (require types), not both."
        )
        raise typer.Exit(code=2)

    type_filter = types or types_strict or semantic_types
    strict = types_strict is not None

    async def _go() -> SearchResults:
        async with OntologyLookup() as mol:
            return await mol.search(
                query,
                ontologies=_parse_list(ontologies),
                backend=backend.value,  # type: ignore[arg-type]
                limit=limit,
                exact=exact,
                semantic_types=_parse_list(type_filter),
                types_strict=strict,
            )

    try:
        results = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(results)
    else:
        _print_search_table(results)


@app.command("get")
def get_cmd(
    identifier: Annotated[str, typer.Argument(help="CUI, code, or class id")],
    ontology: Annotated[
        str | None,
        typer.Option(
            "--ontology", "-o", help="Ontology/source (required for non-CUI without hint)"
        ),
    ] = None,
    backend: Annotated[BackendOpt, typer.Option("--backend", "-b")] = BackendOpt.auto,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """Get a concept by CUI or source code."""

    async def _go() -> Concept:
        async with OntologyLookup() as mol:
            return await mol.get(
                identifier,
                ontology=ontology,
                backend=backend.value,  # type: ignore[arg-type]
            )

    try:
        concept = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(concept)
    else:
        _print_concept(concept)


@app.command("crosswalk")
def crosswalk_cmd(
    query: Annotated[str, typer.Argument(help="CUI, source code, or term")],
    from_source: Annotated[
        str | None,
        typer.Option("--from-source", help="Source SAB when query is a code (e.g. SNOMEDCT_US)"),
    ] = None,
    to_sources: Annotated[
        str | None,
        typer.Option(
            "--to-sources",
            help="Comma-separated target SABs (default: SNOMEDCT_US,FMA,RADLEX,LNC)",
        ),
    ] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """Map a concept to codes in other vocabularies (UMLS)."""

    async def _go() -> CrosswalkResult:
        async with OntologyLookup() as mol:
            return await mol.crosswalk(
                query,
                from_source=from_source,
                to_sources=_parse_list(to_sources),
            )

    try:
        result = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(result)
    else:
        _print_crosswalk(result)


@app.command("parents")
def parents_cmd(
    identifier: Annotated[str, typer.Argument()],
    ontology: Annotated[str, typer.Option("--ontology", "-o")],
    backend: Annotated[BackendOpt, typer.Option("--backend", "-b")] = BackendOpt.auto,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """List immediate parents of a concept."""

    async def _go() -> list[HierarchyNode]:
        async with OntologyLookup() as mol:
            return await mol.parents(
                identifier,
                ontology=ontology,
                backend=backend.value,  # type: ignore[arg-type]
            )

    try:
        nodes = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(nodes)
    else:
        _print_hierarchy(nodes, f"Parents of {ontology}:{identifier}")


@app.command("children")
def children_cmd(
    identifier: Annotated[str, typer.Argument()],
    ontology: Annotated[str, typer.Option("--ontology", "-o")],
    backend: Annotated[BackendOpt, typer.Option("--backend", "-b")] = BackendOpt.auto,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """List immediate children of a concept."""

    async def _go() -> list[HierarchyNode]:
        async with OntologyLookup() as mol:
            return await mol.children(
                identifier,
                ontology=ontology,
                backend=backend.value,  # type: ignore[arg-type]
            )

    try:
        nodes = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(nodes)
    else:
        _print_hierarchy(nodes, f"Children of {ontology}:{identifier}")


@app.command("lookup")
def lookup_cmd(
    query: Annotated[str, typer.Argument(help="Term, code, or CUI (auto-detected)")],
    ontologies: Annotated[str | None, typer.Option("--ontologies", "-o")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, max=200)] = 15,
    exact: Annotated[bool, typer.Option("--exact")] = False,
    output: Annotated[OutputFormat, typer.Option("--output", "-f")] = OutputFormat.table,
) -> None:
    """Smart lookup: auto-detect term vs code vs CUI."""

    async def _go() -> Any:
        async with OntologyLookup() as mol:
            return await mol.lookup(
                query,
                ontologies=_parse_list(ontologies),
                limit=limit,
                exact=exact,
            )

    try:
        result = _run(_go())
    except Exception as exc:  # noqa: BLE001
        _handle_errors(exc, output=output)
        return

    if output == OutputFormat.json:
        _print_json(result)
        return

    if isinstance(result, SearchResults):
        _print_search_table(result)
    elif isinstance(result, Concept):
        _print_concept(result)
    elif isinstance(result, CrosswalkResult):
        _print_crosswalk(result)
    else:
        console.print(result)


@app.command("version")
def version_cmd() -> None:
    """Print package version."""
    from med_ontology_lookup import __version__

    console.print(__version__)


def main() -> None:
    """Entry point for `python -m med_ontology_lookup`."""
    app()


if __name__ == "__main__":
    # Avoid noisy traceback on BrokenPipe when piping to head
    try:
        app()
    except BrokenPipeError:
        sys.exit(0)
