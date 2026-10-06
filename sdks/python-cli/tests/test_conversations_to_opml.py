import importlib.util
import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

# Dynamically load the conversations_to_opml module to run cleanly in isolation
recipe_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_opml.py"
spec = importlib.util.spec_from_file_location("conversations_to_opml", recipe_path)
conversations_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conversations_module)

create_opml = conversations_module.create_opml
get_opml_string = conversations_module.get_opml_string
extract_conversations = conversations_module.extract_conversations
filter_conversations = conversations_module.filter_conversations
atomic_write = conversations_module.atomic_write
strip_surrogates = conversations_module.strip_surrogates


class TestConversationsToOpml(unittest.TestCase):
    def setUp(self):
        self.test_output = "test_conversations_output.opml"
        self.partial_output = "test_conversations_output.opml.partial"
        self.test_input = "test_conversations_input.json"
        for p in (self.test_output, self.partial_output, self.test_input):
            if os.path.exists(p):
                os.remove(p)

    def tearDown(self):
        for p in (self.test_output, self.partial_output, self.test_input):
            if os.path.exists(p):
                os.remove(p)

    def test_basic_conversation_export(self):
        data = [
            {
                "id": "conv_01",
                "started_at": "2026-10-06T15:30:00Z",
                "structured": {
                    "title": "Quarterly Product Strategy",
                    "category": "work",
                    "overview": "Discussed Q4 roadmap priorities and developer tooling.",
                    "action_items": [
                        {"description": "Publish OPML export recipe", "completed": True},
                        {"description": "Review PR benchmarks", "completed": False, "due_at": "2026-10-10"}
                    ]
                },
                "transcript_segments": [
                    {"speaker": "Speaker 0", "text": "Let's align on Q4 goals.", "start": 0.0},
                    {"speaker": "Speaker 1", "text": "Agreed, developer experience is top priority.", "start": 15.5}
                ]
            }
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertIn('<opml version="2.0">', xml_str)
        self.assertIn('<title>Omi Conversations</title>', xml_str)
        self.assertIn('text="Quarterly Product Strategy"', xml_str)
        self.assertIn('category="work"', xml_str)
        self.assertIn('created="2026-10-06T15:30:00Z"', xml_str)
        self.assertIn('_id="conv_01"', xml_str)

        # Parse XML tree to verify hierarchy
        root = ET.fromstring(xml_str.encode("utf-8"))
        conv_outline = root.find(".//body/outline")
        self.assertIsNotNone(conv_outline)
        self.assertEqual(conv_outline.attrib["text"], "Quarterly Product Strategy")

        child_nodes = conv_outline.findall("outline")
        child_texts = [c.attrib.get("text") for c in child_nodes]
        self.assertTrue(any(t.startswith("Overview:") for t in child_texts))
        self.assertIn("Action Items", child_texts)
        self.assertIn("Transcript", child_texts)

        # Verify action items
        ai_node = [c for c in child_nodes if c.attrib.get("text") == "Action Items"][0]
        ai_items = ai_node.findall("outline")
        self.assertEqual(len(ai_items), 2)
        self.assertEqual(ai_items[0].attrib["_status"], "completed")
        self.assertEqual(ai_items[1].attrib["_status"], "open")
        self.assertEqual(ai_items[1].attrib["due"], "2026-10-10")

        # Verify transcript
        tr_node = [c for c in child_nodes if c.attrib.get("text") == "Transcript"][0]
        tr_items = tr_node.findall("outline")
        self.assertEqual(len(tr_items), 2)
        self.assertIn("[00:00] Speaker 0:", tr_items[0].attrib["text"])
        self.assertIn("[00:15] Speaker 1:", tr_items[1].attrib["text"])

    def test_flat_export(self):
        data = [
            {
                "id": "c1",
                "structured": {"title": "Call 1", "overview": "Some overview"},
                "transcript_segments": [{"text": "Hello"}]
            },
            {
                "id": "c2",
                "structured": {"title": "Call 2"}
            }
        ]
        opml = create_opml(data, flat=True)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        body = root.find("body")
        outlines = body.findall("outline")
        self.assertEqual(len(outlines), 2)
        self.assertEqual(outlines[0].attrib["text"], "Call 1")
        self.assertEqual(len(outlines[0].findall("outline")), 0) # No children

    def test_category_filtering(self):
        data = [
            {"structured": {"title": "Work call", "category": "work"}},
            {"structured": {"title": "Personal chat", "category": "personal"}},
            {"structured": {"title": "Tech talk", "category": "tech"}}
        ]
        filtered = filter_conversations(data, "work,tech")
        self.assertEqual(len(filtered), 2)
        titles = [c["structured"]["title"] for c in filtered]
        self.assertIn("Work call", titles)
        self.assertIn("Tech talk", titles)
        self.assertNotIn("Personal chat", titles)

    def test_envelope_extraction(self):
        bare_list = [{"id": "c1"}]
        wrapped_dict = {"conversations": [{"id": "c2"}]}
        empty_envelope = {"conversations": []}

        self.assertEqual(len(extract_conversations(bare_list)), 1)
        self.assertEqual(len(extract_conversations(wrapped_dict)), 1)
        self.assertEqual(len(extract_conversations(empty_envelope)), 0)

    def test_lone_surrogates_sanitization(self):
        bad_text = "Corrupted \ud800 audio text"
        clean = strip_surrogates(bad_text)
        self.assertEqual(clean, "Corrupted  audio text")

        data = [
            {
                "structured": {"title": bad_text, "overview": bad_text},
                "transcript_segments": [{"speaker": "A", "text": bad_text}]
            }
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertIn('text="Corrupted  audio text"', xml_str)

    def test_xml_escaping(self):
        data = [
            {
                "structured": {
                    "title": "Meeting & Discussion <Project X> \"2026\" 'v1' 🎙️",
                    "overview": "Reviewed specs & schemas"
                }
            }
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outline = root.find(".//body/outline")
        self.assertIsNotNone(outline)
        self.assertEqual(outline.attrib["text"], "Meeting & Discussion <Project X> \"2026\" 'v1' 🎙️")

    def test_missing_and_null_fields(self):
        data = [
            {"structured": None, "transcript_segments": None},
            {}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outlines = root.findall(".//body/outline")
        self.assertEqual(len(outlines), 2)
        for o in outlines:
            self.assertEqual(o.attrib["text"], "Untitled Conversation")

    def test_atomic_write(self):
        atomic_write(self.test_output, "<opml>test</opml>")
        self.assertTrue(os.path.exists(self.test_output))
        self.assertFalse(os.path.exists(self.partial_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "<opml>test</opml>")

    def test_cli_invocation(self):
        sample = [{
            "id": "c1",
            "structured": {
                "title": "CLI Integration Test",
                "overview": "CLI overview summary"
            }
        }]
        with open(self.test_input, "w", encoding="utf-8") as f:
            json.dump(sample, f)

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
            self.assertIn("CLI Integration Test", content)
            self.assertIn("CLI overview summary", content)


if __name__ == "__main__":
    unittest.main()
