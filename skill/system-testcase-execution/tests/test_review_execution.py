"""Synthetic isolated checks; no real users, business actions or feedback."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_execution.py"
SPEC = importlib.util.spec_from_file_location("review_execution", SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def ledger():
    return {"schema_version": "1.0", "run_id": "DEMO-RUN", "revision": 1,
            "baseline": {"cases_ref": "DEMO-cases@v1", "environment": "DEMO-only", "build": "DEMO-build",
                         "role_scope": "DEMO-org", "authorization_ref": "Synthetic; no business permission"},
            "selected_case_ids": ["TC1"],
            "cases": [{"id": "TC1", "branches": [{"id": "B1", "assertions": [
                {"id": "A1", "basis_ref": "DEMO-rule-1"}, {"id": "A2", "basis_ref": "DEMO-rule-2"}],
                "required_checkpoints": ["identity", "action", "persistence"]}]}],
            "attempts": [], "regression_scope_note": "Synthetic scope, no actual regression policy",
            "regressions": [], "blocker_reviews": []}


def attempt(tid="T1", states=("passed", "passed"), phase="first", prior=None, branch="B1", second=0):
    row = {"id": tid, "case_id": "TC1", "branch_id": branch, "phase": phase,
           "at": "2026-10-18T08:00:%02d+08:00" % second,
           "context_verified": True, "preconditions_verified": True,
           "context_evidence": ["DEMO-context"],
           "checkpoint_evidence": {key: ["DEMO-" + key] for key in ("identity", "action", "persistence")},
           "results": [{"assertion_id": "A" + str(i + 1), "status": state,
                        "actual": "Synthetic observed value" if state in ("passed", "failed") else None,
                        "evidence": ["DEMO-observation"] if state in ("passed", "failed") else [],
                        "reason": "Synthetic explicit missing condition"} for i, state in enumerate(states)]}
    if phase != "first":
        row.update(prior_attempt_id=prior, reason="Synthetic new evidence; no live retry")
    return row


def regression(status="pending"):
    return {"id": "RG1", "kind": "dynamic", "case_id": "TC1", "branch_id": "B1",
            "reason": "Synthetic risk triggered", "status": status}


class ReviewTests(unittest.TestCase):
    def test_plan_never_completes_even_with_manual_true(self):
        data = ledger()
        data["completion_gate"] = True
        result = REVIEW.analyze(data)
        self.assertFalse(result["completion_gate"])
        self.assertEqual(result["latest_counts"]["not_run"], 1)

    def test_complete_pass_has_case_not_attempt_count(self):
        data = ledger()
        data["attempts"] = [attempt()]
        result = REVIEW.analyze(data)
        self.assertTrue(result["completion_gate"])
        self.assertEqual(result["latest_counts"]["passed"], 1)
        self.assertEqual(result["selected_branch_count"], 1)

    def test_pass_requires_actual_evidence(self):
        data = ledger()
        data["attempts"] = [attempt()]
        data["attempts"][0]["results"][0]["evidence"] = []
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)

    def test_pass_requires_independent_basis(self):
        data = ledger()
        data["cases"][0]["branches"][0]["assertions"][0]["basis_ref"] = None
        data["attempts"] = [attempt()]
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)

    def test_pass_requires_current_context_and_preconditions(self):
        for flag in ("context_verified", "preconditions_verified"):
            with self.subTest(flag=flag):
                data = ledger()
                data["attempts"] = [attempt()]
                data["attempts"][0][flag] = False
                with self.assertRaises(ValueError):
                    REVIEW.analyze(data)

    def test_true_flags_cannot_be_numbers(self):
        data = ledger()
        data["attempts"] = [attempt()]
        data["attempts"][0]["context_verified"] = 1
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)

    def test_missing_persistence_downgrades_claim(self):
        data = ledger()
        data["attempts"] = [attempt()]
        del data["attempts"][0]["checkpoint_evidence"]["persistence"]
        result = REVIEW.analyze(data)
        self.assertEqual(result["latest_counts"]["inconclusive"], 1)
        self.assertEqual(result["latest_counts"]["passed"], 0)
        self.assertIn("persistence", result["branches"][0]["latest"]["missing_checkpoints"])

    def test_failure_does_not_hide_unexecuted_assertion(self):
        data = ledger()
        data["attempts"] = [attempt(states=("failed",))]
        result = REVIEW.analyze(data)
        self.assertEqual(result["latest_counts"]["failed"], 1)
        self.assertFalse(result["completion_gate"])
        self.assertEqual(result["branches"][0]["latest"]["missing_assertions"], ["A2"])

    def test_failure_in_one_branch_is_not_cancelled(self):
        data = ledger()
        branch = copy.deepcopy(data["cases"][0]["branches"][0])
        branch["id"] = "B2"
        data["cases"][0]["branches"].append(branch)
        data["attempts"] = [attempt(), attempt("T2", ("failed", "passed"), branch="B2")]
        result = REVIEW.analyze(data)
        self.assertEqual(result["latest_counts"]["failed"], 1)
        self.assertEqual([row["latest"]["verdict"] for row in result["branches"]], ["passed", "failed"])

    def test_different_attempts_cannot_be_stitched(self):
        data = ledger()
        data["attempts"] = [attempt(states=("passed", "blocked")),
                            attempt("T2", ("blocked", "passed"), "retry", "T1", second=1)]
        data["blocker_reviews"] = [{"case_id": "TC1", "branch_id": "B1", "resolution": "retried",
                                    "attempt_id": "T2", "reason": "Synthetic recheck"}]
        result = REVIEW.analyze(data)
        self.assertEqual(result["latest_counts"]["passed"], 0)
        self.assertEqual(result["latest_counts"]["blocked"], 1)

    def test_retry_success_preserves_first_failure(self):
        data = ledger()
        data["attempts"] = [attempt(states=("failed", "passed")),
                            attempt("T2", phase="retry", prior="T1", second=1)]
        result = REVIEW.analyze(data)
        self.assertEqual(result["first_pass_counts"]["failed"], 1)
        self.assertEqual(result["latest_counts"]["passed"], 1)
        self.assertEqual(result["historical_failed_attempt_ids"], ["T1"])

    def test_initial_blocker_needs_final_review(self):
        data = ledger()
        data["attempts"] = [attempt(states=("blocked", "blocked"))]
        result = REVIEW.analyze(data)
        self.assertFalse(result["completion_gate"])
        self.assertEqual(result["unreviewed_initial_blockers"], [{"case_id": "TC1", "branch_id": "B1"}])

    def test_still_blocked_can_close_without_replaying_write(self):
        data = ledger()
        data["attempts"] = [attempt(states=("blocked", "blocked"))]
        data["blocker_reviews"] = [{"case_id": "TC1", "branch_id": "B1", "resolution": "still_blocked",
                                    "reason": "No changed permission; do not replay", "evidence": ["DEMO-recheck"]}]
        result = REVIEW.analyze(data)
        self.assertTrue(result["completion_gate"])
        self.assertEqual(result["latest_counts"]["blocked"], 1)

    def test_failure_with_blocked_assertion_also_needs_review(self):
        data = ledger()
        data["attempts"] = [attempt(states=("failed", "blocked"))]
        result = REVIEW.analyze(data)
        self.assertEqual(result["latest_counts"]["failed"], 1)
        self.assertFalse(result["completion_gate"])

    def test_pending_regression_prevents_closure(self):
        data = ledger()
        data["attempts"] = [attempt()]
        data["regressions"] = [regression()]
        self.assertFalse(REVIEW.analyze(data)["completion_gate"])

    def test_done_regression_cannot_link_first_attempt(self):
        data = ledger()
        data["attempts"] = [attempt()]
        task = regression("done")
        task["attempt_id"] = "T1"
        data["regressions"] = [task]
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)

    def test_executed_failed_regression_is_not_passed(self):
        data = ledger()
        data["attempts"] = [attempt(), attempt("T2", ("failed", "passed"), "regression", "T1", second=1)]
        task = regression("done")
        task["attempt_id"] = "T2"
        data["regressions"] = [task]
        result = REVIEW.analyze(data)
        self.assertTrue(result["completion_gate"])
        self.assertEqual(result["latest_counts"]["failed"], 1)

    def test_waived_task_requires_human_authorization_reference(self):
        data = ledger()
        data["attempts"] = [attempt()]
        data["regressions"] = [regression("waived")]
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)
        data["regressions"][0]["waiver_ref"] = "DEMO-user-scope-decision"
        result = REVIEW.analyze(data)
        self.assertEqual(result["regression_results"][0]["status"], "waived")

    def test_selection_cannot_silently_drop_case(self):
        data = ledger()
        data["selected_case_ids"].append("TC2")
        with self.assertRaises(ValueError):
            REVIEW.analyze(data)

    def test_ids_and_references_are_checked(self):
        for change in ("duplicate_attempt", "unknown_assertion", "wrong_previous", "retry_before_first", "naive_time"):
            with self.subTest(change=change):
                data = ledger()
                data["attempts"] = [attempt()]
                if change == "duplicate_attempt":
                    data["attempts"].append(attempt())
                elif change == "unknown_assertion":
                    data["attempts"][0]["results"][0]["assertion_id"] = "FOREIGN"
                elif change == "wrong_previous":
                    data["attempts"].append(attempt("T2", phase="retry", prior="FOREIGN", second=1))
                elif change == "retry_before_first":
                    data["attempts"][0]["phase"] = "retry"
                else:
                    data["attempts"][0]["at"] = "2026-10-18T08:00:00"
                with self.assertRaises(ValueError):
                    REVIEW.analyze(data)

    def test_analysis_does_not_mutate_input(self):
        data = ledger()
        data["attempts"] = [attempt()]
        before = copy.deepcopy(data)
        REVIEW.analyze(data)
        self.assertEqual(data, before)

    def test_cli_is_read_only_and_does_not_open_evidence_references(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "ledger.json"
            data = ledger()
            data["attempts"] = [attempt()]
            data["attempts"][0]["results"][0]["evidence"] = [str(root / "not-existing-evidence.txt")]
            path.write_text(json.dumps(data), encoding="utf-8")
            before = path.read_bytes()
            result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(SCRIPT), str(path), "--format", "json"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["completion_gate"])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in root.iterdir()], ["ledger.json"])

    def test_duplicate_json_fields_and_nonfinite_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.json"
            for content in ('{"run_id":"a","run_id":"b"}', '{"x":NaN}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        REVIEW.load_ledger(path)


if __name__ == "__main__":
    unittest.main()
