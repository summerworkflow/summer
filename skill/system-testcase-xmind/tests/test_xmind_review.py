"""Synthetic conversion invariants; no business execution or real user feedback."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xmind_review", ROOT / "scripts/xmind_review.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def fixture():
    return json.loads((ROOT / "assets/example-cases.json").read_text(encoding="utf-8"))


def walk(node):
    yield node
    for child in node.get("children", {}).get("attached", []):
        yield from walk(child)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = fixture()
        self.input = self.root / "input.json"
        self.input.write_text(m.dump(self.data), encoding="utf-8")
        self.out = self.root / "batch"

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return m.build(self.input, self.out)

    def replace_archive(self, name, transform):
        path = self.out / "测试用例.xmind"
        with zipfile.ZipFile(path) as z:
            files = {n: z.read(n) for n in z.namelist()}
        files[name] = m.dump(transform(json.loads(files[name]))).encode("utf-8")
        with zipfile.ZipFile(path, "w") as z:
            for key, value in files.items():
                z.writestr(key, value)

    def record(self):
        self.build()
        return m.read_json(self.out / "xmind-review-record.json")

    def event(self, record, **overrides):
        event = {"id": "FB-1", "at": "2026-10-17T15:00:00+08:00",
                 "artifact_sha256": record["artifacts"]["xmind"]["sha256"],
                 "kind": "readability", "value": False, "comment": "虚构评价：复杂步骤不易定位",
                 "evidence": ["虚构测试夹具，不是真实用户反馈"]}
        event.update(overrides)
        return event

    def test_package_roundtrip_and_unique_count(self):
        result = self.build()
        self.assertEqual(result["unique_cases"], 3)
        result = m.check_xmind(m.read_json(self.out / "review-cases.json"), self.out / "测试用例.xmind")
        self.assertEqual(result["index_references"], 3)
        with zipfile.ZipFile(self.out / "测试用例.xmind") as z:
            self.assertEqual(len(json.loads(z.read("content.json"))), 2)
            self.assertIn("metadata.json", json.loads(z.read("manifest.json"))["file-entries"])

    def test_original_fields_in_native_notes_and_visible_nodes(self):
        sheets = m.workbook(self.data)
        detail = list(walk(sheets[1]["rootTopic"]))
        for case in self.data["cases"]:
            node = next(n for n in detail if n["id"] == m.node_id("detail", "case", case["id"]))
            raw = node["notes"]["plain"]["content"].split("完整归一化用例（原文抽取保真仍需对照源文）：\n", 1)[1]
            self.assertEqual(json.loads(raw), case)
        titles = [n["title"] for n in detail]
        self.assertIn("A < B & C\n第二行：中文、引号\"与反斜杠\\", titles)
        self.assertIn("false", titles)
        self.assertIn("0", titles)
        self.assertIn("对应检查", titles)

    def test_p0_candidate_is_never_promoted(self):
        sheets = m.workbook(self.data)
        for sheet in sheets:
            node = next(n for n in walk(sheet["rootTopic"]) if n["title"].startswith("DEMO-001｜"))
            self.assertIn("底线候选", node["labels"])
            self.assertNotIn("已核定底线", node["labels"])

    def test_duplicate_case_is_rejected_before_writing(self):
        self.data["cases"].append(copy.deepcopy(self.data["cases"][0]))
        self.input.write_text(m.dump(self.data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()
        self.assertFalse(self.out.exists())

    def test_unknown_field_does_not_disappear(self):
        self.data["cases"][0]["cleanup"] = "不能静默丢弃"
        with self.assertRaisesRegex(ValueError, "unknown"):
            m.validate(self.data)

    def test_unknown_document_and_empty_group_are_rejected(self):
        for mutation in ("doc", "group"):
            data = fixture()
            if mutation == "doc":
                data["cases"][0]["source_refs"][0]["document_id"] = "NOT-FOUND"
            else:
                data["cases"][0]["group"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.validate(data)

    def test_duplicate_field_names_rejected(self):
        self.data["cases"][0]["fields"].append(copy.deepcopy(self.data["cases"][0]["fields"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            m.validate(self.data)

    def test_confirmed_needs_basis_and_source(self):
        for field, value in (("basis", []), ("refs", [])):
            data = fixture()
            case = data["cases"][0]
            case["bottomline"]["status"] = "confirmed"
            case["bottomline"]["basis"] = ["虚构已核定依据"]
            if field == "basis":
                case["bottomline"]["basis"] = value
            else:
                case["source_refs"] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "confirmed"):
                m.validate(data)

    def test_all_five_bottomline_labels_distinct(self):
        self.data["cases"] = []
        for i, status in enumerate(m.BOTTOMLINE):
            case = copy.deepcopy(fixture()["cases"][0])
            case["id"] = f"CASE-{i}"
            case["bottomline"] = {"status": status, "basis": ["虚构来源已有判断"]}
            self.data["cases"].append(case)
        nodes = list(walk(m.workbook(self.data)[0]["rootTopic"]))
        labels = [n["labels"][0] for n in nodes if "labels" in n]
        self.assertEqual(set(labels), set(m.BOTTOMLINE.values()))

    def test_gaps_include_nested_expectation_but_not_zero_or_false(self):
        self.data["cases"][0]["fields"][2]["content"][0]["对应检查"] = None
        gaps = m.missing_fields(self.data)
        first = next(g for g in gaps if g["case_id"] == "DEMO-001")
        self.assertIn("操作步骤[1] → 对应检查", first["fields"])
        self.assertNotIn("IMPORT-001", [g["case_id"] for g in gaps])
        second = next(g for g in gaps if g["case_id"] == "DEMO-002")
        self.assertIn("预期结果", second["fields"])

    def test_missing_core_field_rendered_as_gap_and_import_id_mapped(self):
        self.data["cases"][0]["fields"] = self.data["cases"][0]["fields"][1:]
        sheets = m.workbook(self.data)
        node = next(n for n in walk(sheets[1]["rootTopic"]) if n["id"] == m.node_id("detail", "case", "DEMO-001"))
        self.assertIn("前置条件", [n["title"] for n in walk(node)])
        self.assertIn(m.MISSING, [n["title"] for n in walk(node)])
        record = self.record()
        imported = next(c for c in record["case_mapping"] if c["case_id"] == "IMPORT-001")
        self.assertIsNone(imported["original_id"])

    def test_same_named_group_different_parents_distinct(self):
        self.data["cases"][0]["group"] = ["付款", "校验"]
        self.data["cases"][1]["group"] = ["审批", "校验"]
        nodes = list(walk(m.workbook(self.data)[0]["rootTopic"]))
        groups = [n for n in nodes if n["title"] == "校验"]
        self.assertEqual(len(groups), 2)
        self.assertNotEqual(groups[0]["id"], groups[1]["id"])

    def test_long_text_not_truncated(self):
        long_text = "中文<>&\n" * 1500
        self.data["cases"][0]["fields"][0]["content"] = long_text
        nodes = list(walk(m.workbook(self.data)[1]["rootTopic"]))
        self.assertIn(long_text, [n["title"] for n in nodes])

    def test_check_detects_deleted_field_or_changed_note(self):
        for mutation in ("field", "note"):
            with self.subTest(mutation=mutation):
                if self.out.exists():
                    path = self.out / "测试用例.xmind"
                    path.unlink()
                    m.write_xmind(path, self.data)
                else:
                    self.build()
                def transform(sheets):
                    node = next(n for n in walk(sheets[1]["rootTopic"]) if n["id"] == m.node_id("detail", "case", "DEMO-001"))
                    if mutation == "field":
                        node["children"]["attached"].pop(0)
                    else:
                        node["notes"]["plain"]["content"] = "被改写"
                    return sheets
                self.replace_archive("content.json", transform)
                with self.assertRaisesRegex(ValueError, "differs"):
                    m.check_xmind(self.data, self.out / "测试用例.xmind")

    def test_check_rejects_invalid_manifest(self):
        self.build()
        self.replace_archive("manifest.json", lambda x: {"file-entries": {}})
        with self.assertRaisesRegex(ValueError, "manifest"):
            m.check_xmind(self.data, self.out / "测试用例.xmind")

    def test_input_and_existing_reviewed_output_are_not_overwritten(self):
        before = self.input.read_bytes()
        self.build()
        old = (self.out / "测试用例.xmind").read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.build()
        self.assertEqual(self.input.read_bytes(), before)
        self.assertEqual((self.out / "测试用例.xmind").read_bytes(), old)

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in ('{"id":1,"id":2}', '{"value": NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                m.loads(raw)

    def test_default_record_has_no_fabricated_real_effect(self):
        record = self.record()
        result = m.review(record)
        self.assertEqual(record["feedback"], [])
        self.assertEqual(len(result["unresolved_checks"]), 3)
        self.assertTrue(all(e is None for e in result["current_feedback"].values()))
        self.assertEqual(record["skill"]["version"], "1.0.0")

    def test_feedback_time_order_null_retraction_and_history_preserved(self):
        record = self.record()
        later = self.event(record, id="FB-2", at="2026-10-17T16:00:00+08:00", value=None)
        earlier = self.event(record)
        record["feedback"] = [later, earlier]
        result = m.review(record)
        self.assertIsNone(result["current_feedback"]["readability"]["value"])
        self.assertEqual(len(result["negative_feedback_history"]), 1)
        self.assertEqual(result["feedback_event_count"], 2)

    def test_feedback_wrong_snapshot_duplicate_id_fake_boolean_rejected(self):
        base = self.record()
        for mutation in ("hash", "id", "bool", "evidence", "time"):
            record = copy.deepcopy(base)
            event = self.event(record)
            if mutation == "hash":
                event["artifact_sha256"] = "0" * 64
            elif mutation == "bool":
                event["value"] = 1
            elif mutation == "evidence":
                event["evidence"] = []
            elif mutation == "time":
                event["at"] = "2026-10-17T15:00:00"
            record["feedback"] = [event, copy.deepcopy(event)] if mutation == "id" else [event]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.review(record)

    def test_claimed_desktop_pass_needs_evidence(self):
        record = self.record()
        record["checks"]["desktop_open"]["status"] = "pass"
        with self.assertRaisesRegex(ValueError, "evidence"):
            m.review(record)

    def test_review_does_not_follow_paths_or_modify_record(self):
        record = self.record()
        record["artifacts"]["xmind"]["path"] = "https://invalid.example/no-follow"
        path = self.root / "record.json"
        path.write_text(m.dump(record), encoding="utf-8")
        before = path.read_bytes()
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(ROOT / "scripts/xmind_review.py"),
                                 "review", "--record", str(path), "--format", "json"],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["unique_cases"], 3)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
