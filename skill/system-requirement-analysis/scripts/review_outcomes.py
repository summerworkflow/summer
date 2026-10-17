#!/usr/bin/env python3
"""只读检查并汇总指定需求分析记录；不联网、不写回、不判断业务正确性。"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys


STATUSES = (
    "open", "waiting_material", "answered", "applied",
    "not_issue", "deferred", "out_of_scope",
)
KINDS = {
    "rule_conflict", "rule_missing", "material_needed",
    "existing_rule_needed", "configuration_needed",
}
FEEDBACK = {"understood": "能直接看懂", "answerable": "能直接回答", "useful": "对工作有帮助"}
LABELS = {
    "open": "等答案", "waiting_material": "等资料", "answered": "已有答案",
    "applied": "已更新文档", "not_issue": "无需再问", "deferred": "暂缓",
    "out_of_scope": "本期不处理",
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def need(condition, message):
    if not condition:
        raise ValueError(message)


def valid_time(value):
    if not nonempty(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.utcoffset() is not None
    except ValueError:
        return False


def validate_record(record):
    """检查记录的可汇总性，不将机械通过当作语义或业务审核通过。"""
    need(isinstance(record, dict), "记录必须是JSON对象")
    need(record.get("schema_version") == "1.0", "不支持的schema_version，当前为1.0")
    need(record.get("skill_id") == "system-requirement-analysis", "skill_id不匹配")
    need(bool(re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?",
                          str(record.get("skill_version", "")))), "skill_version必须是语义版本")
    for key in ("run_id", "requirement"):
        need(nonempty(record.get(key)), key + "不能为空")
    revision = record.get("revision")
    need(type(revision) is int and revision >= 1, "revision必须是正整数")
    need(valid_time(record.get("created_at")), "created_at须包含真实记录时间和时区")

    sources = record.get("sources")
    need(isinstance(sources, list), "sources必须是数组")
    source_map = {}
    for source in sources:
        need(isinstance(source, dict), "来源必须是对象")
        need(nonempty(source.get("id")), "来源缺少id")
        need(source["id"] not in source_map, "来源id重复：" + source["id"])
        need(nonempty(source.get("path")), "来源缺少可定位path")
        need(nonempty(source.get("version")), "来源缺少version；未知时如实写待确认")
        need(source.get("read_status") in {"read", "partial", "unread"}, "来源read_status无效")
        digest = source.get("sha256")
        need(digest is None or (isinstance(digest, str) and
                               bool(re.fullmatch(r"[0-9a-fA-F]{64}", digest))),
             "sha256须为64位十六进制或null")
        source_map[source["id"]] = source

    coverage = record.get("coverage")
    need(isinstance(coverage, list), "coverage必须是数组")
    for area in coverage:
        need(isinstance(area, dict) and nonempty(area.get("area")), "覆盖项缺少area")
        need(area.get("status") in {"reviewed", "partial", "not_reviewed"}, "覆盖状态无效")
        need(isinstance(area.get("note"), str), "覆盖项note必须是文字")

    questions = record.get("questions")
    need(isinstance(questions, list), "questions必须是数组")
    ids = set()
    for question in questions:
        need(isinstance(question, dict), "问题必须是对象")
        qid = question.get("id")
        need(isinstance(qid, str) and bool(re.fullmatch(r"Q\d{3,}", qid)), "问题编号须为Q001等形式")
        need(qid not in ids, "问题编号重复：" + qid)
        ids.add(qid)
        need(question.get("kind") in KINDS, qid + "：问题类型无效")
        need(question.get("status") in STATUSES, qid + "：问题状态无效")
        for key in ("title", "scenario", "uncertainty", "question", "owner_role", "impact"):
            need(nonempty(question.get(key)), qid + "：缺少" + key)
        need(isinstance(question.get("recommendation"), str), qid + "：recommendation须为文字，可为空")
        refs = question.get("source_refs")
        need(isinstance(refs, list) and bool(refs), qid + "：缺少材料依据")
        distinct_refs = set()
        readable_refs = set()
        for ref in refs:
            need(isinstance(ref, dict) and ref.get("source_id") in source_map,
                 qid + "：引用了不存在的source_id")
            need(nonempty(ref.get("location")), qid + "：来源位置不具体")
            pair = (ref["source_id"], ref["location"])
            need(pair not in distinct_refs, qid + "：来源位置重复")
            distinct_refs.add(pair)
            if source_map[ref["source_id"]]["read_status"] != "unread":
                readable_refs.add(pair)
        if question["kind"] != "material_needed":
            need(bool(readable_refs), qid + "：未读材料不能单独支撑规则或配置结论")
        if question["kind"] == "rule_conflict":
            need(len(readable_refs) >= 2, qid + "：规则冲突至少需两处已读依据")

        resolution = question.get("resolution")
        need(isinstance(resolution, dict), qid + "：缺少resolution")
        if question["status"] in {"answered", "applied"}:
            need(nonempty(resolution.get("answer")) and nonempty(resolution.get("evidence")),
                 qid + "：已有答案必须附实际答案和确认依据")
        applied_to = resolution.get("applied_to")
        need(isinstance(applied_to, list) and all(nonempty(item) for item in applied_to),
             qid + "：applied_to须为非空制品位置组成的数组")
        if question["status"] == "applied":
            need(bool(applied_to), qid + "：文档已更新必须提供制品位置")
        if question["status"] in {"not_issue", "deferred", "out_of_scope"}:
            need(nonempty(resolution.get("reason")) and nonempty(resolution.get("evidence")),
                 qid + "：撤销、延期或范围排除必须有原因和依据")
        feedback = question.get("feedback")
        need(isinstance(feedback, dict), qid + "：缺少feedback")
        rated = False
        for key in FEEDBACK:
            need(key in feedback and (feedback[key] is None or type(feedback[key]) is bool),
                 qid + "：" + key + "只接受true/false/null")
            rated = rated or feedback[key] is not None
        if rated:
            need(nonempty(feedback.get("evidence")), qid + "：效果评价缺少实际反馈来源")
        history = question.get("history")
        need(isinstance(history, list), qid + "：history必须是数组")
        for event in history:
            need(isinstance(event, dict) and valid_time(event.get("at")) and
                 nonempty(event.get("event")) and nonempty(event.get("evidence")),
                 qid + "：历史变化须有时间、事件和依据")

    overall = record.get("overall_feedback", [])
    need(isinstance(overall, list), "overall_feedback必须是数组")
    for item in overall:
        need(isinstance(item, dict) and nonempty(item.get("comment")) and
             nonempty(item.get("evidence")), "整体反馈须包含comment和evidence")
    measurements = record.get("benefit_measurements", [])
    need(isinstance(measurements, list), "benefit_measurements必须是数组")
    for measurement in measurements:
        need(isinstance(measurement, dict), "收益记录必须是对象")
        for key in ("metric", "unit", "scope", "evidence"):
            need(nonempty(measurement.get(key)), "收益记录缺少" + key)
        for key in ("before", "after"):
            number = measurement.get(key)
            need(type(number) in (int, float) and math.isfinite(number) and number >= 0,
                 "收益记录的" + key + "须为非负有限数字")
    proposals = record.get("improvement_proposals", [])
    need(isinstance(proposals, list), "improvement_proposals必须是数组")
    for proposal in proposals:
        need(isinstance(proposal, dict) and nonempty(proposal.get("proposal")) and
             nonempty(proposal.get("evidence")) and
             proposal.get("status") in {"proposed", "applied", "rejected"},
             "改进提案须包含proposal、evidence和有效status")
        if proposal["status"] == "applied":
            need(nonempty(proposal.get("applied_version")), "已应用提案须记录applied_version")
    return record


def ratio(positive, denominator):
    return round(100 * positive / denominator, 1) if denominator else None


def summarize(records):
    need(bool(records), "至少提供一份分析记录")
    groups = defaultdict(list)
    run_ids = set()
    for record in records:
        validate_record(record)
        need(record["run_id"] not in run_ids, "run_id重复，不能重复汇总：" + record["run_id"])
        run_ids.add(record["run_id"])
        groups[record["skill_version"]].append(record)
    output = []
    for version, runs in sorted(groups.items()):
        questions = [question for run in runs for question in run["questions"]]
        counts = Counter(question["status"] for question in questions)
        eligible = len(questions) - counts["not_issue"] - counts["out_of_scope"]
        answered = counts["answered"] + counts["applied"]
        feedback_stats = {}
        for key in FEEDBACK:
            values = [question["feedback"][key] for question in questions]
            positive = sum(value is True for value in values)
            negative = sum(value is False for value in values)
            feedback_stats[key] = {
                "positive": positive, "negative": negative,
                "evaluated": positive + negative,
                "unknown": sum(value is None for value in values),
                "percent": ratio(positive, positive + negative),
            }
        run_details = []
        for run in runs:
            run_details.append({
                "run_id": run["run_id"], "requirement": run["requirement"],
                "revision": run["revision"],
                "overall_feedback": run.get("overall_feedback", []),
                "coverage_gaps": [item for item in run["coverage"] if item["status"] != "reviewed"],
                "coverage_recorded": bool(run["coverage"]),
                "unread_sources": [item for item in run["sources"] if item["read_status"] != "read"],
                "pending": [
                    {key: question[key] for key in ("id", "title", "question", "owner_role", "status")}
                    for question in run["questions"]
                    if question["status"] in {"open", "waiting_material", "deferred"}
                ],
                "answered_not_applied": [
                    {"id": question["id"], "title": question["title"],
                     "answer": question["resolution"]["answer"],
                     "evidence": question["resolution"]["evidence"]}
                    for question in run["questions"] if question["status"] == "answered"
                ],
                "dispositions": [
                    {"id": question["id"], "status": question["status"],
                     "reason": question["resolution"]["reason"],
                     "evidence": question["resolution"]["evidence"]}
                    for question in run["questions"]
                    if question["status"] in {"not_issue", "out_of_scope"}
                ],
            })
        output.append({
            "skill_version": version, "run_count": len(runs),
            "question_count": len(questions),
            "status_counts": {status: counts[status] for status in STATUSES},
            "answer_progress": {
                "answered": answered, "eligible": eligible, "percent": ratio(answered, eligible),
            },
            "feedback": feedback_stats, "runs": run_details,
            "benefit_measurements": [
                {**measurement, "run_id": run["run_id"]}
                for run in runs for measurement in run.get("benefit_measurements", [])
            ],
            "improvement_proposals": [
                {**proposal, "run_id": run["run_id"]}
                for run in runs for proposal in run.get("improvement_proposals", [])
            ],
        })
    return {"schema_version": "1.0", "groups": output}


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def percent(value):
    return "N/A" if value is None else str(value) + "%"


def render_markdown(summary):
    lines = ["# 需求分析：处理进展与使用反馈", "",
             "以下只汇总所提供的记录；不代表业务实现、测试通过或已证明节省时间。", ""]
    for group in summary["groups"]:
        lines.extend(["## Skill " + group["skill_version"], ""])
        for run in group["runs"]:
            lines.extend(["### " + cell(run["requirement"]) + "（" + cell(run["run_id"]) +
                          "，记录修订 " + str(run["revision"]) + "）", "",
                          "还没解决的问题：", ""])
            if run["pending"]:
                lines.extend(["| 编号 | 状态 | 具体要问什么 | 找谁 |",
                              "| --- | --- | --- | --- |"])
                for item in run["pending"]:
                    lines.append("| " + " | ".join(cell(value) for value in (
                        item["id"], LABELS[item["status"]], item["question"], item["owner_role"])) + " |")
            else:
                lines.append("记录中没有待处理问题；仍须结合下方未读范围判断分析是否完整。")
            lines.extend(["", "已有答案但尚未记录文档更新：", ""])
            if run["answered_not_applied"]:
                for item in run["answered_not_applied"]:
                    lines.append("- " + cell(item["id"] + "：" + item["answer"]) +
                                 "；依据：" + cell(item["evidence"]))
            else:
                lines.append("无。")
            lines.extend(["", "未读或部分覆盖：", ""])
            if not run["coverage_recorded"]:
                lines.append("- 未记录分析覆盖范围，不能认定已经全审。")
            for area in run["coverage_gaps"]:
                lines.append("- " + cell(area["area"]) + "：" + cell(area["status"]) +
                             "；" + cell(area["note"]))
            for source in run["unread_sources"]:
                lines.append("- 材料 " + cell(source["path"]) + "：" + cell(source["read_status"]))
            if run["coverage_recorded"] and not run["coverage_gaps"] and not run["unread_sources"]:
                lines.append("所提供记录没有标注未读范围；此处不做独立语义审核。")
            if run["dispositions"]:
                lines.extend(["", "无需再问或本期不处理：", ""])
                for item in run["dispositions"]:
                    lines.append("- " + cell(item["id"]) + "（" + LABELS[item["status"]] + "）：" +
                                 cell(item["reason"]) + "；依据：" + cell(item["evidence"]))
            if run["overall_feedback"]:
                lines.extend(["", "使用者对整份清单的反馈（不代替逐题评价）：", ""])
                for item in run["overall_feedback"]:
                    lines.append("- " + cell(item["comment"]) + "；来源：" + cell(item["evidence"]))
            lines.append("")
        progress = group["answer_progress"]
        lines.extend(["### 处理进展与反馈", "",
                      "- 记录：" + str(group["run_count"]) + "份；问题：" + str(group["question_count"]) + "项。",
                      "- 已取得答案：" + str(progress["answered"]) + "/" + str(progress["eligible"]) +
                      "（" + percent(progress["percent"]) + "）；不包含无需再问和范围排除项。",
                      "- 已记录文档更新：" + str(group["status_counts"]["applied"]) + "项。",
                      "- 各状态：" + "、".join(LABELS[key] + str(group["status_counts"][key])
                                              for key in STATUSES) + "。"])
        for key, label in FEEDBACK.items():
            stats = group["feedback"][key]
            lines.append("- " + label + "：" + percent(stats["percent"]) +
                         "；有反馈" + str(stats["evaluated"]) + "项（是" + str(stats["positive"]) +
                         "、否" + str(stats["negative"]) + "），未评价" + str(stats["unknown"]) + "项。")
        if group["benefit_measurements"]:
            lines.extend(["", "已提供的前后记录（可比性仍需核对）：", ""])
            for item in group["benefit_measurements"]:
                lines.append("- " + cell(item["run_id"]) + " / " + cell(item["metric"]) + "：" +
                             str(item["before"]) + " → " + str(item["after"]) + cell(item["unit"]) +
                             "；范围：" + cell(item["scope"]) + "；依据：" + cell(item["evidence"]))
        else:
            lines.extend(["", "节省时间/减少返工：尚不能判断，未提供可比较的前后记录。"])
        lines.extend(["", "改进提案：", ""])
        if group["improvement_proposals"]:
            for item in group["improvement_proposals"]:
                lines.append("- " + cell(item["proposal"]) + "（" + cell(item["status"]) +
                             "）；依据：" + cell(item["evidence"]))
        else:
            lines.append("暂无记录。")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="+", type=Path, help="明确指定的analysis-record.json")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    try:
        records = []
        for path in args.records:
            try:
                records.append(validate_record(json.loads(path.read_text(encoding="utf-8-sig"))))
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError(str(path) + "：" + str(exc)) from exc
        summary = summarize(records)
    except ValueError as exc:
        print("无法汇总：" + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2)
          if args.format == "json" else render_markdown(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
