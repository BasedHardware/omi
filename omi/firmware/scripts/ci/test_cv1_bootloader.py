#!/usr/bin/env python3
"""Regression gate for the stock MCUboot accidentally shipped in CV1 3.0.21/.23/.24."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest

import cv1_bootloader as boot


class BootRegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hex = self.root / 'image.hex'
        self.policy = self.root / 'policy.json'
        self.memory = {0: 0x42, 8: 0x11, 0x10000: 0x3d}
        self.hash = hashlib.sha256(boot.boot_bytes(self.memory)).hexdigest()
        self.policy.write_text(json.dumps({'approved_boot_sha256': [self.hash]}))

    def test_padded_region_and_boundary(self):
        boot.write_hex(self.hex, self.memory)
        self.assertEqual(boot.inspect_hex(self.hex, self.policy)['boot_sha256'], self.hash)
        self.memory[0xffff] = 0  # a single byte at the boundary must fail
        boot.write_hex(self.hex, self.memory)
        with self.assertRaisesRegex(ValueError, 'unapproved'):
            boot.inspect_hex(self.hex, self.policy)

    def test_app_and_network_without_boot_are_accepted(self):
        for address in (0x10000, 0x1000000):
            boot.write_hex(self.hex, {address: 7})
            self.assertEqual(boot.inspect_hex(self.hex, self.policy)['kind'], 'bootloader-free')

    def test_stock_or_partial_boot_fails_even_with_valid_hex(self):
        for memory in ({0: 7}, {0xfffe: 7}, {0: 0xff}):
            boot.write_hex(self.hex, memory)
            with self.assertRaisesRegex(ValueError, 'unapproved'):
                boot.inspect_hex(self.hex, self.policy)

    def test_strips_only_app_and_excludes_boot_uicr_and_settings(self):
        memory = {0: 1, 0x10000: 2, 0x10200: 3, 0xf5fff: 4, 0xf6000: 5, 0xff8000: 6, 0x1000000: 7}
        boot.write_hex(self.hex, memory)
        out = self.root / 'app.hex'
        boot.app_only(self.hex, out)
        self.assertEqual(boot.read_hex(out), {a: memory[a] for a in (0x10000, 0x10200, 0xf5fff)})

    def test_parser_refuses_ambiguous_or_malformed_files(self):
        valid = boot.record(0, 0, b'\x42')
        eof = boot.record(0, 1, b'')
        for text in ('', valid, valid[:-2] + '00\n' + eof, valid + '\n' + valid + '\n' + eof,
                     eof + '\n' + valid, ':broken\n' + eof,
                     boot.record(0, 4, b'\x01') + '\n' + valid + '\n' + eof,
                     boot.record(0xffff, 0, b'\x01\x02') + '\n' + eof):
            self.hex.write_text(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                boot.inspect_hex(self.hex, self.policy)

    def test_segment_addressing_cannot_hide_boot_bytes(self):
        self.hex.write_text('\n'.join((boot.record(0, 2, b'\x00\x01'), boot.record(0, 0, b'\x42'), boot.record(0, 1, b''))) + '\n')
        with self.assertRaisesRegex(ValueError, 'unapproved'):
            boot.inspect_hex(self.hex, self.policy)

    @unittest.skipUnless(shutil.which('cmake'), 'CMake required for source-overlay configure test')
    def test_overlay_replaces_exactly_one_main_and_fails_on_drift(self):
        overlay = boot.POLICY.parents[1] / 'omi/sysbuild/mcuboot-main.cmake'
        for count in (0, 1, 2):
            source = self.root / f'cmake-{count}'
            source.mkdir()
            (source / 'main.c').write_text('int main(void) { return 0; }')
            targets = ''.join(f'add_library(test{i} STATIC main.c)\n' for i in range(count))
            (source / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                f'set(CMAKE_PROJECT_INCLUDE "{overlay}")\n'
                'project(overlay_test C)\n' + targets)
            result = subprocess.run(['cmake', '-S', str(source), '-B', str(source / 'build')],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if count == 1:
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('Omi SD initialization main selected', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('requires exactly one MCUboot main.c replacement', result.stdout)

    def test_committed_factory_hash_matches_reference(self):
        factory = boot.POLICY.parents[1] / 'FLASH_3.0.8/MAC/merged.hex'
        result = boot.inspect_hex(factory)
        self.assertTrue(result['boot_sha256'].startswith('c80cf2fd'))


if __name__ == '__main__':
    unittest.main()
