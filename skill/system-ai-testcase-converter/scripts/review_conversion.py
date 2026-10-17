#!/usr/bin/env python3
"""只读核对转换映射并查看已提供的使用证据；不执行任何业务或登记脚本。"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import sys


PHASES = {"prepare", "act", "check"}
ROUTES = {"script": "脚本方案已绑定", "guided_once": "首次需走通",
          "human": "人工/工具协助", "blocked": "等待确认/准备"}
RESULTS = ("pass", "setup_failed", "script_failed", "assertion_failed", "blocked")
RESULT_LABELS = {"pass": "通过", "setup_failed": "准备失败", "script_failed": "脚本失败",
                 "assertion_failed": "断言不符", "blocked": "阻塞"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def texts(value, nonempty=False):
    return (isinstance(value, list) and all(text(item) for item in value)
            and (bool(value) or not nonempty))


def stamp(value):
    try:
        return text(value) and datetime.fromisoformat(
            value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def objects(value, name):
    need(isinstance(value, list) and all(isinstance(item, dict) for item in value), name + "须为对象数组")
    return value


def keyed(items, label):
    result = {}
    for item in items:
        need(text(item.get("id")), label + "缺少id")
        need(item["id"] not in result, label + "id重复：" + item["id"])
        result[item["id"]] = item
    return result


def validate(record):
    need(isinstance(record, dict), "记录须为JSON对象")
    need(record.get("schema_version") == "1.0", "schema_version须为1.0")
    need(record.get("skill_id") == "system-ai-testcase-converter", "skill_id不匹配")
    need(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?",
                          str(record.get("skill_version", "")))), "skill_version须为语义版本")
    need(text(record.get("conversion_id")), "缺少conversion_id")
    need(type(record.get("revision")) is int and record["revision"] > 0, "revision须为正整数")
    need(stamp(record.get("created_at")), "created_at须包含时区")
    need(text(record.get("counting_unit")), "须说明动作计数粒度counting_unit")

    sources = keyed(objects(record.get("source_cases"), "source_cases"), "原用例")
    checkpoint_map, covered, mapped_sources = {}, defaultdict(set), set()
    for sid, source in sources.items():
        need(text(source.get("location")) and text(source.get("version")), sid + "缺原位置或版本")
        checks = keyed(objects(source.get("checkpoints"), "checkpoints"), sid + "检查点")
        need(bool(checks) and all(text(item.get("text")) for item in checks.values()), sid + "缺原检查内容")
        checkpoint_map[sid] = set(checks)
        need(source.get("disposition") in {"converted", "deferred", "excluded"}, sid + "处理方式无效")
        if source["disposition"] != "converted":
            need(text(source.get("reason")) and text(source.get("evidence")), sid + "暂缓或排除须有原因及依据")
        omitted = objects(source.get("excluded_checkpoints", []), "excluded_checkpoints")
        excluded_ids = set()
        for item in omitted:
            need(item.get("id") in checks and item["id"] not in excluded_ids, sid + "排除检查点无效或重复")
            need(text(item.get("reason")) and text(item.get("evidence")), sid + "排除检查点须有原因及依据")
            excluded_ids.add(item["id"])
        covered[sid].update(excluded_ids)
        digest = source.get("source_sha256")
        need(digest is None or (isinstance(digest, str) and
                               bool(re.fullmatch(r"[a-fA-F0-9]{64}", digest))), sid + "源哈希无效")

    scripts = keyed(objects(record.get("scripts"), "scripts"), "脚本")
    for script_id, script in scripts.items():
        for key in ("path", "entry", "version"):
            need(text(script.get(key)), script_id + "缺少" + key)
        need(texts(script.get("phases"), True) and set(script["phases"]) <= PHASES, script_id + "环节无效")
        need(type(script.get("disabled")) is bool, script_id + "须说明disabled")
        verification = script.get("verification")
        need(isinstance(verification, dict) and
             verification.get("status") in {"unverified", "historical", "current"}, script_id + "验证状态无效")
        need(texts(verification.get("evidence")), script_id + "验证证据须为数组")
        if verification["status"] != "unverified":
            need(bool(verification["evidence"]), script_id + "验证声明缺证据")
        if verification["status"] == "current":
            need(text(verification.get("environment")) and text(verification.get("build")),
                 script_id + "当前验证缺环境/部署")

    cases = keyed(objects(record.get("cases"), "cases"), "AI用例")
    for cid, case in cases.items():
        for key in ("title", "case_ref", "basis", "setup_reason"):
            need(text(case.get(key)), cid + "缺少" + key)
        need(case.get("design_status") in {"complete", "rule_pending", "detail_pending"}, cid + "设计状态无效")
        need(case.get("basis_status") in {"confirmed", "pending"}, cid + "业务依据状态无效")
        need(case.get("route") in ROUTES, cid + "路线无效")
        if case["design_status"] != "complete" or case["basis_status"] != "confirmed":
            need(case["route"] == "blocked", cid + "预期/设计未明确须标等待确认")
        need(type(case.get("setup_required")) is bool, cid + "须说明setup_required")
        need(texts(case.get("assertion_ids"), True) and
             len(case["assertion_ids"]) == len(set(case["assertion_ids"])), cid + "断言编号为空或重复")
        need(texts(case.get("missing")), cid + "missing须为具体缺口数组")
        mapping = case.get("source_checks")
        need(isinstance(mapping, dict) and bool(mapping), cid + "缺原用例检查点对应")
        for sid, checks in mapping.items():
            need(sid in sources and sources[sid]["disposition"] == "converted", cid + "引用未知或未转换原用例")
            need(texts(checks, True) and len(checks) == len(set(checks)) and
                 set(checks) <= checkpoint_map[sid], cid + "引用未知或重复原检查点")
            covered[sid].update(checks)
            mapped_sources.add(sid)
        bindings = objects(case.get("bindings"), cid + " bindings")
        bound_phases = set()
        for binding in bindings:
            script_id = binding.get("script_id")
            need(script_id in scripts, cid + "绑定不存在的脚本")
            script = scripts[script_id]
            need(not script["disabled"], cid + "绑定禁用/隔离脚本")
            need(texts(binding.get("phases"), True) and
                 set(binding["phases"]) <= set(script["phases"]), cid + "调用超出入口已说明能力")
            need(text(binding.get("call_ref")), cid + "缺实际参数/输出调用说明位置")
            bound_phases.update(binding["phases"])
        required = {"act", "check"} | ({"prepare"} if case["setup_required"] else set())
        if case["route"] == "script":
            need(required <= bound_phases, cid + "脚本方案缺准备、被测动作或检查环节")
        preflight = case.get("preflight")
        need(isinstance(preflight, dict) and preflight.get("status") in {"unverified", "missing", "ready"},
             cid + "准备状态无效")
        need(texts(preflight.get("evidence")), cid + "准备证据须为数组")
        if preflight["status"] == "ready":
            need(case["route"] == "script" and not case["missing"], cid + "仍有缺口或人工依赖，不能标AI就绪")
            need(text(preflight.get("environment")) and text(preflight.get("build")) and
                 bool(preflight["evidence"]), cid + "就绪声明缺环境/部署/前置核实证据")
            for binding in bindings:
                verification = scripts[binding["script_id"]]["verification"]
                need(verification["status"] == "current" and
                     verification.get("environment") == preflight["environment"] and
                     verification.get("build") == preflight["build"], cid + "脚本验证与目标环境/部署不匹配")
        feedback = case.get("feedback")
        need(isinstance(feedback, dict), cid + "缺feedback")
        for key in ("understood", "usable"):
            need(key in feedback and (feedback[key] is None or type(feedback[key]) is bool),
                 cid + "反馈只接受true/false/null")
        if any(feedback[key] is not None for key in ("understood", "usable")):
            need(text(feedback.get("evidence")), cid + "反馈缺实际来源")

    for sid, source in sources.items():
        if source["disposition"] == "converted":
            need(sid in mapped_sources, sid + "标已转换但没有AI用例对应")
            need(covered[sid] == checkpoint_map[sid], sid + "有原检查点没有登记去向")

    attempts = keyed(objects(record.get("attempts"), "attempts"), "尝试")
    for aid, attempt in attempts.items():
        need(attempt.get("case_id") in cases, aid + "引用未知AI用例")
        case = cases[attempt["case_id"]]
        need(attempt.get("result") in RESULTS, aid + "结果无效")
        need(text(attempt.get("environment")) and text(attempt.get("build")), aid + "缺环境/部署")
        need(texts(attempt.get("evidence"), True), aid + "缺本次实际执行证据")
        for key in ("script_steps", "exploration_steps", "human_interventions"):
            need(type(attempt.get(key)) is int and attempt[key] >= 0, aid + "动作/介入计数须为非负整数")
        assertions = keyed(objects(attempt.get("assertions"), aid + " assertions"), aid + "断言")
        for assertion_id, assertion in assertions.items():
            need(assertion_id in case["assertion_ids"], aid + "引用未知断言")
            need(assertion.get("status") in {"pass", "fail"} and "actual" in assertion and
                 texts(assertion.get("evidence"), True), aid + "断言缺实际值/有效状态/证据")
        if attempt["result"] == "pass":
            need(case["design_status"] == "complete" and case["basis_status"] == "confirmed",
                 aid + "业务预期未确认，不能记通过")
            need(set(assertions) == set(case["assertion_ids"]) and
                 all(item["status"] == "pass" for item in assertions.values()), aid + "必要断言未全部有证据通过")
            need(texts(attempt.get("preflight_evidence"), True), aid + "通过记录缺本次前置核实证据")
        if attempt["result"] == "assertion_failed":
            need(any(item["status"] == "fail" for item in assertions.values()), aid + "断言不符须有实际失败断言")

    for feedback in objects(record.get("overall_feedback", []), "overall_feedback"):
        need(text(feedback.get("comment")) and text(feedback.get("evidence")), "整体反馈缺原意或来源")
    for measurement in objects(record.get("benefit_measurements", []), "benefit_measurements"):
        for key in ("metric", "unit", "scope", "evidence"):
            need(text(measurement.get(key)), "前后对比缺少" + key)
        for key in ("before", "after"):
            need(type(measurement.get(key)) in (int, float) and
                 0 <= measurement[key] < float("inf"), "前后对比数值无效")
    for proposal in objects(record.get("improvement_proposals", []), "improvement_proposals"):
        need(text(proposal.get("proposal")) and text(proposal.get("evidence")) and
             proposal.get("status") in {"proposed", "applied", "rejected"}, "改进提案无效")
        if proposal["status"] == "applied":
            need(text(proposal.get("applied_version")), "已应用提案缺新版本号")
    return record


def summary(records):
    need(bool(records), "至少提供一份转换记录")
    seen, groups = set(), defaultdict(list)
    for record in records:
        validate(record)
        need(record["conversion_id"] not in seen, "conversion_id重复，不能累计同一批次")
        seen.add(record["conversion_id"])
        groups[(record["skill_version"], record["counting_unit"])].append(record)
    result = []
    for (version, unit), items in sorted(groups.items()):
        cases = [case for item in items for case in item["cases"]]
        attempts = [attempt for item in items for attempt in item["attempts"]]
        feedback_stats = {}
        for key in ("understood", "usable"):
            positive = sum(case["feedback"][key] is True for case in cases)
            negative = sum(case["feedback"][key] is False for case in cases)
            rated = positive + negative
            feedback_stats[key] = {"yes": positive, "no": negative, "unrated": len(cases) - rated,
                                   "percent": round(100 * positive / rated, 1) if rated else None}
        details = []
        for item in items:
            environments = defaultdict(list)
            for attempt in item["attempts"]:
                environments[(attempt["environment"], attempt["build"])].append(attempt)
            actual = []
            for (environment, build), runs in sorted(environments.items()):
                first = {}
                for attempt in runs:
                    first.setdefault(attempt["case_id"], attempt["result"])
                actual.append({"environment": environment, "build": build,
                               "attempt_count": len(runs),
                               "results": dict(Counter(attempt["result"] for attempt in runs)),
                               "first_results": dict(Counter(first.values())),
                               "tested_case_ids": sorted(first)})
            details.append({
                "conversion_id": item["conversion_id"], "revision": item["revision"],
                "source_case_count": len(item["source_cases"]),
                "source_checkpoint_count": sum(len(source["checkpoints"]) for source in item["source_cases"]),
                "source_dispositions": dict(Counter(source["disposition"] for source in item["source_cases"])),
                "cases": [{"id": case["id"], "title": case["title"], "route": case["route"],
                           "design_status": case["design_status"], "preflight": case["preflight"]["status"],
                           "missing": case["missing"], "case_ref": case["case_ref"]} for case in item["cases"]],
                "source_decisions": [{"id": source["id"], "reason": source["reason"], "evidence": source["evidence"]}
                                     for source in item["source_cases"] if source["disposition"] != "converted"],
                "actual_runs": actual, "overall_feedback": item.get("overall_feedback", []),
            })
        scripted = sum(attempt["script_steps"] for attempt in attempts)
        explored = sum(attempt["exploration_steps"] for attempt in attempts)
        result.append({
            "skill_version": version, "counting_unit": unit, "conversions": details,
            "routes": dict(Counter(case["route"] for case in cases)),
            "recorded_ready": sum(case["preflight"]["status"] == "ready" for case in cases),
            "attempt_count": len(attempts), "script_steps": scripted, "exploration_steps": explored,
            "script_step_share": round(100 * scripted / (scripted + explored), 1) if scripted + explored else None,
            "human_interventions": sum(attempt["human_interventions"] for attempt in attempts),
            "feedback": feedback_stats,
            "benefit_measurements": [{**value, "conversion_id": item["conversion_id"]}
                                    for item in items for value in item.get("benefit_measurements", [])],
            "improvement_proposals": [{**value, "conversion_id": item["conversion_id"]}
                                     for item in items for value in item.get("improvement_proposals", [])],
        })
    return {"schema_version": "1.0", "groups": result}


def safe(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def pct(value):
    return "N/A" if value is None else str(value) + "%"


def render(report):
    lines = ["# AI用例转换：准备情况与实际反馈", "",
             "按提供记录核对；映射去向不等于业务覆盖，绑定/就绪不等于真实通过。", ""]
    for group in report["groups"]:
        lines += ["## Skill " + group["skill_version"] + "；计数粒度：" + safe(group["counting_unit"]), ""]
        for item in group["conversions"]:
            lines += ["### " + safe(item["conversion_id"]) + "（记录修订" + str(item["revision"]) + "）", "",
                      "原用例" + str(item["source_case_count"]) + "条、原检查点" +
                      str(item["source_checkpoint_count"]) + "个：均已登记去向或有据排除。", "",
                      "| AI用例 | 路线 | 准备 | 具体缺口 |",
                      "| --- | --- | --- | --- |"]
            for case in item["cases"]:
                note = "；".join(case["missing"]) or (
                    "尚需执行前核对" if case["preflight"] != "ready" else "记录有核实证据，执行前仍复核")
                lines.append("| " + " | ".join(safe(value) for value in (
                    case["id"] + " " + case["title"], ROUTES[case["route"]], case["preflight"], note)) + " |")
            for decision in item["source_decisions"]:
                lines.append("- 原用例" + safe(decision["id"]) + "：" + safe(decision["reason"]) +
                             "；依据：" + safe(decision["evidence"]))
            lines += ["", "实际试跑：", ""]
            if not item["actual_runs"]:
                lines.append("尚未试跑。")
            for actual in item["actual_runs"]:
                lines.append("- " + safe(actual["environment"]) + " / " + safe(actual["build"]) +
                             "；尝试" + str(actual["attempt_count"]) + "次；结果：" +
                             "、".join(RESULT_LABELS[key] + str(value) for key, value in actual["results"].items()))
                lines.append("  按记录顺序的首次尝试：" + "、".join(RESULT_LABELS[key] + str(value)
                                                     for key, value in actual["first_results"].items()) +
                             "；后续成功不抹去首次结果。")
            for feedback in item["overall_feedback"]:
                lines.append("- 整体反馈：" + safe(feedback["comment"]) + "；来源：" + safe(feedback["evidence"]))
            lines.append("")
        lines += ["### 汇总", "",
                  "- 路线：" + "、".join(ROUTES[key] + str(group["routes"].get(key, 0)) for key in ROUTES) + "。",
                  "- 有准备核实记录：" + str(group["recorded_ready"]) + "条；实际尝试：" +
                  str(group["attempt_count"]) + "次。",
                  "- 已记录脚本动作" + str(group["script_steps"]) + "、临时探索" +
                  str(group["exploration_steps"]) + "、人工接管" + str(group["human_interventions"]) + "。",
                  "- 脚本动作占比：" + pct(group["script_step_share"]) + "；不能据此推出覆盖率或省时比例。"]
        for key, label in (("understood", "看得懂"), ("usable", "拿去能用")):
            stat = group["feedback"][key]
            lines.append("- " + label + "：" + pct(stat["percent"]) + "；是" + str(stat["yes"]) +
                         "、否" + str(stat["no"]) + "，未评价" + str(stat["unrated"]) + "条。")
        if not group["benefit_measurements"]:
            lines.append("- 减少探索/节省时间：尚不能判断，缺可比较的前后基线。")
        for measurement in group["benefit_measurements"]:
            lines.append("- 前后记录（可比性需核对）：" + safe(measurement["metric"]) + " " +
                         str(measurement["before"]) + " → " + str(measurement["after"]) +
                         safe(measurement["unit"]) + "；范围：" + safe(measurement["scope"]) +
                         "；依据：" + safe(measurement["evidence"]))
        for proposal in group["improvement_proposals"]:
            lines.append("- 改进提案：" + safe(proposal["proposal"]) + "（" + safe(proposal["status"]) +
                         "）；依据：" + safe(proposal["evidence"]))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="+", type=Path)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        records = []
        for path in args.records:
            try:
                records.append(validate(json.loads(path.read_text(encoding="utf-8-sig"))))
            except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError(str(path) + "：" + str(exc)) from exc
        report = summary(records)
    except ValueError as exc:
        print("无法汇总：" + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
