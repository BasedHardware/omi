import importlib.util
import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Dynamically load the memories_to_opml module to run cleanly in isolation
recipe_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_opml.py"
spec = importlib.util.spec_from_file_location("memories_to_opml", recipe_path)
memories_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memories_module)

create_opml = memories_module.create_opml
get_opml_string = memories_module.get_opml_string
extract_memories = memories_module.extract_memories
filter_memories = memories_module.filter_memories
atomic_write = memories_module.atomic_write
strip_surrogates = memories_module.strip_surrogates


class TestMemoriesToOpml(unittest.TestCase):
    def setUp(self):
        self.test_output = "test_memories_output.opml"
        self.partial_output = "test_memories_output.opml.partial"
        self.test_input = "test_memories_input.json"
        for p in (self.test_output, self.partial_output, self.test_input):
            if os.path.exists(p):
                os.remove(p)

    def tearDown(self):
        for p in (self.test_output, self.partial_output, self.test_input):
            if os.path.exists(p):
                os.remove(p)

    def test_basic_memory_export(self):
        data = [
            {
                "id": "mem_01",
                "content": "Alex prefers dark roast coffee",
                "category": "lifestyle",
                "created_at": "2026-10-06T12:00:00Z",
                "tags": ["coffee", "preferences"],
                "visibility": "public"
            }
        ]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        self.assertIn('<opml version="2.0">', xml_str)
        self.assertIn('<title>Omi Memories</title>', xml_str)
        self.assertIn('text="Alex prefers dark roast coffee"', xml_str)
        self.assertIn('category="lifestyle"', xml_str)
        self.assertIn('_tags="#coffee #preferences"', xml_str)
        self.assertIn('_visibility="public"', xml_str)
        self.assertIn('_id="mem_01"', xml_str)

    def test_category_hierarchical_grouping(self):
        data = [
            {"content": "Work task 1", "category": "work"},
            {"content": "Work task 2", "category": "work"},
            {"content": "Learned Rust lifetimes", "category": "skills"}
        ]
        opml = create_opml(data, flat=False)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        body = root.find("body")
        self.assertIsNotNone(body)

        category_nodes = body.findall("outline")
        category_titles = [c.attrib.get("text") for c in category_nodes]
        self.assertIn("Work", category_titles)
        self.assertIn("Skills", category_titles)

        work_node = [c for c in category_nodes if c.attrib.get("text") == "Work"][0]
        work_memories = work_node.findall("outline")
        self.assertEqual(len(work_memories), 2)

    def test_flat_export(self):
        data = [
            {"content": "Note 1", "category": "work"},
            {"content": "Note 2", "category": "personal"}
        ]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        body = root.find("body")
        outlines = body.findall("outline")
        # Direct memory outlines without category wrappers
        self.assertEqual(len(outlines), 2)
        self.assertEqual(outlines[0].attrib["text"], "Note 1")
        self.assertEqual(outlines[1].attrib["text"], "Note 2")

    def test_envelope_extraction(self):
        bare_list = [{"content": "Memory A"}]
        wrapped_dict = {"memories": [{"content": "Memory B"}]}
        empty_envelope = {"memories": []}

        self.assertEqual(len(extract_memories(bare_list)), 1)
        self.assertEqual(len(extract_memories(wrapped_dict)), 1)
        self.assertEqual(len(extract_memories(empty_envelope)), 0)

    def test_category_filtering(self):
        data = [
            {"content": "Work memory", "category": "work"},
            {"content": "Personal memory", "category": "personal"},
            {"content": "Skill memory", "category": "skills"}
        ]
        filtered = filter_memories(data, "work,skills")
        self.assertEqual(len(filtered), 2)
        cats = [it["category"] for it in filtered]
        self.assertIn("work", cats)
        self.assertIn("skills", cats)
        self.assertNotIn("personal", cats)

    def test_lone_surrogates_sanitization(self):
        # Lone surrogate \ud800 should be safely dropped without raising UnicodeEncodeError
        bad_text = "Corrupted \ud800 text"
        clean = strip_surrogates(bad_text)
        self.assertEqual(clean, "Corrupted  text")

        data = [{"content": bad_text, "category": "test"}]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        self.assertIn('text="Corrupted  text"', xml_str)

    def test_xml_escaping(self):
        data = [{"content": "Test & < > \" ' 💡"}]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outline = root.find(".//body/outline")
        self.assertIsNotNone(outline)
        self.assertEqual(outline.attrib["text"], "Test & < > \" ' 💡")

    def test_missing_and_null_fields(self):
        data = [
            {"content": None, "category": None, "tags": None, "visibility": None},
            {}
        ]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outlines = root.findall(".//body/outline")
        self.assertEqual(len(outlines), 2)
        for o in outlines:
            self.assertEqual(o.attrib["text"], "Untitled memory")

    def test_empty_input(self):
        opml = create_opml([])
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outlines = root.findall(".//body/outline")
        self.assertEqual(len(outlines), 0)
        self.assertEqual(root.tag, "opml")

    def test_atomic_write(self):
        atomic_write(self.test_output, "<opml>test</opml>")
        self.assertTrue(os.path.exists(self.test_output))
        self.assertFalse(os.path.exists(self.partial_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "<opml>test</opml>")

    def test_cli_invocation(self):
        with open(self.test_input, "w", encoding="utf-8") as f:
            json.dump([{"content": "CLI Memory Test", "category": "work"}], f)

        res = subprocess.run(
            [sys.executable, str(recipe_path), self.test_input, self.test_output],
            capture_output=True,
            text=True,
            check=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.exists(self.test_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("CLI Memory Test", content)
            self.assertIn('text="Work"', content)


if __name__ == "__main__":
    unittest.main()
