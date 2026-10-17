#!/usr/bin/env python3
"""Lossless review-case JSON -> modern XMind; read-only checks and feedback view."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import uuid
import zipfile

SKILL_ID = "system-testcase-xmind"
VERSION = "1.0.0"
MISSING = "未提供（源文未记录）"
CORE_FIELDS = ("前置条件", "测试数据", "操作步骤", "预期结果")
BOTTOMLINE = {
    "confirmed": "已核定底线", "candidate": "底线候选",
    "substitutable": "有替代", "not_bottomline": "非底线", "unassessed": "未评估",
}
CHECK_STATUSES = {
    "integrity": {"pass", "fail"},
    "source_review": {"not_checked", "pass", "fail"},
    "desktop_open": {"not_checked", "pass", "fail"},
    "readability": {"not_evaluated", "pass", "fail"},
}
KINDS = ("openability", "readability", "omission", "mapping", "other")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, where):
    require(isinstance(value, str) and bool(value.strip()), f"{where}: expected nonempty string")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value),
            f"{where}: unsupported control character")
    return value


def obj(value, allowed, required, where):
    require(isinstance(value, dict), f"{where}: expected object")
    require(not set(value) - set(allowed), f"{where}: unknown keys {set(value) - set(allowed)}")
    require(set(required) <= set(value), f"{where}: missing keys {set(required) - set(value)}")


def string_list(value, where, nonempty=False):
    require(isinstance(value, list) and (bool(value) or not nonempty), f"{where}: expected array")
    for item in value:
        text(item, where)


def json_value(value):
    if isinstance(value, str):
        # Blank strings are allowed as source gaps.
        require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value),
                "field content: unsupported control character")
    elif value is None or type(value) in (bool, int):
        pass
    elif type(value) is float:
        require(math.isfinite(value), "non-finite number")
    elif isinstance(value, list):
        for item in value:
            json_value(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            text(key, "field key")
            json_value(item)
    else:
        raise ValueError("unsupported field content")


def duplicate_safe(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(raw):
    def bad_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    return json.loads(raw, object_pairs_hook=duplicate_safe, parse_constant=bad_constant)


def read_json(path):
    return loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hash_text(value, where):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), f"{where}: invalid SHA-256")


def validate(data):
    obj(data, {"schema_version", "title", "scope", "source_documents", "cases"},
        {"schema_version", "title", "scope", "source_documents", "cases"}, "input")
    require(data["schema_version"] == "1.0", "unsupported schema_version")
    text(data["title"], "title")
    text(data["scope"], "scope")
    docs = data["source_documents"]
    require(isinstance(docs, list) and bool(docs), "source_documents: expected nonempty array")
    doc_ids = set()
    for doc in docs:
        obj(doc, {"id", "path", "version", "sha256"}, {"id", "path"}, "document")
        did = text(doc["id"], "document.id")
        require(did not in doc_ids, f"duplicate document id: {did}")
        doc_ids.add(did)
        text(doc["path"], "document.path")
        if doc.get("version") is not None:
            text(doc["version"], "document.version")
        if doc.get("sha256") is not None:
            hash_text(doc["sha256"], "document.sha256")
    cases = data["cases"]
    require(isinstance(cases, list) and bool(cases), "cases: expected nonempty array")
    ids = set()
    for case in cases:
        obj(case, {"id", "original_id", "title", "group", "source_refs", "priority",
                   "design_status", "bottomline", "fields"},
            {"id", "title", "group", "source_refs", "fields"}, "case")
        cid = text(case["id"], "case.id")
        require(cid == cid.strip() and cid not in ids, f"duplicate/whitespace case id: {cid}")
        ids.add(cid)
        text(case["title"], f"{cid}.title")
        if "original_id" in case and case["original_id"] is not None:
            require(case["original_id"] == cid, f"{cid}: preserve original id or use null for imported id")
        string_list(case["group"], f"{cid}.group", True)
        for name in ("priority", "design_status"):
            if name in case:
                text(case[name], f"{cid}.{name}")
        refs = case["source_refs"]
        require(isinstance(refs, list), f"{cid}.source_refs: expected array")
        for ref in refs:
            obj(ref, {"document_id", "locator"}, {"document_id", "locator"}, f"{cid}.source_ref")
            require(ref["document_id"] in doc_ids, f"{cid}: unknown source document")
            text(ref["locator"], f"{cid}.locator")
        if "bottomline" in case:
            bl = case["bottomline"]
            obj(bl, {"status", "basis"}, {"status", "basis"}, f"{cid}.bottomline")
            require(bl["status"] in BOTTOMLINE, f"{cid}: unknown bottomline status")
            string_list(bl["basis"], f"{cid}.bottomline.basis")
            require(bl["status"] != "confirmed" or (bool(bl["basis"]) and bool(refs)),
                    f"{cid}: confirmed needs imported basis and source")
        require(isinstance(case["fields"], list) and bool(case["fields"]), f"{cid}: fields required")
        field_names = set()
        for field in case["fields"]:
            obj(field, {"name", "content"}, {"name", "content"}, f"{cid}.field")
            name = text(field["name"], f"{cid}.field.name")
            require(name not in field_names, f"{cid}: duplicate field name {name}")
            field_names.add(name)
            json_value(field["content"])


def node_id(*parts):
    key = json.dumps([SKILL_ID, *parts], ensure_ascii=False, separators=(",", ":"))
    return uuid.uuid5(uuid.NAMESPACE_URL, key).hex


def topic(title, key, children=None, note=None, labels=None):
    result = {"id": node_id(*key), "class": "topic", "title": title}
    if children:
        result["children"] = {"attached": children}
    if note:
        result["notes"] = {"plain": {"content": note + "\n"}}
    if labels:
        result["labels"] = labels
    return result


def empty(value):
    return value is None or (isinstance(value, str) and not value.strip()) or (
        isinstance(value, (dict, list)) and len(value) == 0)


def value_topic(label, value, key):
    if empty(value):
        return topic(label, key, [topic(MISSING, [*key, "missing"])])
    if isinstance(value, list):
        return topic(label, key, [value_topic(str(i + 1), x, [*key, "item", i])
                                  for i, x in enumerate(value)])
    if isinstance(value, dict):
        return topic(label, key, [value_topic(k, v, [*key, "key", k]) for k, v in value.items()])
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, allow_nan=False)
    return topic(label, key, [topic(content, [*key, "value"])])


def bottomline(case):
    return case.get("bottomline", {}).get("status", "unassessed")


def empty_paths(value, prefix):
    if empty(value):
        return [prefix]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in empty_paths(v, prefix + " → " + k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in empty_paths(v, prefix + f"[{i + 1}]")]
    return []


def missing_fields(data):
    result = []
    for case in data["cases"]:
        by_name = {x["name"]: x["content"] for x in case["fields"]}
        missing = [name for name in CORE_FIELDS if name not in by_name]
        missing += [p for field in case["fields"] for p in empty_paths(field["content"], field["name"])]
        if not case["source_refs"]:
            missing.append("来源定位")
        if missing:
            result.append({"case_id": case["id"], "fields": missing})
    return result


def source_note(case, docs):
    lines = ["来源定位："]
    for ref in case["source_refs"]:
        doc = docs[ref["document_id"]]
        lines.append(f'{doc["id"]}｜{doc["path"]}｜版本：{doc.get("version") or "未提供"}'
                     f'｜SHA-256：{doc.get("sha256") or "未取得"}｜{ref["locator"]}')
    if not case["source_refs"]:
        lines.append(MISSING)
    if case.get("original_id", case["id"]) is None:
        lines.append("本编号为导入分配，原文无编号；对应位置见上。")
    return "\n".join(lines)


def workbook(data):
    validate(data)
    docs = {d["id"]: d for d in data["source_documents"]}
    sheets = []
    for mode, title in (("index", "审阅索引"), ("detail", "详细用例")):
        root = topic(data["title"], [mode, "root"], note=(
            f'范围：{data["scope"]}\n唯一用例数：{len(data["cases"])}。'
            "索引是同一用例的引用，不重复计数；转换校验不代表业务覆盖或测试通过。\n来源文档清单：\n"
            + dump(data["source_documents"]).rstrip()))
        groups = {(): root}
        for case in data["cases"]:
            prefix = ()
            for name in case["group"]:
                next_prefix = (*prefix, name)
                if next_prefix not in groups:
                    child = topic(name, [mode, "group", *next_prefix])
                    groups[prefix].setdefault("children", {"attached": []})["attached"].append(child)
                    groups[next_prefix] = child
                prefix = next_prefix
            cid = case["id"]
            labels = [BOTTOMLINE[bottomline(case)]]
            labels.extend(case[k] for k in ("priority", "design_status") if k in case)
            note = source_note(case, docs)
            branches = []
            if mode == "detail":
                note += "\n\n完整归一化用例（原文抽取保真仍需对照源文）：\n" + dump(case).rstrip()
                fields = list(case["fields"])
                names = {x["name"] for x in fields}
                fields.extend({"name": n, "content": None} for n in CORE_FIELDS if n not in names)
                for i, field in enumerate(fields):
                    branches.append(value_topic(field["name"], field["content"], [mode, cid, "field", i]))
                branches.append(value_topic("底线判断（沿用来源）", {
                    "状态": BOTTOMLINE[bottomline(case)],
                    "原有依据": case.get("bottomline", {}).get("basis") or "未提供，不自动核定",
                }, [mode, cid, "bottomline"]))
            else:
                note += f"\n到“详细用例”页按编号 {cid} 查找完整内容。"
            node = topic(f'{cid}｜{case["title"]}', [mode, "case", cid], branches, note, labels)
            groups[prefix].setdefault("children", {"attached": []})["attached"].append(node)
        sheets.append({"id": node_id("sheet", mode), "class": "sheet", "title": title, "rootTopic": root})
    return sheets


def write_xmind(path, data):
    payloads = {
        "content.json": dump(workbook(data)),
        "metadata.json": dump({"creator": {"name": SKILL_ID, "version": VERSION}, "dataStructureVersion": "2"}),
        "manifest.json": dump({"file-entries": {"content.json": {}, "metadata.json": {}}}),
    }
    with zipfile.ZipFile(path, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            archive.writestr(name, content.encode("utf-8"))


def check_xmind(data, path):
    expected = workbook(data)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) == 3 and {i.filename for i in infos} ==
                {"content.json", "metadata.json", "manifest.json"}, "unexpected/duplicate archive entries")
        require(sum(i.file_size for i in infos) <= 128 * 1024 * 1024, "archive exceeds 128 MiB check limit")
        require(not any(i.flag_bits & 1 for i in infos), "encrypted archive unsupported")
        require(archive.testzip() is None, "corrupt archive")
        content = loads(archive.read("content.json").decode("utf-8"))
        metadata = loads(archive.read("metadata.json").decode("utf-8"))
        manifest = loads(archive.read("manifest.json").decode("utf-8"))
    require(content == expected, "XMind differs from input: nodes/fields/notes/labels/order changed")
    require(metadata == {"creator": {"name": SKILL_ID, "version": VERSION}, "dataStructureVersion": "2"},
            "wrong XMind metadata/version")
    require(manifest == {"file-entries": {"content.json": {}, "metadata.json": {}}}, "manifest mismatch")
    return {"status": "pass", "unique_cases": len(data["cases"]), "index_references": len(data["cases"]),
            "detail_cases": len(data["cases"]), "missing_fields": missing_fields(data)}


def counts(data):
    return {"unique_cases": len(data["cases"]), "index_references": len(data["cases"]),
            "bottomline": dict(Counter(bottomline(c) for c in data["cases"]))}


def md(value):
    return str(value).replace("|", "／").replace("\n", " / ").replace("\r", "")


def report(data, result):
    lines = ["# 用例转XMind：转换核对", "", f'范围：{data["scope"]}', "",
             f'唯一用例 {len(data["cases"])} 条，索引引用同为 {len(data["cases"])} 条，不相加。',
             "", "归一化输入到导图的字段、备注、标签和节点回读：通过。",
             "原文抽取核对：尚未核实。客户端实际打开：尚未核实。审阅效果：未评价。",
             "", "## 需关注", ""]
    gaps = result["missing_fields"]
    lines += [f'- {md(g["case_id"])}：{md("、".join(g["fields"]))}' for g in gaps] or ["未发现本协议定义的空字段；不代表原文抽取或业务内容完整。"]
    lines += ["", "## 编号与来源", "", "| 编号 | 业务分组 | 原编号 | 来源定位 |",
              "|---|---|---|---|"]
    for c in data["cases"]:
        refs = "；".join(r["document_id"] + "：" + r["locator"] for r in c["source_refs"]) or MISSING
        lines.append("| " + " | ".join(md(x) for x in (
            c["id"], " → ".join(c["group"]), c.get("original_id", c["id"]) or "原文无编号，导入分配", refs)) + " |")
    lines += ["", "## 校验边界", "",
              "本记录只证明归一化输入到现代JSON格式XMind的转换一致性。须对照原文核对编号集合、数量、共享引用与抽取异常。",
              "尚未在实际XMind客户端打开；客户端显示、旧版兼容和真实审阅帮助需另外记录。转换不代表评审或业务测试通过。",
              "可按编号回收漏项、错配、打开和可读性反馈，追加到同目录xmind-review-record.json，保留历史并增加revision。", ""]
    return "\n".join(lines)


def build(input_path, output_dir):
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).absolute()
    raw = input_path.read_bytes()
    data = loads(raw.decode("utf-8-sig"))
    validate(data)
    require(not output_dir.exists(), "output directory already exists; choose a new batch")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".xmind-stage-", dir=output_dir.parent) as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        normalized = stage / "review-cases.json"
        normalized.write_bytes(dump(data).encode("utf-8"))
        target = stage / "测试用例.xmind"
        write_xmind(target, data)
        result = check_xmind(read_json(normalized), target)
        (stage / "转换核对.md").write_bytes(report(data, result).encode("utf-8"))
        mapping = [{"case_id": c["id"], "original_id": c.get("original_id", c["id"]),
                    "group": c["group"], "source_refs": c["source_refs"],
                    "index_topic_id": node_id("index", "case", c["id"]),
                    "detail_topic_id": node_id("detail", "case", c["id"])} for c in data["cases"]]
        record = {
            "schema_version": "1.0", "run_id": "XMIND-" + uuid.uuid4().hex,
            "revision": 1, "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "skill": {"id": SKILL_ID, "version": VERSION},
            "source_input": {"path": str(input_path), "sha256": hashlib.sha256(raw).hexdigest()},
            "scope": data["scope"], "counts": counts(data), "missing_fields": result["missing_fields"],
            "case_mapping": mapping,
            "checks": {
                "integrity": {"status": "pass", "evidence": ["build后实际回读；归一化JSON到XMind的节点/字段/备注/标签一致"]},
                "source_review": {"status": "not_checked", "evidence": []},
                "desktop_open": {"status": "not_checked", "evidence": []},
                "readability": {"status": "not_evaluated", "evidence": []},
            },
            "artifacts": {key: {"path": str(output_dir / name), "sha256": sha256(stage / name)}
                          for key, name in (("xmind", "测试用例.xmind"), ("normalized", "review-cases.json"),
                                            ("report", "转换核对.md"))},
            "feedback": [],
        }
        (stage / "xmind-review-record.json").write_bytes(dump(record).encode("utf-8"))
        stage.rename(output_dir)
    return {"output_dir": str(output_dir), "run_id": record["run_id"], **result}


def timestamp(value):
    text(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "timestamp must include timezone")
    return parsed


def review(record):
    require(isinstance(record, dict) and record.get("schema_version") == "1.0", "invalid record schema")
    text(record.get("run_id"), "run_id")
    require(type(record.get("revision")) is int and record["revision"] >= 1, "invalid revision")
    timestamp(record.get("created_at"))
    skill = record.get("skill", {})
    require(skill.get("id") == SKILL_ID, "wrong skill record")
    require(isinstance(skill.get("version"), str) and
            re.fullmatch(r"\d+\.\d+\.\d+", skill["version"]), "invalid skill version")
    digest = record.get("artifacts", {}).get("xmind", {}).get("sha256")
    hash_text(digest, "artifact")
    count = record.get("counts", {}).get("unique_cases")
    require(type(count) is int and count >= 1, "invalid case count")
    gaps = record.get("missing_fields")
    require(isinstance(gaps, list), "missing_fields must be array")
    checks = record.get("checks", {})
    unresolved = []
    for name, statuses in CHECK_STATUSES.items():
        item = checks.get(name, {})
        require(item.get("status") in statuses, f"invalid check: {name}")
        string_list(item.get("evidence"), f"{name}.evidence")
        if item["status"] in {"pass", "fail"}:
            require(bool(item["evidence"]), f"{name}: claimed result needs evidence")
        if item["status"] != "pass":
            unresolved.append({"check": name, **item})
    events = record.get("feedback")
    require(isinstance(events, list), "feedback must be array")
    seen, current = set(), {}
    ordered = []
    for event in events:
        obj(event, {"id", "at", "artifact_sha256", "kind", "value", "comment", "evidence"},
            {"id", "at", "artifact_sha256", "kind", "value", "comment", "evidence"}, "feedback")
        eid = text(event["id"], "feedback.id")
        require(eid not in seen, "duplicate feedback id")
        seen.add(eid)
        require(event["artifact_sha256"] == digest, "feedback belongs to different XMind snapshot")
        require(event["kind"] in KINDS, "invalid feedback kind")
        require(event["value"] is None or type(event["value"]) is bool, "feedback.value must be bool/null")
        text(event["comment"], "feedback.comment")
        string_list(event["evidence"], "feedback.evidence", True)
        ordered.append((timestamp(event["at"]), len(ordered), event))
    for _, _, event in sorted(ordered, key=lambda x: (x[0], x[1])):
        current[event["kind"]] = event
    return {
        "run_id": record["run_id"], "revision": record["revision"], "skill": skill,
        "unique_cases": count, "missing_fields": gaps, "unresolved_checks": unresolved,
        "negative_feedback_history": [e for e in events if e["value"] is False],
        "feedback_event_count": len(events),
        "current_feedback": {kind: current.get(kind) for kind in KINDS},
        "boundary": "仅汇总指定记录，未重新核验引用文件、客户端或源文；没有基线不判断效率收益",
    }


def review_text(result):
    lines = [f'批次 {result["run_id"]}；skill {result["skill"]["version"]}；记录修订 {result["revision"]}',
             "需关注："]
    for gap in result["missing_fields"]:
        lines.append(f'- {gap["case_id"]} 缺口：{"、".join(gap["fields"])}')
    for item in result["unresolved_checks"]:
        lines.append(f'- {item["check"]}：{item["status"]}')
    for item in result["negative_feedback_history"]:
        lines.append(f'- 历史负面反馈 {item["id"]}：{item["comment"]}')
    lines += [f'唯一用例：{result["unique_cases"]}；实际反馈事件：{result["feedback_event_count"]}']
    for kind, event in result["current_feedback"].items():
        state = "未评价" if event is None or event["value"] is None else ("满足" if event["value"] else "不满足")
        lines.append(f'- {kind}：{state}' + (f'；{event["comment"]}' if event else ""))
    return "\n".join([*lines, result["boundary"]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--input", type=Path, required=True)
    b.add_argument("--output-dir", type=Path, required=True)
    c = sub.add_parser("check")
    c.add_argument("--input", type=Path, required=True)
    c.add_argument("--xmind", type=Path, required=True)
    r = sub.add_parser("review")
    r.add_argument("--record", type=Path, required=True)
    r.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        if args.command == "build":
            print(dump(build(args.input, args.output_dir)), end="")
        elif args.command == "check":
            print(dump(check_xmind(read_json(args.input), args.xmind)), end="")
        else:
            result = review(read_json(args.record))
            print(dump(result) if args.format == "json" else review_text(result), end="\n")
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
