"""Focused tests for metadata normalization and MCP tool registration."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
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

    def test_csv_profiles_and_group_counts_without_returning_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.csv"
            path.write_text("phone,rural,pay\nsmart,0,1\nbasic,1,0\nsmart,1,1\nsmart,,0\n", encoding="utf-8")
            profile = server.profile_csv_variables_data(str(path), ["phone", "rural", "pay"])
            cells = server.count_group_cells_data(str(path), ["phone", "rural", "pay"])
        self.assertEqual(profile["columns"]["rural"]["missing"], 1)
        self.assertEqual(profile["columns"]["phone"]["value_counts_if_10_or_fewer_levels"]["smart"], 3)
        self.assertEqual(cells["incomplete_rows"], 1)
        self.assertEqual(sum(cell["count"] for cell in cells["cells"]), 3)
        self.assertNotIn("smart,0,1", json.dumps(profile))

    def test_model_plan_flags_missing_moderator_and_nonbinary_logit(self):
        plan = {"research_question": "Does association differ by area?", "data_source": "survey",
                "sample": "eligible adults", "outcome": {"name": "payment", "type": "continuous"},
                "exposure": "phone", "model_family": "Logit", "interaction": True,
                "estimand": "conditional association", "interpretation_plan": "predicted probabilities"}
        result = server.check_model_plan_data(json.dumps(plan))
        self.assertEqual(result["status"], "needs_revision")
        self.assertEqual(len(result["consistency_issues"]), 2)
        self.assertTrue(any("moderator" in issue for issue in result["consistency_issues"]))

    def test_mcp_advertises_six_read_only_tools(self):
        from mcp import Client

        async def inspect():
            async with Client(server.mcp) as client:
                response = await client.list_tools()
                return {tool.name: tool.annotations.read_only_hint for tool in response.tools}

        self.assertEqual(asyncio.run(inspect()), {
            "search_openalex": True, "search_crossref": True,
            "lookup_crossref_doi": True,
            "profile_csv_variables": True, "count_group_cells": True,
            "check_model_plan": True,
        })


if __name__ == "__main__":
    unittest.main()

