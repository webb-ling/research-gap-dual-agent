"""Focused tests for metadata normalization and MCP tool registration."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import server  # noqa: E402


class MetadataToolsTests(unittest.TestCase):
    def test_openalex_search_returns_traceable_records_without_key_leak(self):
        payload = {"results": [{
            "title": "Example study", "publication_year": 2024,
            "doi": "https://doi.org/10.1234/example",
            "id": "https://openalex.org/W123", "cited_by_count": 4,
            "authorships": [{"author": {"display_name": "A. Author"}}],
            "primary_location": {"source": {"display_name": "Example Journal"}},
        }]}
        with patch.dict(server.os.environ, {"OPENALEX_API_KEY": "secret"}):
            with patch.object(server, "_fetch_json", return_value=payload) as fetch:
                result = server.search_openalex_data("digital payment", 5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["doi"], "https://doi.org/10.1234/example")
        self.assertNotIn("secret", result["query_url"])
        self.assertIn("api_key=secret", fetch.call_args.args[0])

    def test_crossref_doi_title_check_only_confirms_metadata(self):
        payload = {"message": {
            "DOI": "10.1234/example", "title": ["Example Study"],
            "author": [{"given": "A.", "family": "Author"}],
            "published": {"date-parts": [[2024, 6]]},
            "container-title": ["Example Journal"], "type": "journal-article",
        }}
        with patch.object(server, "_fetch_json", return_value=payload):
            result = server.lookup_crossref_doi_data("https://doi.org/10.1234/example", "Example Study")
        self.assertEqual(result["status"], "metadata_found")
        self.assertEqual(result["title_similarity"], 1.0)
        self.assertIn("not the paper's methods", result["note"])

    def test_crossref_404_is_not_proof_paper_is_nonexistent(self):
        error = HTTPError("https://api.crossref.org/works/test", 404, "Not Found", None, None)
        with patch.object(server, "_fetch_json", side_effect=error):
            result = server.lookup_crossref_doi_data("10.1234/example")
        self.assertEqual(result["status"], "not_found_in_crossref")
        self.assertIn("does not prove", result["note"])

    def test_invalid_inputs_do_not_call_network(self):
        with patch.object(server, "_fetch_json") as fetch:
            self.assertFalse(server.search_openalex_data("", 10)["ok"])
            self.assertFalse(server.search_crossref_data("topic", 100)["ok"])
            self.assertFalse(server.lookup_crossref_doi_data("not-a-doi")["ok"])
        fetch.assert_not_called()

    def test_mcp_advertises_three_read_only_tools(self):
        from mcp import Client

        async def inspect():
            async with Client(server.mcp) as client:
                response = await client.list_tools()
                return {tool.name: tool.annotations.read_only_hint for tool in response.tools}

        self.assertEqual(asyncio.run(inspect()), {
            "search_openalex": True, "search_crossref": True,
            "lookup_crossref_doi": True,
        })


if __name__ == "__main__":
    unittest.main()
