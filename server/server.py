"""Read-only scholarly metadata tools exposed over MCP stdio."""

from __future__ import annotations

import difflib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


mcp = MCPServer("scholarly-metadata")
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


if __name__ == "__main__":
    mcp.run()
