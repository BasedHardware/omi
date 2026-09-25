#!/usr/bin/env python3
"""Unit tests for memories_to_joplin.py."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_joplin import MemoryConverter

class TestMemoryConverter(unittest.TestCase):
    def setUp(self):
        self.converter = MemoryConverter()
        self.sample_memory = {
            'id': 'test-id-123',
            'title': 'Test Memory',
            'content': '# Heading\n\nSome content',
            'createdAt': 1672531200000,
            'updatedAt': 1672617600000,
            'tags': ['test', 'sample']
        }

    def test_sanitize_filename(self):
        self.assertEqual(
            self.converter.sanitize_filename('Test/Title!@#'),
            'Test_Title___'
        )

    def test_memory_to_markdown(self):
        markdown = self.converter.memory_to_markdown(self.sample_memory)
        self.assertIn('Test Memory', markdown)
        self.assertIn('Omi Memories', markdown)
        self.assertIn('omi', markdown)
        self.assertIn('memory', markdown)
        self.assertIn('test', markdown)
        self.assertIn('sample', markdown)
        self.assertIn('2023-01-01', markdown)  # createdAt timestamp

    def test_memory_to_markdown_deduplication(self):
        # First call should generate output
        self.assertTrue(len(self.converter.memory_to_markdown(self.sample_memory)) > 0)
        # Second call with same ID should return empty string
        self.assertEqual(self.converter.memory_to_markdown(self.sample_memory), "")

    def test_create_jex_archive(self):
        with tempfile.NamedTemporaryFile(suffix='.jex', delete=False) as tmp:
            self.converter.create_jex_archive(tmp.name, [self.sample_memory])
            self.addCleanup(os.unlink, tmp.name)

            with tarfile.open(tmp.name, 'r:gz') as tar:
                self.assertEqual(len(tar.getmembers()), 2)  # JEX manifest + 1 note
                self.assertEqual(tar.getmember('Test_Memory.md').size, 100)  # Approx size

    def test_process_input_stdin(self):
        input_data = json.dumps([self.sample_memory])
        with patch('sys.stdin', io.StringIO(input_data)), \
             tempfile.TemporaryDirectory() as tmpdir:
            self.converter.process_input('-', tmpdir, force=True)
            self.assertTrue(Path(tmpdir).joinpath('Test_Memory.md').exists())

    def test_process_input_file(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            json.dump([self.sample_memory], tmp)
            tmp_path = tmp.name
            self.addCleanup(os.unlink, tmp_path)

            with tempfile.TemporaryDirectory() as tmpdir:
                self.converter.process_input(tmp_path, tmpdir, force=True)
                self.assertTrue(Path(tmpdir).joinpath('Test_Memory.md').exists())

    def test_process_input_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = Path(tmpdir) / 'input.json'
            json.dump([self.sample_memory], input_file.open('w'))

            output_dir = tmpdir + '_output'
            self.converter.process_input(tmpdir, output_dir, force=True)
            self.assertTrue(Path(output_dir).joinpath('Test_Memory.md').exists())


if __name__ == '__main__':
    unittest.main()