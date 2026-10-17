"""Read only explicit generation records; no external reads or business execution."""
import argparse
import collections
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

RATINGS = {"atomic", "readable", "usable", "reviewable"}
SUBJECTS = {"generator", "generated_skill"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$")
SKILL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Invalid(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def text(value, name):
    need(isinstance(value, str) and bool(value.strip()), name + "需要非空文本")


def evidence(values, name, required=False):
    need(isinstance(values, list), name + "需要数组")
    need(not required or bool(values), name + "缺实际依据")
    for value in values:
        text(value, name)


def rows(values, name):
    need(isinstance(values, list), name + "需要数组")
    seen = set()
    for row in values:
        need(isinstance(row, dict), name + "条目须为对象")
        text(row.get("id"), name + ".id")
        need(row["id"] not in seen, name + "重复ID")
        seen.add(row["id"])
    return values


def time(value):
    text(value, "时间")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid("时间须ISO格式") from exc
    need(parsed.tzinfo is not None, "时间须带时区")
    return parsed


def subject(record, event):
    need(event["subject"] in SUBJECTS, "评价/使用对象不符")
    expected = record[event["subject"]]["version"]
    need(event["subject_version"] == expected, "旧版本评价或使用不能借给当前对象")


def load(path):
    def nonfinite(value):
        raise Invalid("JSON不接受非有限数值 " + value)
    record = json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=nonfinite)
    need(record["schema_version"] == "1.0", "不支持的协议版本")
    text(record["run_id"], "run_id")
    need(type(record["revision"]) is int and record["revision"] > 0, "revision须正整数")
    time(record["created_at"])
    for name in SUBJECTS:
        obj = record[name]
        need(isinstance(obj["id"], str) and len(obj["id"]) < 64 and SKILL_ID.fullmatch(obj["id"]), "技能ID不符")
        version = obj["version"]
        need((name == "generator" and version is None) or (isinstance(version, str) and SEMVER.fullmatch(version)),
             "版本须语义版本，未知生成器版本可null")
    text(record["generated_skill"]["display_name"], "目标显示名")
    text(record["request"]["summary"], "请求")
    text(record["request"]["evidence"], "请求来源")
    for requirement in rows(record["requirements"], "requirements"):
        text(requirement["text"], "要求")
        need(requirement["origin"] in {"explicit", "convention", "task_specific", "inferred"}, "要求来源类型不符")
        need(requirement["status"] in {"met", "partial", "unmet", "unverified", "not_applicable"}, "要求去向状态不符")
        text(requirement["reason"], "要求判断理由")
        evidence(requirement["evidence"], "要求依据", requirement["status"] == "met")
    for check in rows(record["checks"], "checks"):
        text(check["kind"], "检查类型")
        need(check["status"] in {"pass", "fail", "not_run"}, "检查状态不符")
        evidence(check["evidence"], "检查依据", check["status"] != "not_run")
        if check["status"] == "not_run":
            text(check["reason"], "未做原因")
    for artifact in rows(record["artifacts"], "artifacts"):
        need(artifact["kind"] in {"source", "archive", "installed"}, "产物类型不符")
        text(artifact["ref"], "产物位置")
        need(artifact["sha256"] is None or (isinstance(artifact["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", artifact["sha256"])),
             "产物指纹须真实格式或null")
    for issue in rows(record["issues"], "issues"):
        text(issue["description"], "问题")
        need(issue["status"] in {"open", "resolved"}, "问题状态不符")
        evidence(issue["evidence"], "问题来源")
    for feedback in rows(record["feedback"], "feedback"):
        subject(record, feedback)
        time(feedback["at"])
        text(feedback["comment"], "反馈原意")
        text(feedback["evidence"], "真实反馈来源")
        rating = feedback.get("ratings", {})
        need(isinstance(rating, dict) and set(rating) <= RATINGS, "反馈维度不符")
        need(all(value is None or type(value) is bool for value in rating.values()), "反馈仅接受实际布尔或null")
    for usage in rows(record["usage"], "usage"):
        subject(record, usage)
        time(usage["at"])
        text(usage["scope"], "实际使用范围")
        need(usage["result"] in {"pass", "fail", "blocked", "inconclusive"}, "实际使用状态不符")
        evidence(usage["evidence"], "实际使用依据", True)
    need(isinstance(record["benefit_measurements"], list), "收益需数组")
    for measurement in record["benefit_measurements"]:
        need(measurement["subject"] in SUBJECTS, "收益对象不符")
        for field in ["metric", "unit", "scope", "evidence"]:
            text(measurement[field], "收益" + field)
        need(all(type(measurement.get(field)) in {int, float} and math.isfinite(measurement[field])
                 for field in ["before", "after"]), "收益缺有限数值前后基线")
    for proposal in rows(record["improvement_proposals"], "improvement_proposals"):
        text(proposal["proposal"], "改进提案")
        text(proposal["evidence"], "提案依据")
        need(proposal["status"] in {"proposed", "applied", "rejected"}, "提案状态不符")
        if proposal["status"] == "applied":
            text(proposal["applied_version"], "应用版本")
    return record


def summarize(record):
    latest = {}
    for feedback in sorted(record["feedback"], key=lambda row: time(row["at"])):
        for dimension, value in feedback.get("ratings", {}).items():
            latest[(feedback["subject"], dimension)] = value
    ratings = {}
    for target in sorted(SUBJECTS):
        ratings[target] = {}
        for dimension in sorted(RATINGS):
            value = latest.get((target, dimension))
            ratings[target][dimension] = {"value": value, "rated": int(value is not None),
                                          "status": "未评价" if value is None else "实际对象评价，非逐要求评分"}
    return {
        "run_id": record["run_id"], "revision": record["revision"],
        "generator": record["generator"], "generated_skill": record["generated_skill"],
        "requirements_open": [r for r in record["requirements"] if r["status"] in {"partial", "unmet", "unverified"}],
        "checks_failed_or_not_run": [c for c in record["checks"] if c["status"] != "pass"],
        "issues_open": [i for i in record["issues"] if i["status"] == "open"],
        "requirement_counts": dict(collections.Counter(r["status"] for r in record["requirements"])),
        "check_counts": dict(collections.Counter(c["status"] for c in record["checks"])),
        "artifacts": record["artifacts"], "ratings": ratings, "feedback_events": record["feedback"],
        "usage": {target: {"status": "尚无使用记录" if not any(u["subject"] == target for u in record["usage"]) else "仅有记录的实际范围",
                          "counts": dict(collections.Counter(u["result"] for u in record["usage"] if u["subject"] == target))}
                  for target in sorted(SUBJECTS)},
        "usage_events": record["usage"], "benefit_measurements": record["benefit_measurements"],
        "benefit_note": "没有可比前后基线时收益尚不能判断；自测、文件数、关闭率和业务通过率不是技能有效性。",
        "improvement_proposals": record["improvement_proposals"],
        "evidence_limit": "只核对记录结构与所述范围，未读取引用产物或重新验证目标业务；生成质量和目标效果不混算。"
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="+")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)
    try:
        records = [load(path) for path in args.records]
        need(len({r["run_id"] for r in records}) == len(records), "run_id重复；同批次只选一个revision")
        summaries = [summarize(r) for r in records]
        if args.format == "json":
            print(json.dumps(summaries, ensure_ascii=False, indent=2))
        else:
            for summary in summaries:
                print(f'生成批次 {summary["run_id"]}｜revision {summary["revision"]}｜目标 {summary["generated_skill"]["display_name"]} {summary["generated_skill"]["version"]}')
                print("生成器：" + summary["generator"]["id"] + "；版本：" + (summary["generator"]["version"] or "未提供"))
                for label, key in [("未满足/未核实要求", "requirements_open"), ("失败/未做检查", "checks_failed_or_not_run"),
                                   ("未关闭问题", "issues_open"), ("要求去向", "requirement_counts"),
                                   ("验证记录", "check_counts"), ("产物", "artifacts"), ("实际评价", "ratings"),
                                   ("原始反馈", "feedback_events"), ("实际使用", "usage"),
                                   ("收益原始记录", "benefit_measurements"), ("改进提案", "improvement_proposals")]:
                    print(label + "：" + json.dumps(summary[key], ensure_ascii=False))
                print(summary["benefit_note"])
                print(summary["evidence_limit"])
        return 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print("生成记录检查失败：" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
