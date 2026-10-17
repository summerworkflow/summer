"""仅使用虚构转换与运行记录；验证汇总行为，不访问实际业务环境。"""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "review_conversion", Path(__file__).resolve().parents[1] / "scripts" / "review_conversion.py")
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def record(cid="SYNTHETIC-001", version="1.0.0"):
    return {
        "schema_version": "1.0", "skill_id": "system-ai-testcase-converter",
        "skill_version": version, "conversion_id": cid, "revision": 1,
        "created_at": "2026-10-17T10:00:00+08:00", "counting_unit": "虚构同粒度业务动作",
        "source_cases": [{
            "id": "MAN-1", "location": "虚构用例第1条", "version": "V1",
            "checkpoints": [{"id": "P1", "text": "修改数量后人工金额保持"}],
            "disposition": "converted", "reason": "", "evidence": "", "excluded_checkpoints": [],
        }],
        "scripts": [],
        "cases": [{
            "id": "AI-1", "title": "人工金额保护", "source_checks": {"MAN-1": ["P1"]},
            "case_ref": "虚构AI执行用例.md#AI-1", "design_status": "complete",
            "basis_status": "confirmed", "basis": "虚构需求R1", "route": "guided_once",
            "setup_required": True, "setup_reason": "需要独占草稿", "bindings": [],
            "assertion_ids": ["A1", "A2"], "missing": ["缺实际脚本"],
            "preflight": {"status": "unverified", "environment": None, "build": None, "evidence": []},
            "feedback": {"understood": None, "usable": None, "evidence": ""},
        }],
        "attempts": [], "overall_feedback": [], "benefit_measurements": [],
        "improvement_proposals": [],
    }


def bind(data, current=False):
    data["scripts"] = [{
        "id": "CAP-1", "path": "虚构脚本.mjs", "entry": "test", "version": "虚构提交",
        "phases": ["prepare", "act", "check"], "disabled": False,
        "verification": {
            "status": "current" if current else "unverified",
            "environment": "虚构环境" if current else None,
            "build": "BUILD-A" if current else None,
            "evidence": ["虚构当前验证记录"] if current else [],
        },
    }]
    case = data["cases"][0]
    case.update(route="script", missing=[], bindings=[{
        "script_id": "CAP-1", "phases": ["prepare", "act", "check"],
        "call_ref": "虚构AI文档中的参数与返回说明",
    }])
    return data


def attempt(aid="T1", result="pass"):
    return {
        "id": aid, "case_id": "AI-1", "environment": "虚构环境", "build": "BUILD-A",
        "result": result, "preflight_evidence": ["虚构本次前置检查"],
        "assertions": [
            {"id": key, "status": "pass", "actual": "虚构实测值", "evidence": ["虚构证据" + key]}
            for key in ("A1", "A2")
        ] if result == "pass" else [],
        "evidence": ["虚构运行日志"], "script_steps": 3, "exploration_steps": 1,
        "human_interventions": 0,
    }


class ConverterTests(unittest.TestCase):
    def test_no_run_or_feedback_cannot_be_called_effective(self):
        group = review.summary([record()])["groups"][0]
        self.assertEqual(group["attempt_count"], 0)
        self.assertIsNone(group["script_step_share"])
        self.assertIsNone(group["feedback"]["understood"]["percent"])
        report = review.render({"groups": [group]})
        self.assertIn("尚未试跑", report)
        self.assertIn("尚不能判断", report)

    def test_dropped_source_checkpoint_is_rejected(self):
        data = record()
        data["source_cases"][0]["checkpoints"].append({"id": "P2", "text": "包干金额"})
        with self.assertRaisesRegex(ValueError, "没有登记去向"):
            review.summary([data])

    def test_split_preserves_all_source_checkpoints(self):
        data = record()
        data["source_cases"][0]["checkpoints"].append({"id": "P2", "text": "包干金额"})
        second = deepcopy(data["cases"][0])
        second.update(id="AI-2", source_checks={"MAN-1": ["P2"]})
        data["cases"].append(second)
        result = review.summary([data])["groups"][0]["conversions"][0]
        self.assertEqual(result["source_checkpoint_count"], 2)
        self.assertEqual(len(result["cases"]), 2)

    def test_unknown_source_checkpoint_is_rejected(self):
        data = record()
        data["cases"][0]["source_checks"] = {"MAN-1": ["NOT-FOUND"]}
        with self.assertRaisesRegex(ValueError, "未知或重复原检查点"):
            review.summary([data])

    def test_pending_rule_cannot_be_script_ready(self):
        data = bind(record())
        data["cases"][0]["basis_status"] = "pending"
        with self.assertRaisesRegex(ValueError, "须标等待确认"):
            review.summary([data])

    def test_missing_action_or_check_binding_is_rejected(self):
        data = bind(record())
        data["cases"][0]["bindings"][0]["phases"] = ["prepare"]
        with self.assertRaisesRegex(ValueError, "缺准备、被测动作或检查"):
            review.summary([data])

    def test_one_script_can_cover_all_three_phases(self):
        group = review.summary([bind(record())])["groups"][0]
        self.assertEqual(group["routes"]["script"], 1)
        self.assertEqual(group["recorded_ready"], 0)

    def test_no_setup_case_does_not_require_fake_data_creation(self):
        data = bind(record())
        case = data["cases"][0]
        case.update(setup_required=False, setup_reason="只读页面，无新造数据")
        case["bindings"][0]["phases"] = ["act", "check"]
        self.assertEqual(review.summary([data])["groups"][0]["routes"]["script"], 1)

    def test_disabled_script_is_not_bound_as_usable(self):
        data = bind(record())
        data["scripts"][0]["disabled"] = True
        with self.assertRaisesRegex(ValueError, "禁用/隔离"):
            review.summary([data])

    def test_invented_script_id_is_rejected(self):
        data = bind(record())
        data["cases"][0]["bindings"][0]["script_id"] = "NOT-FOUND"
        with self.assertRaisesRegex(ValueError, "不存在的脚本"):
            review.summary([data])

    def test_ready_requires_matching_current_environment_and_build(self):
        data = bind(record(), current=True)
        data["cases"][0]["preflight"].update(
            status="ready", environment="虚构环境", build="BUILD-B", evidence=["虚构前置核对"])
        with self.assertRaisesRegex(ValueError, "不匹配"):
            review.summary([data])
        data["cases"][0]["preflight"]["build"] = "BUILD-A"
        self.assertEqual(review.summary([data])["groups"][0]["recorded_ready"], 1)

    def test_historical_script_is_not_current_readiness(self):
        data = bind(record(), current=True)
        data["scripts"][0]["verification"]["status"] = "historical"
        data["cases"][0]["preflight"].update(
            status="ready", environment="虚构环境", build="BUILD-A", evidence=["虚构前置核对"])
        with self.assertRaisesRegex(ValueError, "不匹配"):
            review.summary([data])

    def test_success_without_all_required_assertions_is_rejected(self):
        data = record()
        run = attempt()
        run["assertions"].pop()
        data["attempts"] = [run]
        with self.assertRaisesRegex(ValueError, "未全部有证据通过"):
            review.summary([data])

    def test_success_without_this_attempt_preflight_is_rejected(self):
        data = record()
        run = attempt()
        run["preflight_evidence"] = []
        data["attempts"] = [run]
        with self.assertRaisesRegex(ValueError, "本次前置核实证据"):
            review.summary([data])

    def test_assertion_mismatch_needs_actual_failed_assertion(self):
        data = record()
        data["attempts"] = [attempt(result="assertion_failed")]
        with self.assertRaisesRegex(ValueError, "实际失败断言"):
            review.summary([data])

    def test_retry_success_keeps_first_failure(self):
        data = record()
        data["attempts"] = [attempt("T1", "script_failed"), attempt("T2", "pass")]
        actual = review.summary([data])["groups"][0]["conversions"][0]["actual_runs"][0]
        self.assertEqual(actual["results"], {"script_failed": 1, "pass": 1})
        self.assertEqual(actual["first_results"], {"script_failed": 1})

    def test_runs_are_separated_by_deployment(self):
        data = record()
        other = attempt("T2", "pass")
        other["build"] = "BUILD-B"
        data["attempts"] = [attempt("T1", "setup_failed"), other]
        actual = review.summary([data])["groups"][0]["conversions"][0]["actual_runs"]
        self.assertEqual(len(actual), 2)

    def test_duplicate_conversion_is_not_double_counted(self):
        data = record()
        with self.assertRaisesRegex(ValueError, "conversion_id重复"):
            review.summary([data, deepcopy(data)])

    def test_versions_and_counting_units_are_separate(self):
        one, two, three = record("ONE"), record("TWO", "1.1.0"), record("THREE")
        three["counting_unit"] = "另一种计数粒度"
        self.assertEqual(len(review.summary([one, two, three])["groups"]), 3)

    def test_overall_feedback_does_not_become_per_case_score(self):
        data = record()
        data["overall_feedback"] = [{"comment": "虚构整体反馈：看不懂", "evidence": "虚构用户回复"}]
        report = review.summary([data])
        self.assertIsNone(report["groups"][0]["feedback"]["understood"]["percent"])
        self.assertIn("看不懂", review.render(report))

    def test_rating_requires_real_source(self):
        data = record()
        data["cases"][0]["feedback"]["usable"] = True
        with self.assertRaisesRegex(ValueError, "反馈缺实际来源"):
            review.summary([data])

    def test_benefit_claim_requires_comparable_scope_and_evidence(self):
        data = record()
        data["benefit_measurements"] = [{"metric": "耗时", "before": 30, "after": 10, "unit": "分钟"}]
        with self.assertRaisesRegex(ValueError, "前后对比缺少"):
            review.summary([data])

    def test_cli_reads_only_and_never_executes_registered_scripts(self):
        with tempfile.TemporaryDirectory(prefix="ai-converter-test-") as temp:
            root = Path(temp)
            business = root / "must-not-run.py"
            business.write_text("raise RuntimeError('business script must never run')", encoding="utf-8")
            data = bind(record())
            data["scripts"][0]["path"] = str(business)
            path = root / "conversion-record.json"
            original = json.dumps(data, ensure_ascii=False).encode("utf-8")
            path.write_bytes(original)
            output = io.StringIO()
            with redirect_stdout(output):
                code = review.main([str(path), "--format", "json"])
            self.assertEqual(code, 0)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(json.loads(output.getvalue())["groups"][0]["attempt_count"], 0)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["conversion-record.json", "must-not-run.py"])

    def test_cli_invalid_data_reports_error_without_result(self):
        with tempfile.TemporaryDirectory(prefix="ai-converter-test-") as temp:
            path = Path(temp) / "conversion-record.json"
            path.write_text('{"schema_version":"invalid"}', encoding="utf-8")
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = review.main([str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("schema_version", error.getvalue())


if __name__ == "__main__":
    unittest.main()
