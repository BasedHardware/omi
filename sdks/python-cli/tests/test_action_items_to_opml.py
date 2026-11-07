import unittest
import json
import os
import sys
import subprocess
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

# Dynamically load the action_items_to_opml module
recipe_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_opml.py"
spec = importlib.util.spec_from_file_location("action_items_to_opml", recipe_path)
action_items_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(action_items_module)

create_opml = action_items_module.create_opml
get_opml_string = action_items_module.get_opml_string
safe_get = action_items_module.safe_get
atomic_write = action_items_module.atomic_write

class TestActionItemsToOpml(unittest.TestCase):
    def setUp(self):
        self.test_output = "test_output.opml"
        self.partial_output = "test_output.opml.partial"
        if os.path.exists(self.test_output):
            os.remove(self.test_output)
        if os.path.exists(self.partial_output):
            os.remove(self.partial_output)

    def tearDown(self):
        if os.path.exists(self.test_output):
            os.remove(self.test_output)
        if os.path.exists(self.partial_output):
            os.remove(self.partial_output)

    def test_due_at_produces_due(self):
        data = [
            {"description": "Task Due", "completed": False, "due_at": "2024-12-31T23:59:59Z"}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertIn('due="2024-12-31T23:59:59Z"', xml_str)
        self.assertIn('<outline text="Task Due" _status="open" due="2024-12-31T23:59:59Z" />', xml_str)

    def test_category_not_produced(self):
        data = [
            {"description": "Task 2", "completed": True, "category": "Work"}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertNotIn("category", xml_str)
        self.assertIn('<outline text="Task 2" _status="completed" />', xml_str)

    def test_xml_escaping(self):
        data = [
            {"description": "Task & < > \" ' 😊", "completed": False}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode('utf-8'))
        outline = root.find('.//outline')
        self.assertIsNotNone(outline)
        self.assertEqual(outline.attrib['text'], "Task & < > \" ' 😊")

    def test_missing_and_null_fields(self):
        data = [
            {"description": None, "completed": None, "created_at": None, "category": None},
            {}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertIn('<outline text="Untitled Action Item" _status="open" />', xml_str)

    def test_empty_input(self):
        opml = create_opml([])
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode('utf-8'))
        outlines = root.findall('.//outline')
        self.assertEqual(len(outlines), 0)
        self.assertEqual(root.tag, "opml")

    def test_atomic_write(self):
        atomic_write(self.test_output, "test content")
        self.assertTrue(os.path.exists(self.test_output))
        self.assertFalse(os.path.exists(self.partial_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "test content")

    def test_cli_invocation(self):
        with open("test_input.json", "w", encoding="utf-8") as f:
            json.dump([{"description": "CLI Task"}], f)
        
        subprocess.run([sys.executable, str(recipe_path), "test_input.json", self.test_output], check=True)
        
        self.assertTrue(os.path.exists(self.test_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("CLI Task", content)
            
        os.remove("test_input.json")

    def test_strip_surrogates_in_description_and_fields(self):
        data = [
            {"description": "Task with lone surrogate \ud800 here", "completed": False, "created_at": "2024-01-01T00:00:00Z\ud800"}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertNotIn("\ud800", xml_str)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outline = root.find(".//outline")
        self.assertIsNotNone(outline)
        self.assertEqual(outline.attrib["text"], "Task with lone surrogate  here")

    def test_strip_control_characters(self):
        data = [
            {"description": "Task with control \x00\x08\x1b\x0c chars", "completed": False}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outline = root.find(".//outline")
        self.assertIsNotNone(outline)
        self.assertNotIn("\x00", outline.attrib["text"])
        self.assertNotIn("\x08", outline.attrib["text"])

    def test_envelope_unwrapping_action_items_and_data(self):
        envelope_action_items = {"action_items": [{"description": "Action item envelope task", "completed": True}]}
        envelope_data = {"data": [{"description": "Data envelope task", "completed": False}]}
        
        # Test CLI invocation handles envelope formats
        with open("test_env_ai.json", "w", encoding="utf-8") as f:
            json.dump(envelope_action_items, f)
        subprocess.run([sys.executable, str(recipe_path), "test_env_ai.json", self.test_output], check=True)
        with open(self.test_output, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Action item envelope task", content)
            self.assertIn('_status="completed"', content)
        os.remove("test_env_ai.json")

        with open("test_env_data.json", "w", encoding="utf-8") as f:
            json.dump(envelope_data, f)
        subprocess.run([sys.executable, str(recipe_path), "test_env_data.json", self.test_output], check=True)
        with open(self.test_output, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Data envelope task", content)
            self.assertIn('_status="open"', content)
        os.remove("test_env_data.json")

    def test_loosely_typed_completed_and_description(self):
        data = [
            {"description": {"title": "Structured object task"}, "completed": 1},
            {"description": ["List task"], "completed": "done"},
            {"description": "Falsy task", "completed": "0"},
            {"description": "False string task", "completed": "false"}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        root = ET.fromstring(xml_str.encode("utf-8"))
        outlines = root.findall(".//outline")
        self.assertEqual(len(outlines), 4)
        self.assertEqual(outlines[0].attrib["_status"], "completed")
        self.assertIn("Structured object task", outlines[0].attrib["text"])
        self.assertEqual(outlines[1].attrib["_status"], "completed")
        self.assertEqual(outlines[2].attrib["_status"], "open")
        self.assertEqual(outlines[3].attrib["_status"], "open")

if __name__ == '__main__':
    unittest.main()

