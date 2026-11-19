#!/usr/bin/env python3
"""Regression gate for the stock MCUboot accidentally shipped in CV1 3.0.21/.23/.24."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest
from unittest.mock import patch

import cv1_bootloader as boot
from prove_cv1_bootloader import validate_main_disassembly


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

    def test_app_hex_preserves_signed_bytes_and_rejects_storage_overlap(self):
        out = self.root / 'app.hex'
        image = b'\x3d\x00\xffsigned-app'
        boot.app_hex(image, out)
        self.assertEqual(boot.read_hex(out), dict(enumerate(image, boot.BOOT_END)))
        for invalid in (b'', bytes(0xf6000 - boot.BOOT_END + 1)):
            with self.assertRaisesRegex(ValueError, 'fit entirely'):
                boot.app_hex(invalid, out)

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
        overlay = boot.POLICY.parents[1] / 'omi/sysbuild/mcuboot-main/CMakeLists.txt'
        for count in (0, 1, 2):
            source = self.root / f'cmake-{count}' / 'boot/zephyr'
            source.mkdir(parents=True)
            (source / 'main.c').write_text('int main(void) { return 0; }')
            targets = ''.join(f'add_library(test{i} STATIC main.c)\n' for i in range(count))
            (source / 'CMakeLists.txt').write_text(
                'cmake_minimum_required(VERSION 3.20)\n'
                'project(overlay_test C)\n'
                f'set(APPLICATION_SOURCE_DIR "{source}")\n'
                f'set(ZEPHYR_MCUBOOT_MODULE_DIR "{source.parents[1]}")\n' + targets +
                f'include("{overlay}")\n')
            result = subprocess.run(['cmake', '-S', str(source), '-B', str(source / 'build')],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if count == 1:
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('Omi SD initialization main selected', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('requires exactly one MCUboot main.c replacement', result.stdout)

    def test_manual_recovery_and_manufacturing_roles_fail_closed(self):
        boot.app_hex(bytes.fromhex('3db8f396') + bytes(28), self.hex)
        self.assertEqual(boot.inspect_role(self.hex, 'app')['kind'], 'bootloader-free')
        with self.assertRaisesRegex(ValueError, 'must contain an approved bootloader'):
            boot.inspect_role(self.hex, 'manufacturing')
        for address in (0xf6000, 0xff8000, 0x1000000):
            memory = boot.read_hex(self.hex)
            memory[address] = 1
            boot.write_hex(self.hex, memory)
            with self.assertRaisesRegex(ValueError, 'outside'):
                boot.inspect_role(self.hex, 'app')

    def test_pending_manufacturing_candidate_is_not_approved(self):
        boot.write_hex(self.hex, self.memory)
        self.policy.write_text(json.dumps({'approved_boot_sha256': [],
                                         'manufacturing_candidate': {'boot_sha256': self.hash}}))
        with self.assertRaisesRegex(ValueError, 'unapproved'):
            boot.inspect_hex(self.hex, self.policy)

    def test_compiled_sd_order_arguments_and_gpio_precede_boot_go(self):
        assembly = """
  470: blx r3
  49a: blx r3
  49c: movs r1, #0
  49e: mov.w r0, #32768
  4a2: bl 7758 <z_impl_k_sleep>
  4a6: movs r1, #1
  4aa: bl 1c34 <pm_device_action_run>
  4b0: movs r1, #6
  4b4: bl 860a <disk_access_ioctl>
  4b8: movs r1, #0
  4ba: mov.w r0, #32768
  4be: bl 7758 <z_impl_k_sleep>
  4c4: movs r1, #7
  4c8: bl 860a <disk_access_ioctl>
  4cc: movs r1, #0
  4d0: bl 1c34 <pm_device_action_run>
  4da: bl 13f8 <boot_go>
"""
        validate_main_disassembly(assembly)
        for invalid in (
            assembly.replace('#32768', '#1'),
            assembly.replace('r1, #6', 'r1, #7'),
            assembly.replace('r1, #7', 'r1, #6'),
            assembly.replace('r1, #1', 'r1, #0'),
            assembly.replace('<z_impl_k_sleep>', '<unrelated>'),
            assembly.replace('blx r3', 'nop'),
            assembly.replace('<pm_device_action_run>', '<disk_access_ioctl>', 1),
            assembly.replace('<boot_go>', '<z_impl_k_sleep>', 1),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_main_disassembly(invalid)

    def test_build_pin_checks_initialized_reservation_and_exact_hash(self):
        self.policy.write_text(json.dumps({'approved_boot_sha256': [self.hash], 'build_boot_sha256': self.hash}))
        memory = {address: byte for address, byte in self.memory.items() if address < boot.BOOT_END}
        with patch.object(boot, 'POLICY', self.policy):
            self.assertEqual(boot.validate_build_bootloader(memory), boot.boot_bytes(memory))
            self.assertEqual(boot.validate_build_bootloader({**memory, 0xffff: 0xff}), boot.boot_bytes(memory))
            for invalid in ({}, {8: 0x11}, {**memory, 0x10000: 1}, {**memory, 0: 0x43}):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    boot.validate_build_bootloader(invalid)
            self.policy.write_text(json.dumps({'approved_boot_sha256': [], 'build_boot_sha256': self.hash}))
            with self.assertRaisesRegex(ValueError, 'also be approved'):
                boot.validate_build_bootloader(memory)

    def test_release_validation_requires_pin_and_exact_app_map(self):
        image = bytes.fromhex('3db8f396') + b'app'
        self.policy.write_text(json.dumps({'approved_boot_sha256': [self.hash], 'build_boot_sha256': self.hash}))
        with patch.object(boot, 'POLICY', self.policy):
            memory = boot.wire_memory(image, boot.boot_bytes(self.memory))
            boot.write_hex(self.hex, memory)
            self.assertEqual(boot.validate_release_hex(self.hex, image)['boot_sha256'], self.hash)
            for invalid in ({**memory, 0x10004: 42}, {**memory, 0xf6000: 1},
                            boot.app_memory(image)):
                boot.write_hex(self.hex, invalid)
                with self.subTest(invalid_size=len(invalid)), self.assertRaises(ValueError):
                    boot.validate_release_hex(self.hex, image)
            alternative = {**memory, 0: 43}
            other_hash = hashlib.sha256(boot.boot_bytes(alternative)).hexdigest()
            self.policy.write_text(json.dumps({'approved_boot_sha256': [self.hash, other_hash], 'build_boot_sha256': self.hash}))
            boot.write_hex(self.hex, alternative)
            with self.assertRaisesRegex(ValueError, 'pinned build'):
                boot.validate_release_hex(self.hex, image)

    def test_release_cli_requires_exact_signed_app_argument(self):
        result = subprocess.run(['python3', str(Path(boot.__file__)), '--require-bootloader', str(self.hex)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('must be used together', result.stderr)

    def test_committed_build_hash_is_jig_qualified_and_approved(self):
        policy = json.loads(boot.POLICY.read_text())
        expected = '6cfd4a70a715c8885dd86db96eb97286590852dd4b0f28d9f7374faad235cad1'
        self.assertEqual(policy['build_boot_sha256'], expected)
        self.assertIn(expected, policy['approved_boot_sha256'])
        self.assertEqual(policy['qualification']['boot_sha256'], expected)

    def test_committed_factory_hash_matches_reference(self):
        factory = boot.POLICY.parents[1] / 'FLASH_3.0.8/MAC/merged.hex'
        result = boot.inspect_hex(factory)
        self.assertTrue(result['boot_sha256'].startswith('c80cf2fd'))


if __name__ == '__main__':
    unittest.main()
