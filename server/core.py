"""Pure, bounded checks behind the research workflow MCP tools."""

from __future__ import annotations

import csv
import difflib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


USER_AGENT = (
    "research-model-writing-pipeline/2.2 "
    "(scholarly metadata; https://github.com/webb-ling/research-model-writing-pipeline)"
)
MAX_SEARCH_WINDOW = 10_000
MAX_GROUP_COMBINATIONS = 100


def _fetch_json(url: str) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with urlopen(Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def _request_error(source: str, error: Exception) -> dict:
    if isinstance(error, HTTPError):
        return {"ok": False, "source": source, "status": error.code, "error": "upstream_http_error"}
    if isinstance(error, URLError):
        return {"ok": False, "source": source, "error": "upstream_connection_error"}
    return {"ok": False, "source": source, "error": "unexpected_error"}


def _valid_search(query: str, limit: int, page: int) -> bool:
    return (
        isinstance(query, str)
        and 1 <= len(query.strip()) <= 500
        and type(limit) is int
        and 1 <= limit <= 100
        and type(page) is int
        and page >= 1
        and page * limit <= MAX_SEARCH_WINDOW
    )


def _search_meta(source: str, query: str, page: int, limit: int, total: int | None, returned: int) -> dict:
    return {
        "database": source,
        "query": query,
        "searched_at_utc": datetime.now(timezone.utc).date().isoformat(),
        "page": page,
        "page_size": limit,
        "total_results_reported": total,
        "returned_count": returned,
        "has_more": (page * limit < total) if isinstance(total, int) else returned == limit,
        "coverage_note": "One search page only; relevance ranking and database indexing limit coverage.",
    }


def _authors_from_openalex(work: dict) -> list[str]:
    return [
        name for entry in work.get("authorships", [])
        if (name := (entry.get("author") or {}).get("display_name"))
    ]


def _authors_from_crossref(work: dict) -> list[str]:
    return [
        name for author in work.get("author", [])
        if (name := " ".join(filter(None, (author.get("given"), author.get("family")))))
    ]


def _year_from_crossref(work: dict) -> tuple[int | None, str | None]:
    for key in ("published", "published-online", "published-print", "issued"):
        parts = (work.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and type(parts[0][0]) is int:
            return parts[0][0], key
    return None, None


def _crossref_record(work: dict) -> dict:
    doi = work.get("DOI")
    year, year_source = _year_from_crossref(work)
    authors = _authors_from_crossref(work)
    return {
        "title": (work.get("title") or [None])[0],
        "authors": authors,
        "author_count": len(authors),
        "year": year,
        "year_source": year_source,
        "year_needs_verification": year is None,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else None,
        "venue": (work.get("container-title") or [None])[0],
        "type": work.get("type"),
    }


def search_openalex_data(query: str, limit: int = 10, page: int = 1) -> dict:
    if not _valid_search(query, limit, page):
        return {"ok": False, "source": "OpenAlex", "error": "query must have 1-500 characters; limit 1-100; page*limit <= 10000"}
    query = query.strip()
    public_url = "https://api.openalex.org/works?" + urlencode({"search": query, "per_page": limit, "page": page})
    key = os.getenv("OPENALEX_API_KEY")
    url = public_url + ("&" + urlencode({"api_key": key}) if key else "")
    try:
        payload = _fetch_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return _request_error("OpenAlex", error)
    works = []
    for work in payload.get("results", []):
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        authors = _authors_from_openalex(work)
        works.append({
            "title": work.get("title"), "authors": authors, "author_count": len(authors),
            "year": work.get("publication_year"), "doi": work.get("doi"),
            "openalex_url": work.get("id"), "venue": source.get("display_name"),
            "cited_by_count": work.get("cited_by_count"),
        })
    total = (payload.get("meta") or {}).get("count")
    return {
        "ok": True, "source": "OpenAlex", "query_url": public_url,
        "search_log": _search_meta("OpenAlex", query, page, limit, total, len(works)),
        "results": works,
    }


def search_crossref_data(query: str, limit: int = 10, page: int = 1) -> dict:
    if not _valid_search(query, limit, page):
        return {"ok": False, "source": "Crossref", "error": "query must have 1-500 characters; limit 1-100; page*limit <= 10000"}
    query = query.strip()
    public_params = {"query.bibliographic": query, "rows": limit, "offset": (page - 1) * limit}
    public_url = "https://api.crossref.org/works?" + urlencode(public_params)
    mailto = os.getenv("CROSSREF_MAILTO")
    url = public_url + ("&" + urlencode({"mailto": mailto}) if mailto else "")
    try:
        message = _fetch_json(url).get("message", {})
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return _request_error("Crossref", error)
    works = [_crossref_record(work) for work in message.get("items", [])]
    return {
        "ok": True, "source": "Crossref", "query_url": public_url,
        "search_log": _search_meta("Crossref", query, page, limit, message.get("total-results"), len(works)),
        "results": works,
    }


def _normalized_doi(doi: str | None) -> str:
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", (doi or "").strip(), flags=re.I).strip().lower()


def _normalized_title(title: str | None) -> str:
    return re.sub(r"[^\w]+", " ", (title or "").casefold()).strip()


def deduplicate_works(records: list[dict]) -> list[dict]:
    """Merge exact DOIs; attach a DOI-less record only to one unambiguous DOI."""
    merged: list[dict] = []
    doi_index: dict[str, int] = {}
    no_doi: list[dict] = []

    def merge_into(index: int, record: dict) -> None:
        existing = merged[index]
        for source in record.pop("sources", []):
            if source not in existing["sources"]:
                existing["sources"].append(source)
        for key, value in record.items():
            if existing.get(key) is None and value is not None:
                existing[key] = value

    for original in records:
        record = dict(original)
        source = record.pop("_source", None)
        record["sources"] = [source] if source else []
        doi = _normalized_doi(record.get("doi"))
        if doi:
            if doi in doi_index:
                merge_into(doi_index[doi], record)
            else:
                doi_index[doi] = len(merged)
                record["deduplication_status"] = "exact_doi_or_unique_record"
                merged.append(record)
        else:
            no_doi.append(record)

    title_index: dict[tuple[str, int], list[int]] = {}
    for index, record in enumerate(merged):
        title_key = (_normalized_title(record.get("title")), record.get("year"))
        if title_key[0] and type(title_key[1]) is int:
            title_index.setdefault(title_key, []).append(index)

    for record in no_doi:
        title_key = (_normalized_title(record.get("title")), record.get("year"))
        candidates = title_index.get(title_key, []) if title_key[0] and type(title_key[1]) is int else []
        if len(candidates) == 1:
            merge_into(candidates[0], record)
            merged[candidates[0]]["deduplication_status"] = "title_year_single_doi_needs_review"
        else:
            record["deduplication_status"] = (
                "ambiguous_title_year_needs_review" if len(candidates) > 1 else "no_doi_needs_review"
            )
            if len(candidates) > 1:
                record["candidate_dois"] = [merged[index]["doi"] for index in candidates]
            merged.append(record)
    return merged


def search_literature_data(query: str, limit: int = 10, page: int = 1) -> dict:
    openalex = search_openalex_data(query, limit, page)
    crossref = search_crossref_data(query, limit, page)
    sources = {"OpenAlex": openalex, "Crossref": crossref}
    records = [dict(work, _source=name) for name, result in sources.items() if result.get("ok") for work in result["results"]]
    return {
        "ok": any(result.get("ok") for result in sources.values()),
        "status": "both_sources_succeeded" if all(result.get("ok") for result in sources.values()) else "partial_or_failed",
        "coverage_status": "requested_page_only",
        "source_searches": {name: (result.get("search_log") if result.get("ok") else {"error": result.get("error")})
                            for name, result in sources.items()},
        "raw_returned_count": len(records),
        "deduplicated_count": len(merged := deduplicate_works(records)),
        "ambiguous_deduplication_count": sum(
            work.get("deduplication_status") == "ambiguous_title_year_needs_review" for work in merged
        ),
        "results": merged,
        "note": "Only the requested page from each database was checked; total counts are not screened counts.",
    }


def lookup_crossref_doi_data(doi: str, expected_title: str = "") -> dict:
    if not isinstance(doi, str) or not isinstance(expected_title, str) or len(expected_title) > 500:
        return {"ok": False, "source": "Crossref", "error": "invalid DOI or expected title"}
    doi = _normalized_doi(doi)
    if not doi.startswith("10.") or "/" not in doi or len(doi) > 300:
        return {"ok": False, "source": "Crossref", "error": "invalid DOI format"}
    try:
        work = _fetch_json("https://api.crossref.org/works/" + quote(doi, safe="")).get("message", {})
    except HTTPError as error:
        if error.code == 404:
            return {"ok": True, "source": "Crossref", "status": "not_found_in_crossref", "doi": doi,
                    "note": "Crossref has no record; this does not prove the DOI or paper is nonexistent."}
        return _request_error("Crossref", error)
    except (URLError, TimeoutError, ValueError) as error:
        return _request_error("Crossref", error)
    result = _crossref_record(work)
    result.update({
        "ok": True, "source": "Crossref", "status": "metadata_found",
        "doi": work.get("DOI", doi), "publisher": work.get("publisher"),
        "publisher_url": work.get("URL"),
        "title_match_status": "not_checked" if not expected_title else "title_unavailable",
        "note": "Registration metadata does not verify the paper's methods, results, or research gap.",
    })
    if expected_title and result["title"]:
        similarity = difflib.SequenceMatcher(None, _normalized_title(expected_title),
                                             _normalized_title(result["title"])).ratio()
        result["title_similarity"] = round(similarity, 3)
        result["title_match_status"] = "possible_mismatch" if similarity < 0.85 else "similar_title_check_original"
    return result


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _public_source_url(value: object) -> bool:
    if not _nonempty_text(value) or value != value.strip() or any(char.isspace() for char in value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)
    except ValueError:
        return False


def check_gap_evidence_data(gap_json: str) -> dict:
    """Validate a handoff record's shape, never the truth of its evidence."""
    if not isinstance(gap_json, str) or len(gap_json) > 100_000:
        return {"ok": False, "error": "gap_json must be a JSON string of at most 100000 characters"}
    try:
        gap = json.loads(gap_json)
    except ValueError:
        return {"ok": False, "error": "gap_json must be valid JSON"}
    if not isinstance(gap, dict):
        return {"ok": False, "error": "gap_json must encode an object"}
    missing = [key for key in ("candidate_gap", "existing_coverage", "unresolved_part",
                               "data_feasibility", "evidence_boundary") if not _nonempty_text(gap.get(key))]
    invalid: list[str] = []
    consistency: list[str] = []
    logs = gap.get("search_log")
    if not isinstance(logs, list) or not logs:
        missing.append("search_log")
    else:
        for index, entry in enumerate(logs):
            if not isinstance(entry, dict):
                invalid.append(f"search_log[{index}] must be an object")
                continue
            for field in ("database", "query", "searched_at_utc"):
                if not _nonempty_text(entry.get(field)):
                    invalid.append(f"search_log[{index}].{field} is required")
            page = entry.get("page")
            if type(page) is not int or page < 1:
                invalid.append(f"search_log[{index}].page must be a positive integer")
            returned = entry.get("returned_count")
            if type(returned) is not int or returned < 0:
                invalid.append(f"search_log[{index}].returned_count must be a nonnegative integer")
            screened = entry.get("screened_count")
            if type(screened) is not int or screened < 0:
                invalid.append(f"search_log[{index}].screened_count must be a nonnegative integer")
            elif type(returned) is int and returned >= 0 and screened > returned:
                consistency.append(f"search_log[{index}].screened_count exceeds returned_count")
    studies = gap.get("closest_studies")
    if not isinstance(studies, list) or not studies:
        missing.append("closest_studies")
    else:
        for index, study in enumerate(studies):
            if not isinstance(study, dict):
                invalid.append(f"closest_studies[{index}] must be an object")
                continue
            for field in ("title", "original_url", "covered_question", "remaining_difference"):
                if not _nonempty_text(study.get(field)):
                    invalid.append(f"closest_studies[{index}].{field} is required")
            if _nonempty_text(study.get("original_url")) and not _public_source_url(study["original_url"]):
                invalid.append(f"closest_studies[{index}].original_url must be an http(s) URL")
            if study.get("verification_status") not in ("passed", "needs_revision", "unconfirmed"):
                invalid.append(f"closest_studies[{index}].verification_status is invalid")
    if gap.get("verification_status") not in ("passed", "needs_revision", "unconfirmed"):
        invalid.append("verification_status is invalid")
    elif gap["verification_status"] == "passed" and isinstance(studies, list) and any(
        not isinstance(study, dict) or study.get("verification_status") != "passed" for study in studies
    ):
        consistency.append("overall verification_status=passed conflicts with a closest study not marked passed")
    return {
        "ok": True,
        "status": "needs_revision" if missing or invalid or consistency else "required_fields_present",
        "missing_fields": missing,
        "invalid_fields": invalid,
        "consistency_issues": consistency,
        "evidence_verification_status": "not_assessed_by_tool",
        "note": "This only checks record structure; source links and research claims need independent review.",
    }


def _csv_request(
    csv_path: str, columns: list[str], max_rows: int,
    missing_values: dict[str, list[str]] | None, min_columns: int, max_columns: int,
) -> tuple[Path | None, dict | None, dict[str, set[str]] | None, int | None]:
    if (
        not isinstance(columns, list)
        or not min_columns <= len(columns) <= max_columns
        or any(not _nonempty_text(col) for col in columns)
        or len(set(columns)) != len(columns)
    ):
        return None, {"ok": False, "error": f"select {min_columns}-{max_columns} distinct column names"}, None, None
    if type(max_rows) is not int or not 1 <= max_rows <= 1_000_000:
        return None, {"ok": False, "error": "max_rows must be 1-1000000"}, None, None
    root_setting = os.getenv("RESEARCH_DATA_DIR")
    if not root_setting:
        return None, {"ok": False, "error": "data_directory_not_configured",
                      "note": "Set RESEARCH_DATA_DIR to a directory explicitly approved for this MCP server."}, None, None
    try:
        root = Path(root_setting).expanduser().resolve(strict=True)
        path = Path(csv_path).expanduser()
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        path = path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, {"ok": False, "error": "invalid_csv_path_or_data_directory"}, None, None
    if not root.is_dir() or not path.is_relative_to(root) or path.suffix.lower() != ".csv" or not path.is_file():
        return None, {"ok": False, "error": "csv_path_outside_authorized_directory"}, None, None
    threshold_text = os.getenv("RESEARCH_MIN_CELL_COUNT", "5")
    try:
        threshold = int(threshold_text)
    except ValueError:
        threshold = 0
    if not 2 <= threshold <= 100:
        return None, {"ok": False, "error": "RESEARCH_MIN_CELL_COUNT must be 2-100"}, None, None
    if missing_values is not None and not isinstance(missing_values, dict):
        return None, {"ok": False, "error": "missing_values must map selected columns to lists of codes"}, None, None
    codes = {col: {""} for col in columns}
    for col, values in (missing_values or {}).items():
        if col not in codes or not isinstance(values, list) or len(values) > 20 or any(
            not isinstance(value, str) or len(value) > 100 for value in values
        ):
            return None, {"ok": False, "error": "invalid_missing_values"}, None, None
        codes[col].update(value.strip() for value in values)
    return path, None, codes, threshold


def _limit_note(truncated: bool) -> str:
    if truncated:
        return "Only the first max_rows data rows were checked; file order may bias these counts."
    return "All data rows in the supplied file were checked."


def profile_csv_variables_data(
    csv_path: str, columns: list[str], max_rows: int = 100000,
    missing_values: dict[str, list[str]] | None = None,
) -> dict:
    """Summarize approved columns without returning rows or sparse categories."""
    path, error, codes, threshold = _csv_request(csv_path, columns, max_rows, missing_values, 1, 30)
    if error:
        return error
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
            reader = csv.DictReader(stream)
            absent = [col for col in columns if col not in (reader.fieldnames or [])]
            if absent:
                return {"ok": False, "error": "columns_not_found", "columns": absent}
            counters = {col: Counter() for col in columns}
            unique = {col: set() for col in columns}
            missing = {col: 0 for col in columns}
            nonmissing = {col: 0 for col in columns}
            checked = 0
            truncated = False
            for row in reader:
                if checked == max_rows:
                    truncated = True
                    break
                checked += 1
                for col in columns:
                    value = (row[col] or "").strip()
                    if value in codes[col]:
                        missing[col] += 1
                    else:
                        nonmissing[col] += 1
                        if len(unique[col]) <= 1000:
                            unique[col].add(value)
                        if len(unique[col]) <= 10:
                            counters[col][value] += 1
                        else:
                            counters[col].clear()
            fields = {}
            for col in columns:
                counts = counters[col]
                low_frequency = bool(counts) and any(count < threshold for count in counts.values())
                fields[col] = {
                    "nonmissing": nonmissing[col], "missing": missing[col],
                    "distinct_nonmissing": len(unique[col]) if len(unique[col]) <= 1000 else None,
                    "distinct_nonmissing_at_least": 1001 if len(unique[col]) > 1000 else None,
                    "value_counts_if_10_or_fewer_levels": dict(counts) if counts and not low_frequency else None,
                    "counts_suppressed": low_frequency,
                }
            return {
                "ok": True, "checked_rows": checked, "reached_row_limit": checked == max_rows,
                "truncated_by_row_limit": truncated, "minimum_cell_count": threshold,
                "columns": fields, "note": "Descriptive, unweighted counts only. " + _limit_note(truncated),
            }
    except (OSError, csv.Error):
        return {"ok": False, "error": "csv_read_error"}


def count_group_cells_data(
    csv_path: str, columns: list[str], max_rows: int = 100000,
    missing_values: dict[str, list[str]] | None = None,
) -> dict:
    """Count approved 2-3 column combinations, suppressing all sparse cells."""
    path, error, codes, threshold = _csv_request(csv_path, columns, max_rows, missing_values, 2, 3)
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
            truncated = False
            for row in reader:
                if checked == max_rows:
                    truncated = True
                    break
                checked += 1
                values = tuple((row[col] or "").strip() for col in columns)
                if any(value in codes[col] for col, value in zip(columns, values)):
                    incomplete += 1
                else:
                    combinations[values] += 1
                    if len(combinations) > MAX_GROUP_COMBINATIONS:
                        return {"ok": False, "error": "too_many_group_combinations",
                                "note": "Use categorical columns with at most 100 observed combinations; no cells returned."}
            suppressed = any(count < threshold for count in combinations.values())
            cells = None if suppressed else [
                {"values": dict(zip(columns, values)), "count": count}
                for values, count in sorted(combinations.items())
            ]
            return {
                "ok": True, "checked_rows": checked, "reached_row_limit": checked == max_rows,
                "truncated_by_row_limit": truncated, "incomplete_rows": incomplete,
                "minimum_cell_count": threshold, "cells_suppressed": suppressed,
                "cells": cells, "note": "Unweighted complete-case counts. " + _limit_note(truncated),
            }
    except (OSError, csv.Error):
        return {"ok": False, "error": "csv_read_error"}


def _model_family(value: str) -> str | None:
    family = re.sub(r"[\s_-]+", " ", value.strip().casefold())
    if family in ("ols", "linear", "linear regression"):
        return "ols"
    if family in ("ordinal logit", "ordered logit"):
        return "ordinal_logit"
    if family == "multinomial logit":
        return "multinomial_logit"
    if family in ("binary logit", "logit", "logistic regression"):
        return "logit"
    if family in ("ordinal probit", "ordered probit"):
        return "ordinal_probit"
    if family == "multinomial probit":
        return "multinomial_probit"
    if family in ("binary probit", "probit"):
        return "probit"
    if family == "poisson":
        return "poisson"
    if family == "negative binomial":
        return "negative_binomial"
    return "other" if family == "other" else None


_FORMULA_NAME = r"[^\W\d]\w*"
_SIMPLE_TERM = re.compile(rf"\s*({_FORMULA_NAME})(?:\s*([:*])\s*({_FORMULA_NAME}))?\s*\Z")


def _simple_name(value: object) -> bool:
    return _nonempty_text(value) and re.fullmatch(_FORMULA_NAME, value) is not None


def _formula_checks(plan: dict, controls: object, fixed_effects: object) -> tuple[list[str], list[str]]:
    """Check simple R/Patsy formulas; send unparsed notation to human review."""
    formula = plan.get("model_formula")
    outcome = plan.get("outcome")
    exposure = plan.get("exposure")
    moderator = plan.get("moderator")
    if not _nonempty_text(formula) or not isinstance(outcome, dict):
        return [], []
    issues: list[str] = []
    manual: list[str] = []
    if formula.count("~") != 1:
        if "=" in formula:
            for declared, label in ((outcome.get("name"), "outcome"), (exposure, "exposure")):
                if _simple_name(declared) and not re.search(
                    rf"(?<!\w){re.escape(declared)}(?!\w)", formula, flags=re.I
                ):
                    issues.append(f"model_formula omits declared {label}")
            if plan.get("interaction") is True and _simple_name(exposure) and _simple_name(moderator):
                pair = (rf"(?<!\w){re.escape(exposure)}\s*[×*·:]\s*{re.escape(moderator)}(?!\w)|"
                        rf"(?<!\w){re.escape(moderator)}\s*[×*·:]\s*{re.escape(exposure)}(?!\w)")
                if not re.search(pair, formula, flags=re.I):
                    manual.append("no explicit exposure-moderator product found in mathematical formula")
        manual.append("model_formula uses mathematical or unsupported syntax; verify variables and interaction manually")
        return issues, manual
    left, right = (part.strip() for part in formula.split("~", 1))
    if not _simple_name(left) or not right:
        manual.append("model_formula outcome or right-hand side needs manual parsing")
        return issues, manual
    if _simple_name(outcome.get("name")):
        if left.casefold() != outcome["name"].casefold():
            issues.append("model_formula outcome does not match outcome.name")
    else:
        manual.append("outcome.name uses an alias or expression; verify model_formula manually")

    variables: set[str] = set()
    interactions: set[frozenset[str]] = set()
    for term in right.split("+"):
        if term.strip() in ("0", "1"):
            continue
        match = _SIMPLE_TERM.fullmatch(term)
        if not match:
            manual.append("model_formula has functions, aliases, subtraction or unsupported terms")
            return issues, manual
        first, operator, second = match.groups()
        variables.add(first.casefold())
        if operator:
            variables.add(second.casefold())
            interactions.add(frozenset((first.casefold(), second.casefold())))
    if _simple_name(exposure):
        if exposure.casefold() not in variables:
            issues.append("model_formula omits declared exposure")
    else:
        manual.append("exposure uses an alias or expression; verify model_formula manually")
    if plan.get("interaction") is True and _simple_name(moderator) and _simple_name(exposure):
        if frozenset((exposure.casefold(), moderator.casefold())) not in interactions:
            issues.append("interaction=true but model_formula omits the exposure-moderator interaction")
    elif plan.get("interaction") is True:
        manual.append("interaction variable aliases need manual formula review")
    defined = {name.casefold() for name in (exposure, moderator) if _simple_name(name)}
    for collection in (controls, fixed_effects):
        if isinstance(collection, list):
            defined.update(item["name"].casefold() for item in collection
                           if isinstance(item, dict) and _simple_name(item.get("name")))
    unknown = sorted(variables - defined)
    if unknown:
        manual.append("model_formula variables lack matching definitions: " + ", ".join(unknown))
    return issues, manual


def check_model_plan_data(plan_json: str) -> dict:
    """Validate a *proposal*'s fields and a few contradictions, never its fitted model."""
    if not isinstance(plan_json, str) or len(plan_json) > 100_000:
        return {"ok": False, "error": "plan_json must be a JSON string of at most 100000 characters"}
    try:
        plan = json.loads(plan_json)
    except ValueError:
        return {"ok": False, "error": "plan_json must be valid JSON"}
    if not isinstance(plan, dict):
        return {"ok": False, "error": "plan_json must encode an object"}

    missing: list[str] = []
    invalid: list[str] = []
    issues: list[str] = []
    manual_review: list[str] = []
    for field in (
        "research_question", "data_source", "sample", "exposure", "exposure_encoding",
        "model_family", "model_formula", "estimand", "interpretation_plan",
        "missing_data_plan", "robustness_plan",
    ):
        value = plan.get(field)
        if value is None or value == "":
            missing.append(field)
        elif not _nonempty_text(value):
            invalid.append(f"{field} must be a nonempty string")

    outcome = plan.get("outcome")
    if outcome is None:
        missing.append("outcome")
    elif not isinstance(outcome, dict):
        invalid.append("outcome must be an object")
    else:
        for field in ("name", "type", "encoding"):
            if not _nonempty_text(outcome.get(field)):
                missing.append(f"outcome.{field}")
        if _nonempty_text(outcome.get("type")) and outcome["type"] not in (
            "binary", "continuous", "count", "ordinal", "nominal", "rate", "other"
        ):
            invalid.append("outcome.type is unsupported")
        if outcome.get("type") == "other" and not _nonempty_text(outcome.get("type_note")):
            missing.append("outcome.type_note")

    family = None
    if _nonempty_text(plan.get("model_family")):
        family = _model_family(plan["model_family"])
        if family is None:
            invalid.append("model_family is unsupported")
        elif family == "other" and not _nonempty_text(plan.get("model_family_note")):
            missing.append("model_family_note")
    outcome_type = outcome.get("type") if isinstance(outcome, dict) else None
    if family in ("logit", "probit") and outcome_type not in (None, "binary"):
        issues.append("binary Logit/Probit requires a binary outcome")
    if family in ("poisson", "negative_binomial") and outcome_type not in (None, "count", "rate"):
        issues.append("Poisson/negative binomial requires a count or rate outcome")
    if family in ("ordinal_logit", "ordinal_probit") and outcome_type not in (None, "ordinal"):
        issues.append("ordinal Logit/Probit requires an ordinal outcome")
    if family in ("multinomial_logit", "multinomial_probit") and outcome_type not in (None, "nominal"):
        issues.append("multinomial Logit/Probit requires a nominal outcome")
    if family == "ols" and outcome_type == "binary" and not _nonempty_text(plan.get("model_family_note")):
        issues.append("OLS with a binary outcome needs a linear-probability rationale")

    controls = plan.get("controls")
    if controls is None:
        missing.append("controls")
    elif not isinstance(controls, list):
        invalid.append("controls must be a list; use [] when none are planned")
    else:
        for index, control in enumerate(controls):
            if not isinstance(control, dict) or not all(_nonempty_text(control.get(k)) for k in ("name", "rationale")):
                invalid.append(f"controls[{index}] needs name and rationale")

    fixed_effects = plan.get("fixed_effects")
    if fixed_effects is None:
        missing.append("fixed_effects")
    elif not isinstance(fixed_effects, list):
        invalid.append("fixed_effects must be a list; use [] when none are planned")
    else:
        for index, effect in enumerate(fixed_effects):
            if not isinstance(effect, dict) or not all(_nonempty_text(effect.get(k)) for k in ("name", "rationale")):
                invalid.append(f"fixed_effects[{index}] needs name and rationale")

    errors = plan.get("standard_errors")
    if errors is None:
        missing.append("standard_errors")
    elif not isinstance(errors, dict):
        invalid.append("standard_errors must be an object")
    else:
        method = errors.get("method")
        if method not in ("iid", "heteroskedastic_robust", "clustered", "survey_design", "other"):
            invalid.append("standard_errors.method is unsupported")
        if method == "clustered" and not _nonempty_text(errors.get("cluster_level")):
            missing.append("standard_errors.cluster_level")
        if method == "other" and not _nonempty_text(errors.get("rationale")):
            missing.append("standard_errors.rationale")

    design = plan.get("sampling_design")
    if design is None:
        missing.append("sampling_design")
    elif not isinstance(design, dict):
        invalid.append("sampling_design must be an object")
    else:
        kind = design.get("kind")
        if kind not in ("complex_survey", "simple_random", "administrative", "convenience", "other"):
            invalid.append("sampling_design.kind is unsupported")
        if kind == "complex_survey":
            for field in ("weight_plan", "variance_plan"):
                if not _nonempty_text(design.get(field)):
                    missing.append(f"sampling_design.{field}")
        if kind == "other" and not _nonempty_text(design.get("rationale")):
            missing.append("sampling_design.rationale")
        if isinstance(errors, dict) and errors.get("method") == "survey_design" and kind != "complex_survey":
            issues.append("survey-design standard errors require a complex-survey sampling design")
        if kind == "complex_survey" and isinstance(errors, dict) and errors.get("method") in (
            "iid", "heteroskedastic_robust", "clustered", "other"
        ):
            if not _nonempty_text(errors.get("design_compatibility_rationale")):
                missing.append("standard_errors.design_compatibility_rationale")
            else:
                manual_review.append(
                    "complex-survey variance method differs from survey_design; independently assess its rationale"
                )

    interaction = plan.get("interaction", False)
    if not isinstance(interaction, bool):
        invalid.append("interaction must be boolean")
    if interaction is True and not _nonempty_text(plan.get("moderator")):
        missing.append("moderator")
    if interaction is False and _nonempty_text(plan.get("moderator")):
        issues.append("moderator is declared but interaction is false")
    if "causal_claim" not in plan:
        missing.append("causal_claim")
    elif not isinstance(plan["causal_claim"], bool):
        invalid.append("causal_claim must be boolean")
    elif plan["causal_claim"] and not _nonempty_text(plan.get("identification_assumptions")):
        missing.append("identification_assumptions")

    formula_issues, formula_manual = _formula_checks(plan, controls, fixed_effects)
    issues.extend(formula_issues)
    manual_review.extend(formula_manual)
    ready = not (missing or invalid or issues)
    review_items = [
        "Check formula, coding, eligibility and skip logic against the data dictionary.",
        "Inspect actual missingness, group sizes and estimability before fitting.",
        "Fit the model and inspect diagnostics, uncertainty and robustness before making findings.",
    ]
    if isinstance(design, dict) and design.get("kind") == "complex_survey":
        review_items.append("Verify weights, strata and clusters in the original survey documentation.")
    return {
        "ok": True, "status": ("needs_revision" if not ready else
                              "requires_manual_review" if manual_review else "ready_for_data_validation"),
        "required_fields_present": not missing,
        "specification_consistency": ("issues_found" if invalid or issues else
                                      "requires_manual_review" if manual_review else "no_obvious_conflict"),
        "formula_review_status": ("issues_found" if formula_issues else
                                  "requires_manual_review" if formula_manual else "simple_formula_checked"),
        "data_validation_status": "not_run",
        "statistical_validity_status": "not_assessed",
        "missing_fields": missing, "invalid_fields": invalid, "consistency_issues": issues,
        "manual_review_items": manual_review,
        "review_items": review_items,
        "note": "Static plan checks do not establish model correctness, fit, significance or causality.",
    }

