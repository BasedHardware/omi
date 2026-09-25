import unittest
import json
import os
import subprocess
from action_items_to_opml import create_opml, get_opml_string, safe_get, atomic_write

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

    def test_basic_conversion(self):
        data = [
            {"description": "Task 1", "completed": False, "created_at": "2024-01-01"},
            {"description": "Task 2", "completed": True, "category": "Work"}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        self.assertIn('<outline text="Task 1" _status="open" created="2024-01-01" />', xml_str)
        self.assertIn('<outline text="Task 2" _status="completed" category="Work" />', xml_str)

    def test_xml_escaping(self):
        data = [
            {"description": "Task & < > \" ' 😊", "completed": False}
        ]
        opml = create_opml(data)
        xml_str = get_opml_string(opml)
        import xml.etree.ElementTree as ET
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
        import xml.etree.ElementTree as ET
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
        # Create input json
        with open("test_input.json", "w", encoding="utf-8") as f:
            json.dump([{"description": "CLI Task"}], f)
        
        # Run CLI
        subprocess.run(["python", "action_items_to_opml.py", "test_input.json", self.test_output], check=True)
        
        self.assertTrue(os.path.exists(self.test_output))
        with open(self.test_output, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("CLI Task", content)
            
        os.remove("test_input.json")

if __name__ == '__main__':
    unittest.main()