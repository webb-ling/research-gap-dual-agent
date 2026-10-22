"""Meaningful boundary tests for the research MCP and its pure checks."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import core  # noqa: E402


def valid_plan() -> dict:
    return {
        "research_question": "Does the association differ by area?",
        "data_source": "official survey 2024", "sample": "eligible adults",
        "outcome": {"name": "payment", "type": "binary", "encoding": "yes=1, no=0"},
        "exposure": "phone type", "exposure_encoding": "smart=1, basic=0",
        "moderator": "rural residence", "interaction": True,
        "model_family": "binary Logit", "model_formula": "payment ~ phone * rural + age",
        "controls": [{"name": "age", "rationale": "plausible common cause"}],
        "fixed_effects": [], "missing_data_plan": "complete cases, report exclusions",
        "standard_errors": {"method": "clustered", "cluster_level": "survey cluster"},
        "sampling_design": {"kind": "complex_survey", "weight_plan": "use person weight",
                            "variance_plan": "account for clusters and strata"},
        "estimand": "adjusted association", "interpretation_plan": "predicted probabilities",
        "robustness_plan": "compare alternative controls", "causal_claim": False,
    }


class LiteratureTests(unittest.TestCase):
    def test_openalex_paging_count_full_authors_and_secret_not_returned(self):
        payload = {"meta": {"count": 240}, "results": [{
            "title": "Example", "publication_year": 2024, "doi": "https://doi.org/10.1/x",
            "authorships": [{"author": {"display_name": str(i)}} for i in range(9)],
        }]}
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "private-key"}):
            with patch.object(core, "_fetch_json", return_value=payload) as fetch:
                result = core.search_openalex_data("digital payment", 20, 2)
        self.assertEqual(result["search_log"]["total_results_reported"], 240)
        self.assertEqual(result["search_log"]["page"], 2)
        self.assertEqual(result["results"][0]["author_count"], 9)
        self.assertNotIn("private-key", json.dumps(result))
        self.assertIn("page=2", fetch.call_args.args[0])

    def test_crossref_offset_and_created_date_not_used_as_publication_year(self):
        payload = {"message": {"total-results": 80, "items": [{
            "title": ["Example"], "created": {"date-parts": [[2026, 1]]},
            "author": [{"given": "A", "family": str(i)} for i in range(10)],
        }]}}
        with patch.object(core, "_fetch_json", return_value=payload) as fetch:
            result = core.search_crossref_data("payment", 20, 3)
        self.assertIn("offset=40", fetch.call_args.args[0])
        self.assertIsNone(result["results"][0]["year"])
        self.assertTrue(result["results"][0]["year_needs_verification"])
        self.assertEqual(result["results"][0]["author_count"], 10)

    def test_combined_search_deduplicates_by_doi_and_title_year(self):
        openalex = {"ok": True, "results": [
            {"title": "Same Study", "year": 2024, "doi": "https://doi.org/10.1234/A"},
            {"title": "No DOI", "year": 2023, "doi": None},
        ], "search_log": {"database": "OpenAlex"}}
        crossref = {"ok": True, "results": [
            {"title": "Same Study", "year": 2024, "doi": "10.1234/a"},
            {"title": "No-DOI", "year": 2023, "doi": "10.1234/b"},
        ], "search_log": {"database": "Crossref"}}
        with patch.object(core, "search_openalex_data", return_value=openalex), patch.object(
            core, "search_crossref_data", return_value=crossref
        ):
            result = core.search_literature_data("example")
        self.assertEqual(result["raw_returned_count"], 4)
        self.assertEqual(result["deduplicated_count"], 2)
        self.assertEqual(result["results"][0]["sources"], ["OpenAlex", "Crossref"])

    def test_different_dois_with_same_title_remain_separate(self):
        records = [
            {"title": "Same Study", "year": 2024, "doi": "10.1234/a"},
            {"title": "Same Study", "year": 2024, "doi": "10.1234/b"},
        ]
        self.assertEqual(len(core.deduplicate_works(records)), 2)

    def test_doi_mismatch_status_and_404_boundary(self):
        with patch.object(core, "_fetch_json", return_value={"message": {
            "DOI": "10.1234/x", "title": ["Completely Different Article"],
            "published-online": {"date-parts": [[2025, 5]]},
        }}):
            result = core.lookup_crossref_doi_data("10.1234/x", "Digital Payments")
        self.assertEqual(result["title_match_status"], "possible_mismatch")
        self.assertEqual(result["year_source"], "published-online")
        error = HTTPError("https://api.crossref.org/works/test", 404, "Not Found", None, None)
        with patch.object(core, "_fetch_json", side_effect=error):
            result = core.lookup_crossref_doi_data("10.1234/x")
        self.assertEqual(result["status"], "not_found_in_crossref")

    def test_gap_evidence_requires_traceable_search_and_studies(self):
        result = core.check_gap_evidence_data(json.dumps({"candidate_gap": "a narrower question"}))
        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("search_log", result["missing_fields"])
        self.assertEqual(result["evidence_verification_status"], "not_assessed_by_tool")


class ModelPlanTests(unittest.TestCase):
    def test_complete_proposal_does_not_claim_statistical_validity(self):
        result = core.check_model_plan_data(json.dumps(valid_plan()))
        self.assertEqual(result["status"], "ready_for_data_validation")
        self.assertEqual(result["statistical_validity_status"], "not_assessed")
        self.assertEqual(result["data_validation_status"], "not_run")

    def test_invalid_outcome_type_and_missing_formula_do_not_pass(self):
        plan = valid_plan()
        plan["outcome"]["type"] = "unknown_type"
        del plan["model_formula"]
        result = core.check_model_plan_data(json.dumps(plan))
        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("model_formula", result["missing_fields"])
        self.assertIn("outcome.type is unsupported", result["invalid_fields"])

    def test_wrong_types_and_conditional_fields_do_not_pass(self):
        plan = valid_plan()
        plan["controls"] = "age"
        plan["standard_errors"] = {"method": "clustered"}
        plan["sampling_design"] = {"kind": "complex_survey"}
        plan["causal_claim"] = True
        result = core.check_model_plan_data(json.dumps(plan))
        self.assertEqual(result["status"], "needs_revision")
        self.assertTrue(any("controls" in item for item in result["invalid_fields"]))
        self.assertIn("standard_errors.cluster_level", result["missing_fields"])
        self.assertIn("identification_assumptions", result["missing_fields"])
        self.assertIn("sampling_design.weight_plan", result["missing_fields"])


class CsvBoundaryTests(unittest.TestCase):
    def test_unconfigured_and_outside_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as approved, tempfile.TemporaryDirectory() as outside:
            file = Path(outside) / "private.csv"
            file.write_text("x\na\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(core.profile_csv_variables_data(str(file), ["x"])["error"],
                                 "data_directory_not_configured")
            with patch.dict(os.environ, {"RESEARCH_DATA_DIR": approved}):
                self.assertEqual(core.profile_csv_variables_data(str(file), ["x"])["error"],
                                 "csv_path_outside_authorized_directory")

    def test_symlink_outside_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as approved, tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "private.csv"
            target.write_text("x\na\n", encoding="utf-8")
            link = Path(approved) / "link.csv"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with patch.dict(os.environ, {"RESEARCH_DATA_DIR": approved}):
                self.assertEqual(core.profile_csv_variables_data(str(link), ["x"])["error"],
                                 "csv_path_outside_authorized_directory")

    def test_missing_codes_suppression_and_exact_limit(self):
        with tempfile.TemporaryDirectory() as approved:
            file = Path(approved) / "sample.csv"
            file.write_text("phone,area\nsmart,urban\nsmart,urban\nsmart,urban\nsmart,urban\nsmart,urban\nNA,rural\n",
                            encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_DATA_DIR": approved}):
                profile = core.profile_csv_variables_data(str(file), ["phone"], 6, {"phone": ["NA"]})
                cells = core.count_group_cells_data(str(file), ["phone", "area"], 6,
                                                    {"phone": ["NA"]})
                limited = core.profile_csv_variables_data(str(file), ["phone"], 5)
        self.assertEqual(profile["columns"]["phone"]["missing"], 1)
        self.assertFalse(profile["truncated_by_row_limit"])
        self.assertFalse(cells["truncated_by_row_limit"])
        self.assertEqual(cells["incomplete_rows"], 1)
        self.assertTrue(limited["truncated_by_row_limit"])
        self.assertIn("file order may bias", limited["note"])

    def test_rare_categories_and_cells_are_suppressed(self):
        with tempfile.TemporaryDirectory() as approved:
            file = Path(approved) / "sample.csv"
            file.write_text("phone,area\nsmart,urban\nsmart,urban\nbasic,rural\n", encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_DATA_DIR": approved}):
                profile = core.profile_csv_variables_data(str(file), ["phone"])
                groups = core.count_group_cells_data(str(file), ["phone", "area"])
        self.assertTrue(profile["columns"]["phone"]["counts_suppressed"])
        self.assertIsNone(profile["columns"]["phone"]["value_counts_if_10_or_fewer_levels"])
        self.assertTrue(groups["cells_suppressed"])
        self.assertIsNone(groups["cells"])

    def test_high_cardinality_groups_stop_without_disclosing_values(self):
        with tempfile.TemporaryDirectory() as approved:
            file = Path(approved) / "sample.csv"
            file.write_text("a,b\n" + "".join(f"{i},x\n" for i in range(101)), encoding="utf-8")
            with patch.dict(os.environ, {"RESEARCH_DATA_DIR": approved}):
                result = core.count_group_cells_data(str(file), ["a", "b"])
        self.assertEqual(result["error"], "too_many_group_combinations")
        self.assertNotIn("cells", result)


class McpIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(__import__("importlib").util.find_spec("mcp") is not None,
                         "install requirements.txt to run MCP integration tests")
    def test_stdio_launch_from_mcp_json_and_call(self):
        from mcp import Client, StdioServerParameters

        config = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
        spec = config["mcpServers"]["research-workflow-tools"]
        args = [arg.replace("${PLUGIN_ROOT}", str(ROOT)) for arg in spec["args"]]

        async def inspect():
            env = {"PYTHONPATH": os.environ["PYTHONPATH"]} if os.environ.get("PYTHONPATH") else None
            params = StdioServerParameters(command=spec["command"], args=args,
                                           cwd=str(ROOT), env=env)
            async with Client(params) as client:
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                result = await client.call_tool("check_model_plan", {"plan_json": json.dumps(valid_plan())})
                return names, result

        names, result = asyncio.run(inspect())
        self.assertEqual(names, {
            "search_openalex", "search_crossref", "search_literature", "lookup_crossref_doi",
            "check_gap_evidence", "profile_csv_variables", "count_group_cells", "check_model_plan",
        })
        self.assertFalse(result.is_error)
        payload = result.structured_content or json.loads(result.content[0].text)
        self.assertEqual(payload["status"], "ready_for_data_validation")


if __name__ == "__main__":
    unittest.main()

