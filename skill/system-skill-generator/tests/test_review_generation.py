"""Synthetic records only. No actual user feedback or target business execution."""
import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("review_generation", Path(__file__).parents[1]/"scripts/review_generation.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def make_record():
    return {
        "schema_version": "1.0", "run_id": "SYNTHETIC-001", "revision": 1,
        "created_at": "2026-10-17T12:00:00+08:00",
        "generator": {"id": "system-skill-generator", "version": "1.0.0"},
        "request": {"summary": "虚构创建请求，仅验证记录协议", "evidence": "虚构夹具，不是实际用户请求"},
        "generated_skill": {"id": "test-example-skill", "display_name": "测试：虚构例子", "version": "1.0.0"},
        "requirements": [
            {"id": "U01", "text": "单一目的", "origin": "explicit", "status": "met",
             "reason": "仅虚构作者结构审阅", "evidence": ["虚构SKILL职责位置"]},
            {"id": "U02", "text": "查看入口", "origin": "explicit", "status": "partial",
             "reason": "虚构查看方式尚缺例子", "evidence": ["虚构待补位置"]}],
        "checks": [{"id": "CHK-1", "kind": "structure", "status": "pass", "reason": "虚构检查",
                    "evidence": ["虚构结构输出，不是实际验证"]},
                   {"id": "CHK-2", "kind": "target_use", "status": "not_run",
                    "reason": "没有真实使用，不自行试业务", "evidence": []}],
        "artifacts": [{"id": "ART-1", "kind": "archive", "ref": "虚构不存在的文件.zip", "sha256": None}],
        "issues": [{"id": "Q-1", "description": "虚构待补查看示例", "status": "open", "evidence": []}],
        "feedback": [], "usage": [], "benefit_measurements": [], "improvement_proposals": []
    }


class GenerationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/"skill-generation-record.json"
        self.record = make_record()
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.record, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self):
        return mod.summarize(mod.load(self.path))

    def feedback(self, subject="generated_skill", value=True):
        return {"id": "FB-1", "subject": subject, "subject_version": self.record[subject]["version"],
                "at": "2026-10-18T10:00:00+08:00", "comment": "仅虚构反馈原意",
                "evidence": "虚构来源，不是真实反馈", "ratings": {"readable": value}}

    def test_checks_are_not_user_effect(self):
        summary = self.check()
        self.assertEqual(summary["check_counts"]["pass"], 1)
        self.assertEqual(summary["usage"]["generated_skill"]["status"], "尚无使用记录")
        self.assertTrue(all(v["status"] == "未评价" and v["rated"] == 0 for s in summary["ratings"].values() for v in s.values()))
        self.assertEqual(len(summary["requirements_open"]), 1)
        self.assertEqual(len(summary["checks_failed_or_not_run"]), 1)

    def test_whole_comment_does_not_score_requirements(self):
        feedback = self.feedback()
        feedback["ratings"] = {}
        self.record["feedback"] = [feedback]
        self.save()
        summary = self.check()
        self.assertEqual(len(summary["feedback_events"]), 1)
        self.assertEqual(summary["ratings"]["generated_skill"]["readable"]["rated"], 0)
        self.assertEqual(summary["requirement_counts"], {"met": 1, "partial": 1})

    def test_two_subjects_never_mixed(self):
        first = self.feedback("generator", True)
        second = self.feedback("generated_skill", False)
        second["id"] = "FB-2"
        self.record["feedback"] = [first, second]
        self.save()
        values = self.check()["ratings"]
        self.assertIs(values["generator"]["readable"]["value"], True)
        self.assertIs(values["generated_skill"]["readable"]["value"], False)

    def test_feedback_history_and_withdrawal(self):
        first = self.feedback()
        later = copy.deepcopy(first)
        later.update(id="FB-2", at="2026-10-18T11:00:00+08:00", ratings={"readable": None})
        self.record["feedback"] = [first, later]
        self.save()
        summary = self.check()
        self.assertEqual(summary["ratings"]["generated_skill"]["readable"]["status"], "未评价")
        self.assertEqual(len(summary["feedback_events"]), 2)

    def test_old_feedback_cannot_migrate(self):
        event = self.feedback()
        event["subject_version"] = "0.9.0"
        self.record["feedback"] = [event]
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_feedback_requires_real_source(self):
        event = self.feedback()
        event["evidence"] = ""
        self.record["feedback"] = [event]
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_string_rating_not_true_boolean(self):
        self.record["feedback"] = [self.feedback(value="true")]
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_usage_needs_evidence(self):
        self.record["usage"] = [{"id": "USE-1", "subject": "generated_skill", "subject_version": "1.0.0",
                                 "at": "2026-10-18T12:00:00+08:00", "scope": "虚构范围",
                                 "result": "pass", "evidence": []}]
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_usage_is_scoped_to_target_only(self):
        self.record["usage"] = [{"id": "USE-1", "subject": "generated_skill", "subject_version": "1.0.0",
                                 "at": "2026-10-18T12:00:00+08:00", "scope": "虚构范围",
                                 "result": "blocked", "evidence": ["仅虚构阻塞记录"]}]
        self.save()
        summary = self.check()
        self.assertEqual(summary["usage"]["generated_skill"]["counts"], {"blocked": 1})
        self.assertEqual(summary["usage"]["generator"]["status"], "尚无使用记录")

    def test_unmeasured_benefit_not_accepted(self):
        self.record["benefit_measurements"] = [{"subject": "generator", "metric": "耗时",
                                              "before": None, "after": 1, "unit": "分钟",
                                              "scope": "虚构可比范围", "evidence": "仅虚构"}]
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_met_requirement_needs_evidence(self):
        self.record["requirements"][0]["evidence"] = []
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()

    def test_duplicate_batch_not_double_counted(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main([str(self.path), str(self.path)]), 2)

    def test_read_only_and_no_artifact_loading(self):
        self.record["artifacts"][0]["ref"] = str(Path(self.temp.name)/"must-not-read-or-run.py")
        self.save()
        before = self.path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main([str(self.path), "--format", "json"]), 0)
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((Path(self.temp.name)/"must-not-read-or-run.py").exists())

    def test_multiple_versions_stay_separate(self):
        other = copy.deepcopy(self.record)
        other["run_id"] = "SYNTHETIC-002"
        other["generated_skill"]["version"] = "2.0.0"
        second = self.path.with_name("other.json")
        second.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(mod.main([str(self.path), str(second), "--format", "json"]), 0)
        values = json.loads(output.getvalue())
        self.assertEqual([v["generated_skill"]["version"] for v in values], ["1.0.0", "2.0.0"])
        self.assertEqual(len(values), 2)

    def test_unknown_creator_version_is_honest(self):
        self.record["generator"]["version"] = None
        self.save()
        self.assertIsNone(self.check()["generator"]["version"])

    def test_naive_time_and_boolean_revision_rejected(self):
        self.record["created_at"] = "2026-10-17T12:00:00"
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()
        self.record["created_at"] = "2026-10-17T12:00:00+08:00"
        self.record["revision"] = True
        self.save()
        with self.assertRaises(mod.Invalid):
            self.check()


if __name__ == "__main__":
    unittest.main()
