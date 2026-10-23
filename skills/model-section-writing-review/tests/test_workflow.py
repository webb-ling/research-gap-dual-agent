import importlib.util
import sys
import tempfile
import json
import shutil
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "scripts/workflow.py"
spec = importlib.util.spec_from_file_location("workflow", path)
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)


def checks(blocked=False):
    return {"items": [{"id": i, "status": "缺失" if blocked and i == "S1" else "满足",
                       "evidence": "对应素材位置"} for i in sorted(w.CHECK_IDS)],
            "requests": [{"title": "符号定义", "type": "缺失", "existing": "出现符号",
                          "problem": "没有定义", "question": "请定义符号",
                          "basis": "尚无定义", "impact": "无法解释"}]
            if blocked else []}


def review(kind=None):
    return {"dimensions": {i: {"ok": kind is None, "evidence": "审核依据"}
                           for i in w.DIMENSIONS},
            "issues": [] if kind is None else [{"kind": kind, "blocking": True,
                "location": "第2段", "basis": "与确认素材不符", "impact": "含义不明确",
                "direction": "按素材修改", "dimensions": sorted(w.DIMENSIONS)}]}


class Fake:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call(self, role, task, context):
        self.calls.append(role)
        return self.responses.pop(0)


def draft_steps():
    return [checks(), {"paragraphs": [{"id": "P1", "purpose": "完整模型",
              "source": "当前素材", "instructions": "解释模型", "check_ids": sorted(w.CHECK_IDS)}]},
            {"text": "模型正文", "source": "当前素材"}, {"text": "整合正文"}]


class WorkflowTests(unittest.TestCase):
    def test_full_route_and_checkpoint(self):
        backend = Fake(draft_steps() + [review()])
        with tempfile.TemporaryDirectory() as d:
            result = w.run_until_wait(w.WorkflowState("用户原稿"), backend, Path(d))
            self.assertEqual(result.stage, w.Stage.DONE)
            self.assertEqual(backend.calls, ["A", "W1", "W2:P1", "W3", "R"])
            self.assertEqual(w.load_checkpoint(Path(d)), result)
            self.assertEqual((Path(d) / "result.md").read_text(), "整合正文")

    def test_wait_and_user_reply(self):
        backend = Fake([checks(True)])
        state = w.step(w.WorkflowState("原稿"), backend)
        self.assertEqual(state.stage, w.Stage.WAIT)
        self.assertEqual(w.step(state, backend), state)
        self.assertEqual(len(backend.calls), 1)
        updated = w.provide_user_reply(state, "该符号表示个人")
        self.assertEqual(updated.stage, w.Stage.CHECK)
        self.assertEqual(updated.material_version, 2)
        self.assertIn("原稿", updated.material)
        self.assertEqual(state.material, "原稿")

    def test_revision_requires_reviewer(self):
        backend = Fake(draft_steps() + [review("writing"),
                       {"text": "修订稿", "responses": [{"issue": "问题1", "action": "已修正"}]},
                       review()])
        with tempfile.TemporaryDirectory() as d:
            result = w.run_until_wait(w.WorkflowState("原稿"), backend, Path(d))
        self.assertEqual(result.stage, w.Stage.DONE)
        self.assertEqual(result.draft_version, 2)
        self.assertEqual(backend.calls[-3:], ["R", "W", "R"])

    def test_material_problem_returns_to_A(self):
        backend = Fake(draft_steps() + [review("material"), checks(True)])
        with tempfile.TemporaryDirectory() as d:
            result = w.run_until_wait(w.WorkflowState("原稿"), backend, Path(d))
        self.assertEqual(result.stage, w.Stage.WAIT)
        self.assertEqual(result.draft, "整合正文")
        self.assertIsNone(result.checked_version)
        self.assertEqual(backend.calls[-2:], ["R", "A"])

    def test_invalid_check_does_not_commit(self):
        invalid = checks()
        invalid["items"][0]["status"] = "不适用"  # M1 is required
        state = w.WorkflowState("原稿")
        with self.assertRaises(ValueError):
            w.step(state, Fake([invalid]))
        self.assertEqual(state.stage, w.Stage.CHECK)
        self.assertEqual(state.checks, [])

    def test_failed_review_cannot_pass_without_issues(self):
        invalid = review()
        invalid["dimensions"]["fidelity"]["ok"] = False
        state = w.WorkflowState("原稿", stage=w.Stage.REVIEW,
                                draft="正文", draft_material_version=1)
        with self.assertRaises(ValueError):
            w.step(state, Fake([invalid]))
        self.assertEqual(state.stage, w.Stage.REVIEW)

    def test_step_budget_is_not_approval(self):
        with tempfile.TemporaryDirectory() as d:
            state = w.run_until_wait(w.WorkflowState("原稿"), Fake([checks()]), Path(d), max_steps=1)
        self.assertEqual(state.stage, w.Stage.PLAN)

    def test_writer_material_gap_routes_to_checker(self):
        for stage in (w.Stage.PLAN, w.Stage.WRITE, w.Stage.COHERE):
            state = w.WorkflowState("原稿", stage=stage, checked_version=1,
                plan=[{"id": "P1"}])
            result = w.step(state, Fake([{"needs_material": "符号定义存在冲突"}]))
            self.assertEqual(result.stage, w.Stage.CHECK)
            self.assertIsNone(result.checked_version)
            self.assertEqual(result.draft_version, 0)

    def test_failed_dimension_requires_matching_issue(self):
        value = review("writing")
        value["issues"][0]["dimensions"] = ["coverage"]
        state = w.WorkflowState("原稿", stage=w.Stage.REVIEW, draft="正文", draft_material_version=1)
        with self.assertRaises(ValueError):
            w.step(state, Fake([value]))


class RecordingSDK:
    def __init__(self, responses=None):
        self.responses = list(responses or [{}] * 20)
        self.calls = []
        self.sandboxes = []

    def thread_start(self, sandbox):
        self.sandboxes.append(sandbox)
        owner = self

        class Thread:
            def run(self, prompt):
                owner.calls.append(prompt)
                return types.SimpleNamespace(status="completed", final_response=json.dumps(owner.responses.pop(0), ensure_ascii=False))

        return Thread()


def sdk_backend(client, root=ROOT):
    sdk = types.SimpleNamespace(Sandbox=types.SimpleNamespace(read_only="read-only-test"))
    with patch.dict(sys.modules, {"openai_codex": sdk}):
        return w.CodexSDKBackend(client, root)


class RuleLoadingTests(unittest.TestCase):
    def test_interrupted_sdk_turn_cannot_commit_partial_json(self):
        client = RecordingSDK()
        backend = sdk_backend(client)
        class Interrupted:
            def run(self, prompt):
                return types.SimpleNamespace(status="interrupted", final_response='{}')
        backend.threads['A'] = Interrupted()
        with self.assertRaises(RuntimeError):
            backend.call('A', '检查', {})
        self.assertEqual(backend.receipts, [])

    def test_outbound_prompts_contain_actual_role_rules(self):
        client = RecordingSDK()
        backend = sdk_backend(client)
        for role in ("A", "W1", "W2:P1", "W3", "W", "R"):
            backend.call(role, "输出本轮约定JSON", {"material": "本轮作者素材"})
            prompt = client.calls[-1]
            for name in backend.rules.files_for(role):
                self.assertIn((ROOT / name).read_text(), prompt)
            self.assertIn("本轮作者素材", prompt)
        self.assertIn((ROOT / "references/material-request-format.md").read_text(), client.calls[0])
        self.assertNotIn((ROOT / "references/material-request-format.md").read_text(), client.calls[2])
        self.assertIn((ROOT / "references/review-criteria.md").read_text(), client.calls[-1])
        self.assertTrue(all(s == "read-only-test" for s in client.sandboxes))

    def test_same_role_reuses_thread_but_gets_current_material(self):
        client = RecordingSDK()
        backend = sdk_backend(client)
        backend.call("A", "检查", {"material": "第一版材料"})
        backend.call("A", "重查", {"material": "第二版材料"})
        self.assertEqual(len(client.sandboxes), 1)
        self.assertIn("第二版材料", client.calls[-1])
        self.assertNotIn("第一版材料", client.calls[-1])

    def test_changed_or_missing_rules_prevent_sdk_calls(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "skill"
            shutil.copytree(ROOT, root)
            client = RecordingSDK()
            backend = sdk_backend(client, root)
            target = root / "references/writing-framework.md"
            target.write_text(target.read_text() + "\n新规范\n")
            with self.assertRaises(ValueError):
                backend.call("W1", "规划", {})
            self.assertEqual(client.calls, [])
            updated = w.SkillBundle(root)
            prompt, _ = updated.build_prompt("W1", "规划", {})
            self.assertIn("新规范", prompt)
            target.unlink()
            with self.assertRaises(FileNotFoundError):
                w.SkillBundle(root)

    def test_routes_cannot_escape_skill_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "skill"
            shutil.copytree(ROOT, root)
            (Path(d) / "external.md").write_text("不属于Skill的文件")
            manifest = root / "agents/roles.json"
            data = json.loads(manifest.read_text())
            data["roles"]["A"]["references"].append("../external.md")
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                w.SkillBundle(root)

    def test_receipts_saved_and_rule_version_mismatch_rejected(self):
        client = RecordingSDK([checks()])
        backend = sdk_backend(client)
        state = w.step(w.WorkflowState("作者原稿"), backend)
        self.assertEqual(state.rules_digest, backend.rules_digest)
        self.assertEqual(state.audit[-1]["rules"][0]["role"], "A")
        self.assertTrue(state.audit[-1]["rules"][0]["files"])
        changed = Fake([])
        changed.rules_digest = "different-version"
        with self.assertRaises(ValueError):
            w.step(state, changed)
        self.assertEqual(changed.calls, [])


if __name__ == "__main__":
    unittest.main()
