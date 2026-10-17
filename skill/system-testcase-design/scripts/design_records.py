"""Local bundle checks, bottomline document generation and outcome review.

No network, business execution, external discovery or feedback writes.
Consistency checks do not establish truth of business rules or risk evidence.
"""
import argparse
import collections
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

LABELS = {"indispensable": "已核定不可替代", "candidate": "待核定候选",
          "substitutable": "底线有替代／组合补强", "not_bottomline": "未达底线标准",
          "unassessed": "未评估"}
RATINGS = {"readable", "preparable", "assertable", "useful"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MARKER = re.compile(r"^<!-- (CASE|SHARED) ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) (BEGIN|END) -->$")


class Invalid(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def text(value, label):
    need(isinstance(value, str) and bool(value.strip()), label + "：需要非空文本")


def refs(value, label, required=False):
    need(isinstance(value, list), label + "：需要数组")
    need(not required or bool(value), label + "：缺依据或引用")
    for item in value:
        text(item, label)
    need(len(value) == len(set(value)), label + "：重复引用")
    return value


def index(rows, label):
    need(isinstance(rows, list), label + "：需要数组")
    result = {}
    for row in rows:
        need(isinstance(row, dict), label + "：条目须为对象")
        key = row.get("id")
        need(isinstance(key, str) and ID.fullmatch(key), label + "：非法ID")
        need(key not in result, label + "：重复ID " + key)
        result[key] = row
    return result


def known(values, mapping, label):
    for key in refs(values, label):
        need(key in mapping, label + "：未知引用 " + key)


def timestamp(value):
    text(value, "时间")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid("时间须为ISO格式") from exc
    need(parsed.tzinfo is not None, "时间需要时区")
    return parsed


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(body):
    return sha(body.replace("\r\n", "\n").strip().encode("utf-8"))


def docpath(record_path, relative):
    text(relative, "文档路径")
    base = record_path.parent.resolve()
    path = Path(relative)
    need(not path.is_absolute(), "文档路径须相对于记录目录")
    target = (base / path).resolve()
    need(target.is_relative_to(base) and target != base, "文档不能越出批次目录")
    need(target.suffix.lower() == ".md", "助手只处理Markdown，其他格式按同一语义核对")
    return target


def blocks(content):
    result, active, body = {"CASE": {}, "SHARED": {}}, None, []
    for line in content.replace("\r\n", "\n").splitlines():
        marker = MARKER.fullmatch(line)
        if marker:
            kind, key, mode = marker.groups()
            if mode == "BEGIN":
                need(active is None, "正文块不能嵌套")
                need(key not in result[kind], "重复正文块 " + key)
                active, body = (kind, key), []
            else:
                need(active == (kind, key), "正文块结束不匹配 " + key)
                content = "\n".join(body).strip()
                need(bool(content), "正文块不能为空 " + key)
                result[kind][key] = content
                active, body = None, []
        elif active:
            body.append(line)
    need(active is None, "正文块缺END")
    return result


def validate_decisions(record, cases, rules):
    obligations = index(record["obligations"], "obligations")
    for key, ob in obligations.items():
        for field in ["text", "condition", "consequence", "scope"]:
            text(ob[field], key + "." + field)
        known(ob["rule_ids"], rules, key + ".rule_ids")
        need(bool(ob["rule_ids"]), "底线缺适用业务规则")
        need(ob["risk"]["status"] in {"confirmed", "assessed", "pending"}, "风险状态不符")
        refs(ob["risk"]["basis"], "风险依据")
        need(ob["gap"]["status"] in {"shown", "not_shown", "pending"}, "删除空白状态不符")
        text(ob["gap"]["reason"], "删除后空白")
        refs(ob["gap"]["basis"], "删除比较依据")
        for near in ob["gap"]["near_cases"]:
            need(near["case_id"] in cases, "近似用例ID不存在")
            text(near["comparison"], "近似比较")
        alt = ob["alternatives"]
        need(alt["inventory"] in {"complete", "partial", "unknown"}, "替代盘点状态不符")
        need(alt["conclusion"] in {"none_equivalent", "equivalent_exists", "pending"}, "替代结论不符")
        text(alt["scope"], "替代核定范围")
        refs(alt["basis"], "替代盘点依据")
        need(isinstance(alt["checks"], list), "替代checks须为数组")
        for check in alt["checks"]:
            for field in ["kind", "ref", "reason"]:
                text(check[field], "替代." + field)
            need(check["status"] in {"effective", "insufficient", "unverified"}, "替代有效性状态不符")
            refs(check["evidence"], "替代依据", check["status"] != "unverified")
        need(not (alt["conclusion"] == "none_equivalent" and any(c["status"] == "effective" for c in alt["checks"])),
             "有有效替代不能宣称无替代")
        proof = ob["proof"]
        need(proof["case_id"] in cases, "底线证明用例不存在")
        known(proof["assertion_ids"], cases[proof["case_id"]]["assertion_ids"], "底线断言")
        need(bool(proof["assertion_ids"]), "底线缺证明断言")
        need(proof["adequacy"] in {"sufficient", "partial", "unknown"}, "证据方案状态不符")
        text(proof["reason"], "证据能力判断")
        refs(proof["evidence_plan"], "证据方案")
    for key, case in cases.items():
        decision = case["bottomline"]
        need(decision["classification"] in LABELS, "底线分类不符 " + key)
        text(decision["reason"], "底线判断理由")
        known(decision["obligation_ids"], obligations, "底线ID")
        owned = [obligations[o] for o in decision["obligation_ids"] if obligations[o]["proof"]["case_id"] == key]
        if decision["classification"] in {"indispensable", "candidate"}:
            need(bool(owned), key + "：正式或候选缺本例底线论证")
        if decision["classification"] == "indispensable":
            need(case["design_status"] == "complete", key + "：设计未明确不能核定")
            def established(ob):
                risk, gap, alt, proof = (ob[f] for f in ["risk", "gap", "alternatives", "proof"])
                return (risk["status"] == "confirmed" and bool(risk["basis"])
                        and gap["status"] == "shown" and bool(gap["basis"])
                        and alt["inventory"] == "complete" and bool(alt["basis"])
                        and alt["conclusion"] == "none_equivalent"
                        and all(c["status"] == "insufficient" for c in alt["checks"])
                        and proof["adequacy"] == "sufficient" and bool(proof["evidence_plan"])
                        and all(rules[r]["basis_status"] == "confirmed" for r in ob["rule_ids"]))
            need(any(established(o) for o in owned), key + "：三条件或证据论证不足，只能候选")
    return obligations


def validate_feedback(record, cases):
    for feedback in index(record["feedback"], "feedback").values():
        need(feedback["scope"] in {"suite", "case"}, "反馈scope不符")
        timestamp(feedback["at"])
        text(feedback["evidence"], "反馈来源")
        text(feedback["comment"], "反馈原意")
        ratings = feedback.get("ratings", {})
        need(isinstance(ratings, dict) and set(ratings) <= RATINGS, "反馈维度不符")
        need(all(v is None or type(v) is bool for v in ratings.values()), "评价只接受真实布尔或null")
        if feedback["scope"] == "case":
            case = cases.get(feedback.get("case_id"))
            need(case is not None and feedback["case_fingerprint"] == case["fingerprint"], "反馈不能借用其他用例版本")
    for attempt in index(record["outcomes"], "outcomes").values():
        case = cases.get(attempt["case_id"])
        need(case is not None and attempt["case_fingerprint"] == case["fingerprint"], "执行不能借用其他用例版本")
        timestamp(attempt["at"])
        text(attempt["environment"], "执行环境")
        text(attempt["build"], "执行构建")
        refs(attempt["evidence"], "执行依据", True)
        need(attempt["result"] in {"pass", "fail", "blocked", "inconclusive"}, "执行结果不符")
        observed = index(attempt["assertions"], "实际断言")
        for aid, assertion in observed.items():
            need(aid in case["assertion_ids"], "未知执行断言 " + aid)
            need(assertion["status"] in {"pass", "fail", "not_observed"}, "断言状态不符")
            if assertion["status"] != "not_observed":
                need(assertion.get("actual") is not None and assertion.get("actual") != "", "缺实际观察值")
                refs(assertion["evidence"], "断言实测依据", True)
        if attempt["result"] == "pass":
            need(case["design_status"] == "complete", "未决预期不能记通过")
            need(set(observed) == set(case["assertion_ids"]) and all(a["status"] == "pass" for a in observed.values()),
                 "缺少必要断言不能记通过")
            refs(attempt["preflight_evidence"], "本次前置核对", True)
        if attempt["result"] == "fail":
            need(any(a["status"] == "fail" for a in observed.values()), "失败缺实际不符断言")
        if attempt["result"] in {"blocked", "inconclusive"}:
            text(attempt["reason"], "阻塞或不确定原因")
    for finding in index(record["findings"], "findings").values():
        need(finding["status"] in {"reported", "confirmed", "rejected"}, "质量反馈状态不符")
        for field in ["kind", "description", "evidence"]:
            text(finding[field], "质量反馈." + field)
        known(finding["case_ids"], cases, "质量反馈case_ids")
    for measure in record["benefit_measurements"]:
        for field in ["metric", "unit", "scope", "evidence"]:
            text(measure[field], "收益." + field)
        need(all(type(measure.get(f)) in {int, float} and math.isfinite(measure[f]) for f in ["before", "after"]),
             "收益缺有限数值的可比前后基线")
    for proposal in index(record["improvement_proposals"], "improvement_proposals").values():
        need(proposal["status"] in {"proposed", "applied", "rejected"}, "改进状态不符")
        text(proposal["proposal"], "改进提案")
        text(proposal["evidence"], "提案依据")
        if proposal["status"] == "applied":
            text(proposal["applied_version"], "已应用版本")


def load(path):
    path = Path(path).resolve()
    def reject_constant(value):
        raise Invalid("JSON不接受非有限数值 " + value)
    record = json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject_constant)
    need(record["schema_version"] == "1.0" and record["skill_id"] == "system-testcase-design", "记录协议或skill不符")
    need(re.fullmatch(r"\d+\.\d+\.\d+", record["skill_version"]) is not None, "skill版本格式不符")
    for field in ["design_id", "case_set_version", "requirement"]:
        text(record[field], field)
    need(type(record["revision"]) is int and record["revision"] >= 1, "revision须为正整数")
    timestamp(record["created_at"])
    for field in ["obligations", "coverage", "issues", "feedback", "outcomes", "findings", "benefit_measurements", "improvement_proposals"]:
        need(isinstance(record[field], list), field + "须为数组")
    sources = index(record["sources"], "sources")
    for source in sources.values():
        text(source["path"], "source.path")
        text(source["version"], "source.version")
        need(source["read_status"] in {"read", "partial", "unread"}, "来源读取状态不符")
        need(source.get("sha256") is None or re.fullmatch(r"[a-f0-9]{64}", source["sha256"]), "来源指纹格式不符")
    rules = index(record["rules"], "rules")
    for rule in rules.values():
        need(rule["basis_status"] in {"confirmed", "pending", "current_behavior"}, "规则状态不符")
        need(isinstance(rule["source_refs"], list), "规则source_refs须为数组")
        need(rule["basis_status"] != "confirmed" or bool(rule["source_refs"]), "确认规则缺来源")
        for ref in rule["source_refs"]:
            need(ref["source_id"] in sources, "规则引用未知来源")
            text(ref["location"], "规则定位")
            need(rule["basis_status"] != "confirmed" or sources[ref["source_id"]]["read_status"] != "unread",
                 "未读来源不能独立支撑已确认规则")
    full = docpath(path, record["documents"]["full"]["path"])
    second = docpath(path, record["documents"]["bottomline"]["path"])
    need(full != second, "两份文档不能同路径")
    content = full.read_bytes()
    need(sha(content) == record["documents"]["full"]["sha256"], "全量文件指纹不符；请核对并建新设计批次")
    parsed = blocks(content.decode("utf-8-sig"))
    cases = index(record["cases"], "cases")
    need(set(cases) == set(parsed["CASE"]), "全量正文块与记录用例ID不一致")
    for key, case in cases.items():
        text(case["title"], "用例标题")
        text(case["case_ref"], "正文定位")
        text(case["priority"], "优先级")
        need(case["fingerprint"] == fingerprint(parsed["CASE"][key]), key + "：用例正文指纹不符")
        need(case["design_status"] in {"complete", "rule_pending", "detail_pending"}, "设计状态不符")
        known(case["rule_ids"], rules, "用例规则")
        need(bool(case["rule_ids"]), "用例缺规则依据")
        refs(case["assertion_ids"], "用例断言", True)
        known(case["shared_refs"], parsed["SHARED"], "用例共享块")
        if case["design_status"] == "complete":
            need(all(rules[r]["basis_status"] != "pending" for r in case["rule_ids"]), "未决规则不能记设计明确")
        pre = case["preparation"]
        need(pre["status"] in {"unverified", "missing", "ready"}, "准备状态不符")
        refs(pre["evidence"], "准备核对证据")
        if pre["status"] == "ready":
            text(pre["environment"], "准备环境")
            text(pre["build"], "准备构建")
            need(bool(pre["evidence"]), "准备就绪缺实际核对依据")
    dependencies = record.get("shared_dependencies", {})
    need(isinstance(dependencies, dict), "shared_dependencies须为对象")
    for key, values in dependencies.items():
        need(key in parsed["SHARED"], "共享依赖引用未知块")
        known(values, parsed["SHARED"], "共享依赖")
    def visit(key, stack):
        need(key not in stack, "共享依赖循环 " + key)
        for child in dependencies.get(key, []):
            visit(child, stack | {key})
    for key in parsed["SHARED"]:
        visit(key, set())
    need(len(record["coverage"]) == len(rules) and {c["rule_id"] for c in record["coverage"]} == set(rules),
         "每项规则需要唯一覆盖去向")
    for row in record["coverage"]:
        need(row["status"] in {"covered", "partial", "pending", "excluded"}, "覆盖状态不符")
        known(row["case_ids"], cases, "覆盖用例")
        text(row["reason"], "覆盖去向说明")
        need(row["status"] != "covered" or bool(row["case_ids"]), "已设计覆盖不能无用例")
    obligations = validate_decisions(record, cases, rules)
    for issue in index(record["issues"], "issues").values():
        need(issue["status"] in {"open", "resolved"}, "问题状态不符")
        text(issue["title"], "问题描述")
        known(issue["case_ids"], cases, "问题影响用例")
    validate_feedback(record, cases)
    return record, parsed, cases, obligations, second


def cell(value):
    return str(value).replace("|", "／").replace("\n", "；")


def render(record, parsed, cases, obligations):
    counts = collections.Counter(c["bottomline"]["classification"] for c in cases.values())
    out = ["# 不可替代的业务底线用例", "", "需求：" + record["requirement"], "",
           f'设计批次：{record["design_id"]}；用例版本：{record["case_set_version"]}；skill：{record["skill_version"]}。',
           "", f'全部 {len(cases)} 条；已核定 {counts["indispensable"]} 条；候选 {counts["candidate"]} 条；未评估 {counts["unassessed"]} 条。',
           "", "仅在各底线声明的范围内核定，是设计结论，不表示已执行或可发布。候选不混算正式数，正式区为空不表示项目无底线。",
           "", "其他验证原样保留时逐条判定。互为替代者不可成组随意删除，本文件不是最小回归集。"]
    needed = set()
    def include(key):
        if key not in needed:
            needed.add(key)
            for child in record.get("shared_dependencies", {}).get(key, []):
                include(child)
    for classification in ["indispensable", "candidate"]:
        selected = [c for c in cases.values() if c["bottomline"]["classification"] == classification]
        out += ["", "## " + LABELS[classification], ""]
        if not selected:
            out += ["本批次暂无此类用例，以全量覆盖、候选和缺口为准。"]
        for case in selected:
            key = case["id"]
            for shared in case["shared_refs"]:
                include(shared)
            out += ["", "### 筛选依据：" + key, "", case["bottomline"]["reason"]]
            for oid in case["bottomline"]["obligation_ids"]:
                ob = obligations[oid]
                rows = [("底线 " + oid, ob["text"]), ("条件及范围", ob["condition"] + "；" + ob["scope"]),
                        ("直接后果", ob["consequence"]),
                        ("风险定级", ob["risk"]["status"] + "；" + "；".join(ob["risk"]["basis"])),
                        ("删除后空白", ob["gap"]["reason"] + "；" + "；".join(ob["gap"]["basis"])),
                        ("替代盘点", ob["alternatives"]["scope"] + "；" + ob["alternatives"]["inventory"] + "；" + ob["alternatives"]["conclusion"] + "；" + "；".join(ob["alternatives"]["basis"])),
                        ("证据方案", ob["proof"]["adequacy"] + "；" + ob["proof"]["reason"] + "；" + "；".join(ob["proof"]["evidence_plan"]))]
                out += ["", "|判断项|依据|", "|---|---|"] + [f'|{cell(k)}|{cell(v)}|' for k,v in rows]
                if ob["gap"]["near_cases"] or ob["alternatives"]["checks"]:
                    out += [""]
                out += [f'- 近似 {n["case_id"]}：{n["comparison"]}' for n in ob["gap"]["near_cases"]]
                out += [f'- 替代 {a["ref"]}（{a["status"]}）：{a["reason"]}；依据：' + "；".join(a["evidence"]) for a in ob["alternatives"]["checks"]]
            out += ["", f'<!-- CASE {key} BEGIN -->', parsed["CASE"][key], f'<!-- CASE {key} END -->']
    out += ["", "## 未评估条目", ""]
    pending = [c for c in cases.values() if c["bottomline"]["classification"] == "unassessed"]
    out += [f'- {c["id"]}：{c["bottomline"]["reason"]}' for c in pending] or ["无。"]
    out += ["", "## 本文所需共享依据与准备", ""]
    for key, body in parsed["SHARED"].items():
        if key in needed:
            out += [f'<!-- SHARED {key} BEGIN -->', body, f'<!-- SHARED {key} END -->', ""]
    if not needed:
        out += ["所需依据与前置已写入各用例，无共享块引用。"]
    out += ["", "## 尚未关闭的问题", ""]
    opened = [i for i in record["issues"] if i["status"] == "open"]
    out += [f'- {i["id"]}：{i["title"]}' for i in opened] or ["无已登记问题，不代表实际执行条件已核实。"]
    return ("\n".join(out).rstrip() + "\n").encode("utf-8")


def inspect(path, require_second=True):
    record, parsed, cases, obligations, second = load(path)
    expected = render(record, parsed, cases, obligations)
    if require_second:
        need(second.read_bytes() == expected, "第二份文档与当前批次或正文不一致")
    return record, cases, second, expected


def review(record, cases):
    latest = {}
    for feedback in sorted(record["feedback"], key=lambda f: timestamp(f["at"])):
        if feedback["scope"] == "case":
            for dimension, value in feedback.get("ratings", {}).items():
                latest[(feedback["case_id"], dimension)] = value
    ratings = {}
    for dimension in sorted(RATINGS):
        values = [v for (cid, dim), v in latest.items() if dim == dimension and v is not None]
        ratings[dimension] = {"positive": sum(values), "rated": len(values), "unrated": len(cases)-len(values),
                              "status": "未评价" if not values else "仅实际逐例反馈"}
    groups = {}
    for outcome in sorted(record["outcomes"], key=lambda a: timestamp(a["at"])):
        groups.setdefault((outcome["environment"], outcome["build"]), {})[outcome["case_id"]] = outcome
    grouped = [{"environment": env, "build": build,
                "latest_per_case": dict(collections.Counter(a["result"] for a in rows.values())),
                "case_ids": list(rows)} for (env,build),rows in groups.items()]
    counts = collections.Counter(c["bottomline"]["classification"] for c in cases.values())
    return {"design_id": record["design_id"], "skill_version": record["skill_version"],
            "case_set_version": record["case_set_version"], "revision": record["revision"],
            "open_issues": [i for i in record["issues"] if i["status"] == "open"],
            "pending_bottomlines": [{"id": c["id"], "status": c["bottomline"]["classification"],
                                    "reason": c["bottomline"]["reason"]} for c in cases.values()
                                   if c["bottomline"]["classification"] in {"candidate", "unassessed"}],
            "case_count": len(cases), "classification_counts": {k: counts[k] for k in LABELS},
            "bottomline_findings": [f for f in record["findings"]
                                   if f["kind"] in {"new_alternative", "false_bottomline", "missed_bottomline"}
                                   and f["status"] != "rejected"],
            "preparation_counts": dict(collections.Counter(c["preparation"]["status"] for c in cases.values())),
            "case_feedback": ratings, "overall_feedback": [f for f in record["feedback"] if f["scope"] == "suite"],
            "execution_status": "未执行" if not record["outcomes"] else "仅已有证据记录，按环境及构建分列",
            "outcomes": grouped, "findings": record["findings"],
            "benefit_measurements": record["benefit_measurements"],
            "benefit_note": "没有可比较基线时尚不能判断收益；数量、静态校验和业务通过率不是skill有效性。",
            "improvement_proposals": record["improvement_proposals"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build-bottomlines", "check", "review"])
    parser.add_argument("records", nargs="+")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    try:
        need(args.command == "review" or len(args.records) == 1, "build/check一次只处理一个批次")
        bundles, seen = [], set()
        for path in args.records:
            bundle = inspect(path, args.command != "build-bottomlines")
            need(bundle[0]["design_id"] not in seen, "重复design_id；同一批次只选择一个revision")
            seen.add(bundle[0]["design_id"])
            bundles.append(bundle)
        if args.command == "build-bottomlines":
            _, _, target, expected = bundles[0]
            if target.exists():
                need(target.read_bytes() == expected, "已有第二份内容不同，不覆盖历史；请建新批次目录")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as file:
                    file.write(expected)
            print(json.dumps({"document": str(target), "sha256": sha(expected), "business_execution": False}, ensure_ascii=False))
        elif args.command == "check":
            record, cases, _, expected = bundles[0]
            print(json.dumps({"design_id": record["design_id"], "cases": len(cases),
                              "structural_check": "consistent", "semantic_or_execution_proof": False,
                              "bottomline_sha256": sha(expected)}, ensure_ascii=False))
        else:
            summaries = [review(r,c) for r,c,_,_ in bundles]
            if args.format == "json":
                print(json.dumps(summaries, ensure_ascii=False, indent=2))
            else:
                for summary in summaries:
                    print(f'批次 {summary["design_id"]}｜skill {summary["skill_version"]}｜用例 {summary["case_set_version"]}｜revision {summary["revision"]}')
                    for issue in summary["open_issues"]:
                        print(f'待补 {issue["id"]}：{issue["title"]}')
                    for pending in summary["pending_bottomlines"]:
                        print(f'待核定 {pending["id"]}：{pending["reason"]}')
                    for finding in summary["bottomline_findings"]:
                        print(f'底线反馈待复核 {finding["id"]}：{finding["description"]}；依据：{finding["evidence"]}')
                    print("本批次原设计分类：" + "；".join(f'{LABELS[k]} {n}' for k,n in summary["classification_counts"].items()))
                    print("准备：" + json.dumps(summary["preparation_counts"], ensure_ascii=False))
                    print("执行：" + summary["execution_status"] + "；" + json.dumps(summary["outcomes"], ensure_ascii=False))
                    for label, field in [("逐例反馈", "case_feedback"), ("整份反馈", "overall_feedback"),
                                         ("质量反馈", "findings"), ("收益原始记录", "benefit_measurements"),
                                         ("改进提案", "improvement_proposals")]:
                        print(label + "：" + json.dumps(summary[field], ensure_ascii=False))
                    print(summary["benefit_note"])
        return 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        print("记录检查失败：" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
