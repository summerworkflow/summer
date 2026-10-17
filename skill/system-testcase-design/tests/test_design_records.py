"""Synthetic, isolated acceptance checks. No real cases, feedback or execution."""
import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("design_records", Path(__file__).parents[1] / "scripts/design_records.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def make_bundle(root):
    """Runnable protocol example; every business fact here is fictitious."""
    bodies = {
        "TC-001": """### TC-001 并发付款仅一次资金效果（虚构）
目标与依据：R1；防止并发重复扣款。底线BL-001。
前置：PREP-ROOT；两名有权操作者、同一已审批未付款对象。
数据：虚构DATA-1，单轮独占1笔金额100；两请求指向同一稳定ID。
准备方案：合法新建付款对象→审批→回读未付及无进行中请求，停在付款前。
步骤：1. 两请求完成资格检查；2. 同时释放提交屏障；3. 核对同付款的最终结果。
断言A1：只有1次100的资金效果，取同操作标识和资金记录。
断言A2：一次成功完成及正确原付款归属，其他余额关系未变。
证据：受控并发入口、原请求标识、只读资金与完成记录；页面提示不证明幂等。
影响：虚构隔离账本，保留异常现场，无真实付款。设计已明确，准备未核实，未执行。""",
        "TC-002": """### TC-002 原币折算方向（虚构）
目标与依据：R2；防止汇率倒乘。风险定级及外部替代未知，仅候选。
前置：PREP-CHILD；有权用户及独占原币来源。
数据：虚构DATA-2，720CNY、1USD=6CNY，每轮独占1组。
准备方案：合法源对象→有效金额→本对象汇率，回读720/6，停在查看前。
步骤：打开该对象经营金额并读取原币、汇率、USD。
断言A1：折120USD，原币720未反写；以独立除法核对并取业务记录。
影响：只读，无需清理。设计已明确，准备未核实，未执行。""",
        "TC-003": """### TC-003 普通列配置（虚构）
目标与依据：R3；验证列顺序。即便旧标P0也没有已成立重大后果。
前置：有查看权及个人配置，不需要新造业务对象。
步骤：移动普通列，确认并重进。
断言A1：顺序保持，其余业务数据未写；页面前后截图。
影响：恢复个人配置。设计已明确，准备未核实，未执行。"""
    }
    shared = {"PREP-ROOT": "## 付款前置\n依赖PREP-CHILD；准备独占付款对象及受控请求屏障，不执行真实付款。",
              "PREP-CHILD": "## 共有证据条件\n虚构测试夹具，数据和记录都在临时目录，不证明真实系统能力。"}
    lines = ["# 全部测试用例（虚构）", "", "范围仅为本自测夹具，不是项目结论。"]
    for key, body in shared.items():
        lines += ["", f"<!-- SHARED {key} BEGIN -->", body, f"<!-- SHARED {key} END -->"]
    for key, body in bodies.items():
        lines += ["", f"<!-- CASE {key} BEGIN -->", body, f"<!-- CASE {key} END -->"]
    full = ("\n".join(lines) + "\n").encode("utf-8")
    (root / "全部测试用例.md").write_bytes(full)
    cases = []
    for n, (key, body) in enumerate(bodies.items(), 1):
        classification = ["indispensable", "candidate", "not_bottomline"][n-1]
        cases.append({"id": key, "title": body.splitlines()[0], "case_ref": "全部测试用例.md的"+key,
                      "fingerprint": mod.fingerprint(body), "priority": "P0", "rule_ids": [f"R{n}"],
                      "assertion_ids": ["A1", "A2"] if n == 1 else ["A1"], "design_status": "complete",
                      "shared_refs": ["PREP-ROOT"] if n == 1 else ["PREP-CHILD"] if n == 2 else [],
                      "preparation": {"status": "unverified", "environment": None, "build": None, "evidence": []},
                      "bottomline": {"classification": classification, "obligation_ids": [f"BL-00{n}"] if n<3 else [],
                                     "reason": ["虚构政策及明确比较范围下成立", "实际定级及外部替代未知", "无不可接受后果，不按P0入选"][n-1]}})
    obligations = []
    for n in [1, 2]:
        obligations.append({
            "id": f"BL-00{n}", "text": ["同次付款不得重复资金效果", "原币除汇率换USD"][n-1],
            "condition": ["两个有权请求在提交点竞争", "采用1USD=X原币报价"][n-1],
            "scope": "虚构夹具，明确限定比较本3条；不代表任何真实项目",
            "consequence": ["同笔款多扣，损失100", "原币折算导致经营金额错误"][n-1], "rule_ids": [f"R{n}"],
            "risk": {"status": "confirmed" if n == 1 else "assessed", "basis": ["虚构政策S1§风险，损失不可接受"] if n == 1 else []},
            "gap": {"status": "shown", "reason": "其他两例没有该触发和断言", "basis": ["本3例逐条比较，虚构"],
                    "near_cases": [{"case_id": "TC-002" if n == 1 else "TC-001", "comparison": "检验不同目标，无法替代"}]},
            "alternatives": {"inventory": "complete" if n == 1 else "unknown",
                             "scope": "虚构决定仅比较本3例" if n == 1 else "项目外未知",
                             "basis": ["虚构决定S1§范围"] if n == 1 else [],
                             "conclusion": "none_equivalent" if n == 1 else "pending", "checks": []},
            "proof": {"case_id": f"TC-00{n}", "assertion_ids": ["A1", "A2"] if n == 1 else ["A1"],
                      "adequacy": "sufficient", "reason": "业务记录层独立金额与身份检查方案",
                      "evidence_plan": ["同对象稳定ID、金额、版本和最终业务记录"]}})
    record = {"schema_version": "1.0", "skill_id": "system-testcase-design", "skill_version": "2.0.0",
              "design_id": "SYNTHETIC-001", "case_set_version": "1.0.0", "revision": 1,
              "created_at": "2026-10-17T12:00:00+08:00", "requirement": "仅虚构自测", "previous_design_id": None,
              "sources": [{"id": "S1", "path": "虚构需求，不存在真实来源", "version": "fixture-1",
                           "read_status": "read", "sha256": None}],
              "documents": {"full": {"path": "全部测试用例.md", "sha256": mod.sha(full)},
                            "bottomline": {"path": "不可替代的业务底线用例.md"}},
              "rules": [{"id": f"R{n}", "basis_status": "confirmed", "source_refs": [{"source_id": "S1", "location": f"虚构规则{n}"}]} for n in [1,2,3]],
              "shared_dependencies": {"PREP-ROOT": ["PREP-CHILD"]},
              "coverage": [{"rule_id": f"R{n}", "status": "covered", "case_ids": [f"TC-00{n}"], "reason": "仅本虚构目标设计"} for n in [1,2,3]],
              "cases": cases, "obligations": obligations,
              "issues": [{"id": "Q-1", "status": "open", "title": "TC-002缺风险定级和外部验证盘点", "case_ids": ["TC-002"]}],
              "feedback": [], "outcomes": [], "findings": [], "benefit_measurements": [], "improvement_proposals": []}
    path = root / "design-record.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, record


class DesignRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path, self.record = make_bundle(self.root)
        self.build()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.record, ensure_ascii=False, indent=2), encoding="utf-8")

    def build(self):
        r, b, c, o, target = mod.load(self.path)
        target.write_bytes(mod.render(r, b, c, o))

    def test_full_subset_copy_and_shared_dependency_closure(self):
        record, cases, target, _ = mod.inspect(self.path)
        selected = mod.blocks(target.read_text(encoding="utf-8"))
        original = mod.blocks((self.root/"全部测试用例.md").read_text(encoding="utf-8"))
        self.assertEqual(set(selected["CASE"]), {"TC-001", "TC-002"})
        self.assertEqual(selected["CASE"]["TC-001"], original["CASE"]["TC-001"])
        self.assertEqual(set(selected["SHARED"]), {"PREP-ROOT", "PREP-CHILD"})
        summary = mod.review(record, cases)
        self.assertEqual(summary["classification_counts"]["indispensable"], 1)
        self.assertEqual(summary["classification_counts"]["candidate"], 1)
        self.assertEqual(summary["execution_status"], "未执行")
        self.assertTrue(all(r["rated"] == 0 and r["unrated"] == 3 for r in summary["case_feedback"].values()))

    def test_existing_bottomline_is_not_overwritten(self):
        target = self.root/"不可替代的业务底线用例.md"
        target.write_text("原有不同内容", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["build-bottomlines", str(self.path)]), 2)
        self.assertEqual(target.read_text(encoding="utf-8"), "原有不同内容")

    def test_second_document_tampering_rejected(self):
        with (self.root/"不可替代的业务底线用例.md").open("a", encoding="utf-8") as file:
            file.write("擅改断言")
        with self.assertRaises(mod.Invalid):
            mod.inspect(self.path)

    def test_full_document_tampering_rejected(self):
        with (self.root/"全部测试用例.md").open("a", encoding="utf-8") as file:
            file.write("新增未登记设计")
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_updated_file_hash_cannot_hide_changed_case_fingerprint(self):
        full = self.root/"全部测试用例.md"
        full.write_text(full.read_text(encoding="utf-8").replace("只有1次100", "只有2次100"), encoding="utf-8")
        self.record["documents"]["full"]["sha256"] = mod.sha(full.read_bytes())
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_p0_and_unconfirmed_risk_cannot_promote_candidate(self):
        self.record["cases"][1]["bottomline"]["classification"] = "indispensable"
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_weak_proof_cannot_be_formal(self):
        self.record["obligations"][0]["proof"]["adequacy"] = "partial"
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_empty_rule_cannot_make_formal_bottomline(self):
        self.record["obligations"][0]["rule_ids"] = []
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_unread_source_cannot_confirm_rule(self):
        self.record["sources"][0]["read_status"] = "unread"
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_unknown_alternative_cannot_be_formal(self):
        self.record["obligations"][0]["alternatives"]["checks"] = [
            {"kind": "automation", "ref": "尚未取得的回归", "status": "unverified", "reason": "实际断言未知", "evidence": []}]
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_effective_alternative_conflicts_with_none(self):
        self.record["obligations"][0]["alternatives"]["checks"] = [
            {"kind": "automation", "ref": "虚构同条件回归", "status": "effective", "reason": "同触发和业务证据", "evidence": ["虚构审阅记录"]}]
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def outcome(self, result="pass", build="build-1"):
        c = self.record["cases"][0]
        return {"id": "ATT-1", "case_id": c["id"], "case_fingerprint": c["fingerprint"],
                "at": "2026-10-18T10:00:00+08:00", "environment": "synthetic", "build": build,
                "result": result, "evidence": ["虚构执行记录，非真实反馈"], "preflight_evidence": ["虚构前置"],
                "assertions": [{"id": aid, "status": "pass", "actual": 0 if aid == "A1" else False,
                                "evidence": ["虚构实际记录"]} for aid in c["assertion_ids"]]}

    def test_incomplete_assertions_never_pass(self):
        attempt = self.outcome()
        attempt["assertions"].pop()
        self.record["outcomes"] = [attempt]
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_zero_false_actuals_are_not_missing(self):
        self.record["outcomes"] = [self.outcome()]
        self.save()
        record, _, cases, _, _ = mod.load(self.path)
        self.assertEqual(mod.review(record, cases)["outcomes"][0]["latest_per_case"], {"pass": 1})

    def test_old_case_outcome_not_borrowed(self):
        attempt = self.outcome()
        attempt["case_fingerprint"] = "0"*64
        self.record["outcomes"] = [attempt]
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_environments_builds_not_merged(self):
        first = self.outcome()
        later = self.outcome("fail", "build-2")
        later.update(id="ATT-2", at="2026-10-18T11:00:00+08:00")
        later["assertions"][0].update(status="fail", actual=2)
        self.record["outcomes"] = [first, later]
        self.save()
        record, _, cases, _, _ = mod.load(self.path)
        groups = mod.review(record, cases)["outcomes"]
        self.assertEqual([g["latest_per_case"] for g in groups], [{"pass": 1}, {"fail": 1}])
        self.assertEqual(len(record["outcomes"]), 2)

    def feedback(self, scope="suite", rated=True):
        event = {"id": "FB-1", "scope": scope, "at": "2026-10-18T12:00:00+08:00",
                 "comment": "仅虚构评价", "evidence": "仅虚构记录", "ratings": {"readable": rated}}
        if scope == "case":
            event.update(case_id="TC-001", case_fingerprint=self.record["cases"][0]["fingerprint"])
        return event

    def test_suite_feedback_does_not_rate_each_case(self):
        self.record["feedback"] = [self.feedback()]
        self.save()
        r, _, c, _, _ = mod.load(self.path)
        summary = mod.review(r,c)
        self.assertEqual(summary["case_feedback"]["readable"]["rated"], 0)
        self.assertEqual(len(summary["overall_feedback"]), 1)

    def test_feedback_revisions_preserve_denominator_and_history(self):
        first = self.feedback("case")
        later = copy.deepcopy(first)
        later.update(id="FB-2", at="2026-10-18T13:00:00+08:00", ratings={"readable": False})
        self.record["feedback"] = [first, later]
        self.save()
        r, _, c, _, _ = mod.load(self.path)
        value = mod.review(r,c)["case_feedback"]["readable"]
        self.assertEqual((value["positive"], value["rated"], value["unrated"]), (0,1,2))
        self.assertEqual(len(r["feedback"]), 2)

    def test_read_only_review_does_not_modify_artifacts(self):
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["review", str(self.path), "--format", "json"]), 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_duplicate_batch_not_double_counted(self):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mod.main(["review", str(self.path), str(self.path)]), 2)

    def test_new_alternative_is_visible_without_rewriting_history(self):
        self.record["findings"] = [{"id": "F-1", "kind": "new_alternative", "status": "reported",
                                   "case_ids": ["TC-001"], "description": "虚构新发现的替代待核验",
                                   "evidence": "虚构反馈原文，不是已确认有效"}]
        self.save()
        r, _, c, _, _ = mod.load(self.path)
        summary = mod.review(r,c)
        self.assertEqual(len(summary["bottomline_findings"]), 1)
        self.assertEqual(summary["classification_counts"]["indispensable"], 1)

    def test_document_path_cannot_escape_batch(self):
        self.record["documents"]["bottomline"]["path"] = "../outside.md"
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_shared_dependency_cycle_rejected(self):
        self.record["shared_dependencies"]["PREP-CHILD"] = ["PREP-ROOT"]
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)

    def test_ready_requires_real_preflight_evidence(self):
        self.record["cases"][0]["preparation"]["status"] = "ready"
        self.save()
        with self.assertRaises(mod.Invalid):
            mod.load(self.path)


if __name__ == "__main__":
    unittest.main()
