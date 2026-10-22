"""Read-only research workflow tools exposed over MCP stdio."""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from core import (
    check_gap_evidence_data,
    check_model_plan_data,
    count_group_cells_data,
    lookup_crossref_doi_data,
    profile_csv_variables_data,
    search_crossref_data,
    search_literature_data,
    search_openalex_data,
)


mcp = MCPServer("research-workflow-tools")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def search_openalex(query: str, limit: int = 10, page: int = 1) -> dict:
    """Search one OpenAlex page; return coverage metadata and unverified records."""
    return search_openalex_data(query, limit, page)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def search_crossref(query: str, limit: int = 10, page: int = 1) -> dict:
    """Search one Crossref page; return coverage metadata and unverified records."""
    return search_crossref_data(query, limit, page)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def search_literature(query: str, limit: int = 10, page: int = 1) -> dict:
    """Search both sources and deduplicate this page; never claim exhaustive coverage."""
    return search_literature_data(query, limit, page)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def lookup_crossref_doi(doi: str, expected_title: str = "") -> dict:
    """Check DOI metadata and flag a possible title mismatch for human review."""
    return lookup_crossref_doi_data(doi, expected_title)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def check_gap_evidence(gap_json: str) -> dict:
    """Check a candidate research gap's evidence fields, not the truth of its claims."""
    return check_gap_evidence_data(gap_json)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def profile_csv_variables(
    csv_path: str,
    columns: list[str],
    max_rows: int = 100000,
    missing_values: dict[str, list[str]] | None = None,
) -> dict:
    """Profile approved CSV columns; suppress low-frequency categories."""
    return profile_csv_variables_data(csv_path, columns, max_rows, missing_values)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def count_group_cells(
    csv_path: str,
    columns: list[str],
    max_rows: int = 100000,
    missing_values: dict[str, list[str]] | None = None,
) -> dict:
    """Count approved CSV group combinations with low-frequency suppression."""
    return count_group_cells_data(csv_path, columns, max_rows, missing_values)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def check_model_plan(plan_json: str) -> dict:
    """Check model-plan fields and obvious contradictions, never statistical validity."""
    return check_model_plan_data(plan_json)


if __name__ == "__main__":
    mcp.run()

