"""Compile-only safety contracts; no SDK/hardware execution from unit tests."""
import json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import compile_only as compile
import checkout_contributor as entry
import test_checkout_contributor as fixtures
class CompileOnlyTests(unittest.TestCase):
 def test_untracked_configuration_and_keys_are_not_snapshotted(self):
  selected=compile.select_source_names(['omi/firmware/omi/omi.conf'],['omi/firmware/omi/prj.conf','omi/firmware/omi/key.pem','omi/firmware/omi/src/new.c']);self.assertEqual(selected,['omi/firmware/omi/omi.conf','omi/firmware/omi/src/new.c'])
 def test_snapshot_uses_active_source_and_records_exact_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);repo=root/'repo';source=repo/'omi/firmware/omi/src/active.c';source.parent.mkdir(parents=True);source.write_bytes(b'active edited bytes')
   records=compile.snapshot_active_source(repo,root/'out',['omi/firmware/omi/src/active.c']);self.assertEqual((root/'out/omi/firmware/omi/src/active.c').read_bytes(),b'active edited bytes');self.assertEqual(records[0]['sha256'],compile.hashlib.sha256(b'active edited bytes').hexdigest())
 def test_snapshot_refuses_source_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'omi/firmware/omi/src/link.c';source.parent.mkdir(parents=True);target=root/'outside.c';target.write_bytes(b'not read');source.symlink_to(target)
   with self.assertRaises(ValueError):compile.snapshot_active_source(root,root/'out',['omi/firmware/omi/src/link.c'])
 def test_snapshot_refuses_key_path_before_read(self):
  with patch.object(compile.os,'open',side_effect=AssertionError('key must not open')):
   with self.assertRaises(ValueError):compile.snapshot_active_source(Path('/synthetic'),Path('/out'),['omi/firmware/bootloader/mcuboot/key.pem'])
 def test_internal_private_named_C_is_source_not_a_key(self):
  self.assertTrue(compile.source_allowed('omi/firmware/omi/src/lib/core/lib/opus-1.2.1/resampler_private_AR2.c'));self.assertFalse(any('private*' in spec.lower() for spec in entry.EXCLUDES))
 def test_keys_images_and_path_escapes_excluded(self):
  for name in ['omi/firmware/omi/key.pem','omi/firmware/omi/key.key','omi/firmware/omi/id_rsa','omi/firmware/omi/update.hex','omi/firmware/omi/update.bin','omi/firmware/omi/zephyr.elf','omi/firmware/omi/ota.zip','../key.c','/absolute.c']:
   self.assertFalse(compile.source_allowed(name),name)
 def test_fixed_profile_is_keyless_and_skips_children(self):compile.validate_config(compile.PROFILE);self.assertIn('CONFIG_SIGN_IMAGES=n',compile.PROFILE);self.assertIn('CONFIG_NCS_INCLUDE_RPMSG_CHILD_IMAGE=n',compile.PROFILE)
 def test_signing_or_child_config_rejected(self):
  for line in ['CONFIG_SIGN_IMAGES=y','CONFIG_SECURE_BOOT=y','CONFIG_NCS_INCLUDE_RPMSG_CHILD_IMAGE=y','CONFIG_MCUBOOT_BUILD_STRATEGY_FROM_SOURCE=y','CONFIG_BUILD_OUTPUT_HEX=y']:
   with self.assertRaises(ValueError):compile.validate_config(compile.PROFILE+'\n'+line)
 def test_sign_or_provision_commands_rejected(self):
  for cmd in ['python keygen.py','python imgtool.py','west sign','python provision.py']:
   with self.assertRaises(ValueError):compile.validate_commands(cmd)
 def test_normal_application_object_command_allowed(self):compile.validate_commands('arm-zephyr-eabi-gcc -c src/audio_packet_logic.c -o app/a.obj')
 def fixture(self):
  f=fixtures.CheckoutTests();f.setUp();self.addCleanup(f.doCleanups);f.c.update(sdk_root='SDK',toolchain_root='TC');f.path.write_text(json.dumps(f.c));return f
 def test_unavailable_dependencies_prevent_build(self):
  f=self.fixture()
  with patch.object(entry,'kit_integrity',return_value={'state':'passed'}),patch.object(entry,'sdk_check',return_value={'state':'unavailable'}),patch.object(entry,'toolchain_check',return_value={'state':'unavailable'}),patch.object(compile,'build_application_objects') as build:
   r=entry.run('compile-only',f.path,f.kit,work_root=f.root);self.assertFalse(r['required_stages_passed']);build.assert_not_called()
 def test_pinned_ready_target_uses_only_fixed_compile_builder(self):
  f=self.fixture()
  with patch.object(entry,'kit_integrity',return_value={'state':'passed'}),patch.object(entry,'sdk_check',return_value={'state':'passed'}),patch.object(entry,'toolchain_check',return_value={'state':'passed'}),patch.object(compile,'build_application_objects',return_value={'state':'completed_compile_only','flashable':False,'releasable':False}) as build:
   r=entry.run('compile-only',f.path,f.kit,work_root=f.root);self.assertTrue(r['required_stages_passed']);build.assert_called_once_with(f.c,f.kit,f.root);self.assertFalse(r['hardware_access'])
if __name__=='__main__':unittest.main()
