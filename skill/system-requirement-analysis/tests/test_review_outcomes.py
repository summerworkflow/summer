"""虚构记录的行为测试；不访问业务环境或收集真实反馈。"""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_outcomes.py"
SPEC = importlib.util.spec_from_file_location("review_outcomes", SCRIPT)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def question(qid="Q001", status="open"):
    return {
        "id": qid, "kind": "rule_missing", "title": "失败后怎样继续？",
        "scenario": "虚构例子：单据保存后，后续申请页面未打开。",
        "uncertainty": "材料只写了成功流程。",
        "question": "后续申请页面未打开时，用户从哪里继续处理已保存的单据？",
        "owner_role": "开发", "recommendation": "建议先核对现有流程，未确认。",
        "impact": "只影响失败恢复分支。",
        "source_refs": [{"source_id": "S1", "location": "第2节"}],
        "status": status,
        "resolution": {"answer": "", "evidence": "", "applied_to": [], "reason": ""},
        "feedback": {"understood": None, "answerable": None, "useful": None, "evidence": ""},
        "history": [],
    }


def record(run_id="SYNTHETIC-001", version="1.0.0"):
    return {
        "schema_version": "1.0", "skill_id": "system-requirement-analysis",
        "skill_version": version, "run_id": run_id, "requirement": "虚构测试需求",
        "revision": 1, "created_at": "2026-10-16T15:00:00+08:00",
        "sources": [{"id": "S1", "path": "虚构材料.md", "version": "V1", "read_status": "read"}],
        "coverage": [{"area": "失败恢复", "status": "partial", "note": "未取得最终字段表"}],
        "questions": [question()], "benefit_measurements": [], "improvement_proposals": [],
    }


class OutcomeTests(unittest.TestCase):
    def test_no_feedback_is_unknown_not_success(self):
        result = review.summarize([record()])
        stats = result["groups"][0]["feedback"]["understood"]
        self.assertIsNone(stats["percent"])
        self.assertEqual((stats["evaluated"], stats["unknown"]), (0, 1))
        self.assertIn("尚不能判断", review.render_markdown(result))

    def test_answer_requires_real_evidence(self):
        data = record()
        data["questions"][0]["status"] = "answered"
        data["questions"][0]["resolution"]["answer"] = "虚构答案"
        with self.assertRaisesRegex(ValueError, "确认依据"):
            review.summarize([data])

    def test_applied_requires_document_reference(self):
        data = record()
        item = data["questions"][0]
        item["status"] = "applied"
        item["resolution"].update(answer="虚构答案", evidence="虚构评审答复")
        with self.assertRaisesRegex(ValueError, "制品位置"):
            review.summarize([data])

    def test_already_documented_is_not_successful_answer(self):
        data = record()
        item = data["questions"][0]
        item["status"] = "not_issue"
        item["resolution"].update(reason="原需求已经写明", evidence="虚构材料第3节")
        group = review.summarize([data])["groups"][0]
        self.assertEqual(group["answer_progress"]["eligible"], 0)
        self.assertEqual(group["answer_progress"]["answered"], 0)
        self.assertIsNone(group["answer_progress"]["percent"])
        self.assertEqual(group["status_counts"]["not_issue"], 1)

    def test_deferred_is_still_unanswered(self):
        data = record()
        item = data["questions"][0]
        item["status"] = "deferred"
        item["resolution"].update(reason="暂不进入本轮决定", evidence="虚构项目决定")
        group = review.summarize([data])["groups"][0]
        self.assertEqual(group["answer_progress"]["eligible"], 1)
        self.assertEqual(len(group["runs"][0]["pending"]), 1)

    def test_feedback_denominator_excludes_unknown(self):
        data = record()
        data["questions"] = [question("Q001"), question("Q002"), question("Q003")]
        data["questions"][0]["feedback"].update(understood=True, evidence="虚构用户反馈A")
        data["questions"][1]["feedback"].update(understood=False, evidence="虚构用户反馈B")
        stats = review.summarize([data])["groups"][0]["feedback"]["understood"]
        self.assertEqual((stats["positive"], stats["negative"], stats["unknown"]), (1, 1, 1))
        self.assertEqual(stats["percent"], 50.0)

    def test_feedback_cannot_be_invented_without_source(self):
        data = record()
        data["questions"][0]["feedback"]["useful"] = True
        with self.assertRaisesRegex(ValueError, "反馈来源"):
            review.summarize([data])

    def test_overall_feedback_does_not_fabricate_per_question_ratings(self):
        data = record()
        data["overall_feedback"] = [
            {"comment": "虚构反馈：整份清单仍然看不懂。", "evidence": "虚构用户答复"}
        ]
        summary = review.summarize([data])
        group = summary["groups"][0]
        self.assertIsNone(group["feedback"]["understood"]["percent"])
        self.assertEqual(group["feedback"]["understood"]["unknown"], 1)
        self.assertIn("整份清单仍然看不懂", review.render_markdown(summary))

    def test_benefit_record_cannot_override_owning_run(self):
        data = record()
        data["benefit_measurements"] = [{
            "run_id": "OTHER-RUN", "metric": "澄清耗时", "before": 40, "after": 25,
            "unit": "分钟", "scope": "虚构可比范围", "evidence": "虚构计时记录",
        }]
        group = review.summarize([data])["groups"][0]
        self.assertEqual(group["benefit_measurements"][0]["run_id"], data["run_id"])

    def test_integer_is_not_boolean_feedback(self):
        data = record()
        data["questions"][0]["feedback"].update(understood=1, evidence="虚构评价")
        with self.assertRaisesRegex(ValueError, "true/false/null"):
            review.summarize([data])

    def test_unread_source_is_material_request(self):
        data = record()
        data["sources"][0]["read_status"] = "unread"
        data["questions"][0].update(kind="material_needed", status="waiting_material")
        group = review.summarize([data])["groups"][0]
        self.assertEqual(group["status_counts"]["waiting_material"], 1)
        self.assertEqual(len(group["runs"][0]["unread_sources"]), 1)

    def test_unread_source_cannot_prove_rule_gap(self):
        data = record()
        data["sources"][0]["read_status"] = "unread"
        with self.assertRaisesRegex(ValueError, "未读材料"):
            review.summarize([data])

    def test_conflict_needs_two_locatable_sources(self):
        data = record()
        data["questions"][0]["kind"] = "rule_conflict"
        with self.assertRaisesRegex(ValueError, "两处已读依据"):
            review.summarize([data])
        data["questions"][0]["source_refs"].append({"source_id": "S1", "location": "第4节"})
        self.assertEqual(review.summarize([data])["groups"][0]["question_count"], 1)

    def test_question_ids_cannot_repeat(self):
        data = record()
        data["questions"].append(deepcopy(data["questions"][0]))
        with self.assertRaisesRegex(ValueError, "问题编号重复"):
            review.summarize([data])

    def test_same_run_cannot_be_counted_twice(self):
        data = record()
        with self.assertRaisesRegex(ValueError, "run_id重复"):
            review.summarize([data, deepcopy(data)])

    def test_versions_are_separate(self):
        summary = review.summarize([record("A", "1.0.0"), record("B", "1.1.0")])
        self.assertEqual([item["skill_version"] for item in summary["groups"]], ["1.0.0", "1.1.0"])
        self.assertEqual([item["run_count"] for item in summary["groups"]], [1, 1])

    def test_answered_is_not_applied_or_tested(self):
        data = record()
        item = data["questions"][0]
        item["status"] = "answered"
        item["resolution"].update(answer="虚构已确认答案", evidence="虚构评审答复")
        group = review.summarize([data])["groups"][0]
        self.assertEqual(group["answer_progress"]["answered"], 1)
        self.assertEqual(group["status_counts"]["applied"], 0)
        self.assertEqual(len(group["runs"][0]["answered_not_applied"]), 1)

    def test_empty_question_list_does_not_create_hundred_percent(self):
        data = record()
        data["questions"] = []
        group = review.summarize([data])["groups"][0]
        self.assertIsNone(group["answer_progress"]["percent"])
        self.assertIsNone(group["feedback"]["understood"]["percent"])
        self.assertTrue(group["runs"][0]["coverage_gaps"])

    def test_benefit_claim_requires_baseline_and_evidence(self):
        data = record()
        data["benefit_measurements"] = [{"metric": "耗时", "before": 40, "after": 25, "unit": "分钟"}]
        with self.assertRaisesRegex(ValueError, "收益记录缺少"):
            review.summarize([data])

    def test_timezone_is_required(self):
        data = record()
        data["created_at"] = "2026-10-16T15:00:00"
        with self.assertRaisesRegex(ValueError, "时区"):
            review.summarize([data])

    def test_cli_is_read_only_and_can_return_json(self):
        with tempfile.TemporaryDirectory(prefix="requirement-analysis-test-") as temp:
            path = Path(temp) / "analysis-record.json"
            original = json.dumps(record(), ensure_ascii=False).encode("utf-8")
            path.write_bytes(original)
            output = io.StringIO()
            with redirect_stdout(output):
                code = review.main([str(path), "--format", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(json.loads(output.getvalue())["groups"][0]["run_count"], 1)
            self.assertEqual([item.name for item in Path(temp).iterdir()], ["analysis-record.json"])

    def test_cli_invalid_record_fails_without_summary(self):
        with tempfile.TemporaryDirectory(prefix="requirement-analysis-test-") as temp:
            path = Path(temp) / "analysis-record.json"
            path.write_text('{"schema_version": "unknown"}', encoding="utf-8")
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = review.main([str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("不支持的schema_version", error.getvalue())


if __name__ == "__main__":
    unittest.main()
