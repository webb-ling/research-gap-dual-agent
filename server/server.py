"""Read-only scholarly metadata tools exposed over MCP stdio."""

from __future__ import annotations

import difflib
import csv
import json
import os
import re
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


mcp = MCPServer("research-workflow-tools")
USER_AGENT = "research-gap-dual-agent/1.0 (scholarly metadata; https://github.com/webb-ling/research-gap-dual-agent)"


def _fetch_json(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def _authors_from_openalex(work: dict) -> list[str]:
    return [entry.get("author", {}).get("display_name", "") for entry in work.get("authorships", [])[:8]]


def _authors_from_crossref(work: dict) -> list[str]:
    return [" ".join(filter(None, (a.get("given"), a.get("family")))) for a in work.get("author", [])[:8]]


def _year_from_crossref(work: dict) -> int | None:
    for key in ("published", "issued", "created"):
        parts = work.get(key, {}).get("date-parts", [])
        if parts and parts[0]:
            return parts[0][0]
    return None


def _request_error(source: str, error: Exception) -> dict:
    if isinstance(error, HTTPError):
        return {"ok": False, "source": source, "status": error.code, "error": "upstream_http_error"}
    if isinstance(error, URLError):
        return {"ok": False, "source": source, "error": "upstream_connection_error"}
    return {"ok": False, "source": source, "error": "unexpected_error"}


def search_openalex_data(query: str, limit: int = 10) -> dict:
    query = query.strip()
    if not query or len(query) > 500 or not 1 <= limit <= 25:
        return {"ok": False, "source": "OpenAlex", "error": "query must contain 1-500 characters and limit must be 1-25"}
    params = {"search": query, "per_page": limit}
    url = "https://api.openalex.org/works?" + urlencode(params)
    key = os.getenv("OPENALEX_API_KEY")
    headers_url = url  # Keep the returned query URL free of credentials.
    if key:
        url += "&" + urlencode({"api_key": key})
    try:
        data = _fetch_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return _request_error("OpenAlex", error)
    works = []
    for work in data.get("results", []):
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        works.append({
            "title": work.get("title"),
            "authors": _authors_from_openalex(work),
            "year": work.get("publication_year"),
            "doi": work.get("doi"),
            "openalex_url": work.get("id"),
            "venue": source.get("display_name"),
            "cited_by_count": work.get("cited_by_count"),
        })
    return {"ok": True, "source": "OpenAlex", "query_url": headers_url, "results": works}


def search_crossref_data(query: str, limit: int = 10) -> dict:
    query = query.strip()
    if not query or len(query) > 500 or not 1 <= limit <= 25:
        return {"ok": False, "source": "Crossref", "error": "query must contain 1-500 characters and limit must be 1-25"}
    params = {"query.bibliographic": query, "rows": limit}
    mailto = os.getenv("CROSSREF_MAILTO")
    if mailto:
        params["mailto"] = mailto
    url = "https://api.crossref.org/works?" + urlencode(params)
    try:
        data = _fetch_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return _request_error("Crossref", error)
    works = []
    for work in data.get("message", {}).get("items", []):
        doi = work.get("DOI")
        works.append({
            "title": (work.get("title") or [None])[0],
            "authors": _authors_from_crossref(work),
            "year": _year_from_crossref(work),
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}" if doi else None,
            "venue": (work.get("container-title") or [None])[0],
            "type": work.get("type"),
        })
    return {"ok": True, "source": "Crossref", "query_url": url, "results": works}


def lookup_crossref_doi_data(doi: str, expected_title: str = "") -> dict:
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)
    if not doi.startswith("10.") or "/" not in doi or len(doi) > 300:
        return {"ok": False, "source": "Crossref", "error": "invalid DOI format"}
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    try:
        work = _fetch_json(url).get("message", {})
    except HTTPError as error:
        if error.code == 404:
            return {"ok": True, "source": "Crossref", "status": "not_found_in_crossref", "doi": doi,
                    "note": "Crossref has no record for this DOI; this does not prove the DOI or paper is nonexistent."}
        return _request_error("Crossref", error)
    except (URLError, TimeoutError, ValueError) as error:
        return _request_error("Crossref", error)
    title = (work.get("title") or [None])[0]
    result = {
        "ok": True,
        "source": "Crossref",
        "status": "metadata_found",
        "doi": work.get("DOI", doi),
        "doi_url": f"https://doi.org/{doi}",
        "title": title,
        "authors": _authors_from_crossref(work),
        "year": _year_from_crossref(work),
        "venue": (work.get("container-title") or [None])[0],
        "type": work.get("type"),
        "publisher": work.get("publisher"),
        "publisher_url": work.get("URL"),
        "note": "Metadata confirms registration details, not the paper's methods, results, or research gap.",
    }
    if expected_title and title:
        normalize = lambda value: re.sub(r"[^\w]+", " ", value.lower()).strip()
        result["title_similarity"] = round(difflib.SequenceMatcher(None, normalize(expected_title), normalize(title)).ratio(), 3)
    return result


def _csv_request(csv_path: str, columns: list[str], max_rows: int, min_columns: int, max_columns: int) -> tuple[Path | None, dict | None]:
    if not min_columns <= len(columns) <= max_columns or len(set(columns)) != len(columns):
        return None, {"ok": False, "error": f"select {min_columns}-{max_columns} distinct columns"}
    if not 1 <= max_rows <= 1_000_000:
        return None, {"ok": False, "error": "max_rows must be 1-1000000"}
    path = Path(csv_path).expanduser()
    if not path.is_absolute() or path.suffix.lower() != ".csv" or not path.is_file():
        return None, {"ok": False, "error": "provide an existing absolute .csv path"}
    return path, None


def profile_csv_variables_data(csv_path: str, columns: list[str], max_rows: int = 100000) -> dict:
    """Summarize selected CSV columns; never return individual rows."""
    path, error = _csv_request(csv_path, columns, max_rows, 1, 30)
    if error:
        return error
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            absent = [col for col in columns if col not in (reader.fieldnames or [])]
            if absent:
                return {"ok": False, "error": "columns_not_found", "columns": absent,
                        "available_columns": reader.fieldnames or []}
            counters = {col: Counter() for col in columns}
            missing = {col: 0 for col in columns}
            checked = 0
            for row in reader:
                if checked >= max_rows:
                    break
                checked += 1
                for col in columns:
                    value = (row[col] or "").strip()
                    if value:
                        counters[col][value] += 1
                    else:
                        missing[col] += 1
            fields = {}
            for col in columns:
                count = counters[col]
                fields[col] = {
                    "nonmissing": sum(count.values()), "missing": missing[col],
                    "distinct_nonmissing": len(count),
                    "value_counts_if_10_or_fewer_levels": dict(count) if len(count) <= 10 else None,
                }
            return {"ok": True, "checked_rows": checked, "reached_row_limit": checked >= max_rows,
                    "columns": fields, "note": "Descriptive counts only; no model was estimated."}
    except OSError:
        return {"ok": False, "error": "csv_read_error"}


def count_group_cells_data(csv_path: str, columns: list[str], max_rows: int = 100000) -> dict:
    """Count observed combinations in 2-3 selected columns, excluding incomplete rows."""
    path, error = _csv_request(csv_path, columns, max_rows, 2, 3)
    if error:
        return error
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            absent = [col for col in columns if col not in (reader.fieldnames or [])]
            if absent:
                return {"ok": False, "error": "columns_not_found", "columns": absent}
            combinations = Counter()
            incomplete = checked = 0
            for row in reader:
                if checked >= max_rows:
                    break
                checked += 1
                values = tuple((row[col] or "").strip() for col in columns)
                if any(not value for value in values):
                    incomplete += 1
                else:
                    combinations[values] += 1
            if len(combinations) > 100:
                return {"ok": False, "error": "too_many_group_combinations",
                        "observed_combinations": len(combinations),
                        "note": "Select low-cardinality categorical columns; no cell values were returned."}
            cells = [{"values": dict(zip(columns, values)), "count": count}
                     for values, count in sorted(combinations.items())]
            return {"ok": True, "checked_rows": checked, "reached_row_limit": checked >= max_rows,
                    "incomplete_rows": incomplete, "cells": cells,
                    "note": "Counts are unweighted and exclude rows missing a selected column."}
    except OSError:
        return {"ok": False, "error": "csv_read_error"}


def check_model_plan_data(plan_json: str) -> dict:
    """Check declared model-plan fields for omissions and internal mismatches only."""
    try:
        plan = json.loads(plan_json)
    except (ValueError, TypeError):
        return {"ok": False, "error": "plan_json must be valid JSON"}
    if not isinstance(plan, dict):
        return {"ok": False, "error": "plan_json must encode an object"}
    required = ("research_question", "data_source", "sample", "outcome", "exposure",
                "model_family", "estimand", "interpretation_plan")
    missing = [key for key in required if not plan.get(key)]
    issues = []
    outcome = plan.get("outcome")
    if outcome and (not isinstance(outcome, dict) or not outcome.get("name") or not outcome.get("type")):
        issues.append("outcome needs a name and type")
    family = str(plan.get("model_family", "")).lower()
    if "logit" in family and isinstance(outcome, dict) and outcome.get("type") != "binary":
        issues.append("binary Logit requires a declared binary outcome")
    if plan.get("interaction") and not plan.get("moderator"):
        issues.append("interaction is declared but moderator is missing")
    if plan.get("moderator") and not plan.get("interaction"):
        issues.append("moderator is declared but interaction is not specified")
    return {"ok": True, "status": "needs_revision" if missing or issues else "structurally_complete",
            "missing_fields": missing, "consistency_issues": issues,
            "review_items": ["Confirm variable definitions and skip logic in original documentation.",
                             "Check missingness and group sizes using actual data before fitting.",
                             "Review weights, fixed effects, uncertainty estimates and interpretation for the study design."],
            "note": "This is a completeness check, not proof that a model is statistically valid or causal."}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def search_openalex(query: str, limit: int = 10) -> dict:
    """Find scholarly works in OpenAlex. Returns metadata and source links; not verified claims."""
    return search_openalex_data(query, limit)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def search_crossref(query: str, limit: int = 10) -> dict:
    """Find registered works in Crossref by bibliographic query for independent discovery."""
    return search_crossref_data(query, limit)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def lookup_crossref_doi(doi: str, expected_title: str = "") -> dict:
    """Check a DOI's Crossref metadata and optional title similarity; this does not verify study findings."""
    return lookup_crossref_doi_data(doi, expected_title)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def profile_csv_variables(csv_path: str, columns: list[str], max_rows: int = 100000) -> dict:
    """Profile selected variables in a user-supplied local CSV: missingness and low-cardinality levels."""
    return profile_csv_variables_data(csv_path, columns, max_rows)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def count_group_cells(csv_path: str, columns: list[str], max_rows: int = 100000) -> dict:
    """Count observed 2-3 variable combinations in a local CSV to detect empty or sparse groups."""
    return count_group_cells_data(csv_path, columns, max_rows)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def check_model_plan(plan_json: str) -> dict:
    """Check a structured empirical model plan for missing fields and obvious contradictions."""
    return check_model_plan_data(plan_json)


if __name__ == "__main__":
    mcp.run()

