#!/usr/bin/env python3
"""Read-only execution-ledger consistency review; never runs business actions."""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys


STATES = ("passed", "failed", "blocked", "inconclusive", "not_run")
ORDER = ("failed", "not_run", "inconclusive", "blocked", "passed")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), label + " must be a nonempty string")
    return value


def obj(value, label):
    require(isinstance(value, dict), label + " must be an object")
    return value


def array(value, label):
    require(isinstance(value, list), label + " must be an array")
    return value


def strings(value, label, minimum=0):
    result = array(value, label)
    require(len(result) >= minimum, label + " has too few entries")
    for item in result:
        nonempty(item, label + " entry")
    require(len(result) == len(set(result)), label + " has duplicates")
    return result


def verdict(statuses):
    return next(state for state in ORDER if state in statuses)


def timestamp(value):
    nonempty(value, "attempt.at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("attempt.at must be an ISO timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "attempt.at needs a timezone")
    return parsed


def analyze(data):
    obj(data, "ledger")
    require(data.get("schema_version") == "1.0", "unsupported schema_version")
    nonempty(data.get("run_id"), "run_id")
    require(type(data.get("revision")) is int and data["revision"] > 0, "revision must be a positive integer")
    baseline = obj(data.get("baseline"), "baseline")
    for key in ("cases_ref", "environment", "build", "role_scope", "authorization_ref"):
        nonempty(baseline.get(key), "baseline." + key)
    selected = strings(data.get("selected_case_ids"), "selected_case_ids", 1)
    nonempty(data.get("regression_scope_note"), "regression_scope_note")

    cases, branches = {}, {}
    for case in array(data.get("cases"), "cases"):
        obj(case, "case")
        cid = nonempty(case.get("id"), "case.id")
        require(cid not in cases, "duplicate case id: " + cid)
        cases[cid] = case
        selected_branches = array(case.get("branches"), "case.branches")
        require(bool(selected_branches), "case needs selected branches: " + cid)
        for branch in selected_branches:
            obj(branch, "branch")
            bid = nonempty(branch.get("id"), "branch.id")
            key = (cid, bid)
            require(key not in branches, "duplicate branch: " + str(key))
            assertions = {}
            for assertion in array(branch.get("assertions"), "branch.assertions"):
                obj(assertion, "assertion")
                aid = nonempty(assertion.get("id"), "assertion.id")
                require(aid not in assertions, "duplicate assertion: " + str(key + (aid,)))
                require("basis_ref" in assertion, "assertion needs basis_ref, possibly null")
                if assertion["basis_ref"] is not None:
                    nonempty(assertion["basis_ref"], "assertion.basis_ref")
                assertions[aid] = assertion
            require(bool(assertions), "branch needs necessary assertions: " + str(key))
            checks = strings(branch.get("required_checkpoints"), "required_checkpoints", 1)
            branches[key] = {"assertions": assertions, "checks": checks, "attempts": []}
    require(set(selected) == set(cases), "selected_case_ids and cases must match exactly")

    attempts = {}
    for attempt in array(data.get("attempts"), "attempts"):
        obj(attempt, "attempt")
        tid = nonempty(attempt.get("id"), "attempt.id")
        require(tid not in attempts, "duplicate attempt: " + tid)
        key = (attempt.get("case_id"), attempt.get("branch_id"))
        require(key in branches, "attempt targets unknown branch: " + tid)
        branch = branches[key]
        phase = attempt.get("phase")
        require(phase in ("first", "retry", "regression"), "invalid attempt phase: " + tid)
        at = timestamp(attempt.get("at"))
        history = branch["attempts"]
        if not history:
            require(phase == "first" and not attempt.get("prior_attempt_id"), "first branch attempt must be first: " + tid)
        else:
            require(phase != "first", "multiple first attempts: " + tid)
            require(attempt.get("prior_attempt_id") == history[-1]["id"], "attempt must link latest attempt of same branch: " + tid)
            require(at >= history[-1]["at"], "attempt timestamp moves backward: " + tid)
            nonempty(attempt.get("reason"), "later attempt.reason")
        for flag in ("context_verified", "preconditions_verified"):
            require(type(attempt.get(flag)) is bool, flag + " must be a boolean")
        context_evidence = strings(attempt.get("context_evidence"), "context_evidence")
        checkpoints = obj(attempt.get("checkpoint_evidence"), "checkpoint_evidence")
        for name, refs in checkpoints.items():
            nonempty(name, "checkpoint name")
            strings(refs, "checkpoint references", 1)
        results = {}
        for result in array(attempt.get("results"), "attempt.results"):
            obj(result, "result")
            aid = nonempty(result.get("assertion_id"), "result.assertion_id")
            require(aid in branch["assertions"] and aid not in results, "unknown or duplicate result assertion: " + aid)
            state = result.get("status")
            require(state in STATES, "invalid assertion status: " + str(state))
            refs = strings(result.get("evidence"), "assertion evidence")
            if state in ("passed", "failed"):
                nonempty(result.get("actual"), "judged assertion.actual")
                require(bool(refs), "passed/failed needs actual evidence: " + aid)
                require(bool(branch["assertions"][aid]["basis_ref"]), "passed/failed needs independent basis: " + aid)
                require(attempt["context_verified"] and attempt["preconditions_verified"] and bool(context_evidence), "passed/failed needs verified context and prerequisites: " + aid)
            else:
                nonempty(result.get("reason"), "unresolved assertion.reason")
            results[aid] = state
        missing = [aid for aid in branch["assertions"] if aid not in results]
        states = [results.get(aid, "not_run") for aid in branch["assertions"]]
        missing_checks = [name for name in branch["checks"] if not checkpoints.get(name)]
        state = verdict(states)
        if state == "passed" and missing_checks:
            state = "inconclusive"
        summary = {"id": tid, "phase": phase, "verdict": state,
                   "terminal": "not_run" not in states,
                   "missing_assertions": missing, "missing_checkpoints": missing_checks,
                   "has_blocked_assertions": "blocked" in states, "at": at}
        attempts[tid] = (key, summary)
        history.append(summary)

    def referenced(entry, field, key, phase):
        tid = nonempty(entry.get(field), field)
        require(tid in attempts, "unknown attempt reference: " + tid)
        target, result = attempts[tid]
        require(target == key and result["phase"] == phase, "attempt reference has wrong target or phase: " + tid)
        return result

    pending = []
    regression_results = []
    regression_ids = set()
    for task in array(data.get("regressions"), "regressions"):
        obj(task, "regression")
        rid = nonempty(task.get("id"), "regression.id")
        require(rid not in regression_ids, "duplicate regression id: " + rid)
        regression_ids.add(rid)
        key = (task.get("case_id"), task.get("branch_id"))
        require(key in branches, "regression targets unknown branch: " + rid)
        require(task.get("kind") in ("fixed", "dynamic"), "invalid regression kind")
        nonempty(task.get("reason"), "regression.reason")
        state = task.get("status")
        require(state in ("pending", "done", "blocked", "waived"), "invalid regression status")
        if state == "pending":
            pending.append(rid)
        elif state == "done":
            result = referenced(task, "attempt_id", key, "regression")
            require(result["terminal"] and result["verdict"] in ("passed", "failed"), "done regression needs completed judged attempt: " + rid)
        elif state == "blocked":
            strings(task.get("evidence"), "blocked regression evidence", 1)
            if task.get("attempt_id"):
                result = referenced(task, "attempt_id", key, "regression")
                require(result["verdict"] in ("blocked", "inconclusive"), "blocked regression contradicts attempt: " + rid)
        else:
            nonempty(task.get("waiver_ref"), "regression.waiver_ref")
        regression_results.append(dict(task))

    initial_blockers = {key for key, branch in branches.items()
                        if branch["attempts"] and branch["attempts"][0]["has_blocked_assertions"]}
    reviewed = set()
    for review in array(data.get("blocker_reviews"), "blocker_reviews"):
        obj(review, "blocker review")
        key = (review.get("case_id"), review.get("branch_id"))
        require(key in initial_blockers and key not in reviewed, "duplicate or noninitial blocker review: " + str(key))
        reviewed.add(key)
        nonempty(review.get("reason"), "blocker review.reason")
        resolution = review.get("resolution")
        require(resolution in ("retried", "still_blocked", "waived"), "invalid blocker resolution")
        if resolution == "retried":
            result = referenced(review, "attempt_id", key, "retry")
            require(result["terminal"], "blocked retry still has unaddressed assertions")
        elif resolution == "still_blocked":
            strings(review.get("evidence"), "blocker review evidence", 1)
            require(branches[key]["attempts"][-1]["verdict"] != "passed", "still_blocked contradicts latest passed result")
        else:
            nonempty(review.get("waiver_ref"), "blocker review.waiver_ref")

    rows = []
    for (cid, bid), branch in branches.items():
        history = branch["attempts"]
        empty = {"id": None, "verdict": "not_run", "terminal": False,
                 "missing_assertions": list(branch["assertions"]), "missing_checkpoints": branch["checks"]}
        def visible(item):
            return {key: value for key, value in item.items() if key != "at"}
        rows.append({"case_id": cid, "branch_id": bid, "first": visible(history[0] if history else empty),
                     "latest": visible(history[-1] if history else empty),
                     "initially_blocked": (cid, bid) in initial_blockers,
                     "ever_failed": any(item["verdict"] == "failed" for item in history)})
    case_results = []
    for cid in selected:
        own = [row for row in rows if row["case_id"] == cid]
        case_results.append({"case_id": cid, "first_verdict": verdict([row["first"]["verdict"] for row in own]),
                             "latest_verdict": verdict([row["latest"]["verdict"] for row in own])})
    first_complete = all(row["first"]["terminal"] for row in rows)
    latest_complete = all(row["latest"]["terminal"] for row in rows)
    unreviewed = [{"case_id": cid, "branch_id": bid} for cid, bid in sorted(initial_blockers - reviewed)]
    def counts(field):
        raw = Counter(item[field] for item in case_results)
        return {state: raw[state] for state in STATES}
    return {"schema_version": "1.0", "run_id": data["run_id"], "revision": data["revision"],
            "structurally_valid": True, "selected_case_count": len(selected), "selected_branch_count": len(rows),
            "first_pass_counts": counts("first_verdict"), "latest_counts": counts("latest_verdict"),
            "case_results": case_results, "branches": rows,
            "historical_failed_attempt_ids": [tid for tid, (_, item) in attempts.items() if item["verdict"] == "failed"],
            "first_pass_complete": first_complete, "latest_complete": latest_complete,
            "pending_regression_ids": pending, "regression_results": regression_results,
            "unreviewed_initial_blockers": unreviewed, "blocker_review_results": data["blocker_reviews"],
            "completion_gate": first_complete and latest_complete and not pending and not unreviewed,
            "claim_limit": "仅核对声明台账的一致性；收口不代表全通过、证据真实充分或可发布。"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field: " + key)
        result[key] = value
    return result


def load_ledger(path):
    def reject_constant(value):
        raise ValueError("nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", help="explicit UTF-8 JSON ledger; evidence references are not opened")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = analyze(load_ledger(args.ledger))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("Invalid ledger: " + str(exc), file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("运行：" + report["run_id"])
        print("首轮用例：" + json.dumps(report["first_pass_counts"], ensure_ascii=False))
        print("当前用例：" + json.dumps(report["latest_counts"], ensure_ascii=False))
        print("台账已收口：" + str(report["completion_gate"]))
        print("待回归：" + json.dumps(report["pending_regression_ids"], ensure_ascii=False))
        print("回归处置：" + json.dumps(report["regression_results"], ensure_ascii=False))
        print("待复查初始阻塞：" + json.dumps(report["unreviewed_initial_blockers"], ensure_ascii=False))
        print(report["claim_limit"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
