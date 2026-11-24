import unittest
import bootstrap_matrix as model

class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (model.LOADER.exists() and model.PUBLIC.exists()): raise unittest.SkipTest('pinned NCS loader/trailer source not found; set OMI_NCS_ROOT')
        cls.report = model.run()

    def test_conventional_and_equal_versions_lose_retry_image(self):
        for name in ('conventional','equal_conventional'):
            failures=self.report['cases'][name]['failures']
            self.assertTrue(any(x['phase']=='header_word_20' and x['outcome']=='no_boot_source_erased' for x in failures))

    def test_maximum_survives_bounded_interruption_classes_only(self):
        for name in ('maximum_bootstrap','maximum_future_equal'):
            self.assertEqual(self.report['cases'][name]['failures'],[])
            self.assertGreater(self.report['cases'][name]['states'],90)

    def test_lower_candidate_does_not_enter_copy(self):
        case=self.report['cases']['maximum_to_lower_rejected_before_copy']
        self.assertFalse(case['copy_reachable'])
        self.assertEqual(case['initial'],'primary_source_erased')

    def test_torn_request_never_modifies_old_primary(self):
        for phase, version, erased, pv, sv, sm, so in model.snapshots((1,0,0,0),(0,0,0,0)):
            if phase.startswith('request_'): self.assertTrue(pv)

    def test_cleanup_with_torn_primary_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            compare,_=model.comparator_library(directory)
            self.assertEqual(model.reboot(compare,model.MAX,model.MAX,primary_valid=False,secondary_valid=False,secondary_magic='good',secondary_ok='unset'),'no_boot_source_erased')
            self.assertEqual(model.reboot(compare,model.MAX,model.MAX,primary_valid=True,secondary_valid=False,secondary_magic='good',secondary_ok='unset'),'primary_source_erased')

    def test_retained_matrix_result_matches_regenerated_output(self):
        import json
        from pathlib import Path
        retained=json.loads((Path(__file__).parent/'matrix-result.json').read_text())
        self.assertEqual(json.loads(json.dumps(model.run())),retained)

    def test_equal_version_build_is_ignored_by_actual_c(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            compare,_=model.comparator_library(directory)
            self.assertEqual(compare((255,255,65535,0),(255,255,65535,4294967295)),0)
            self.assertEqual(compare((1,0,0,0),(1,0,1,0)),-1)

    def test_secondary_eligibility_precedes_downgrade_but_auth_does_not(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            compare,_=model.comparator_library(directory)
            args=dict(primary_valid=True,secondary_valid=False)
            self.assertEqual(model.reboot(compare,(1,0,0,0),model.MAX,secondary_eligible=False,**args),'primary')
            self.assertEqual(model.reboot(compare,(1,0,0,0),model.MAX,**args),'primary_source_erased')

    def test_bad_secondary_flag_cannot_start_update(self):
        self.assertFalse(model.pending('good','bad'))
        self.assertFalse(model.pending('bad','unset'))
        self.assertTrue(model.pending('good','unset'))

    def test_never_claims_whole_loader_or_crypto_execution(self):
        self.assertIn('NOT whole loader execution',self.report['kind'])
        self.assertIn('No cryptographic',self.report['limits'][1])


class ComparatorBuildTests(unittest.TestCase):
    def test_comparator_build_honors_cc_and_platform(self):
        import sys,tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            loader=Path(directory)/'loader.c'
            loader.write_text('int\nboot_version_cmp(const struct image_version *ver1,\n                   const struct image_version *ver2)\n{\n return 0;\n}\n')
            calls=[]
            with patch.dict('os.environ',{'CC':'/synthetic/cc'}),patch.object(model,'LOADER',loader),\
                 patch.object(model,'sha',return_value='c7fd7916441262e0f5acba84c9d5b400dc38d812a8afeb9ad78956a0473b7fc9'),\
                 patch.object(model.subprocess,'run',side_effect=lambda cmd,check:calls.append(cmd)),\
                 patch.object(model.ctypes,'CDLL'):
                model.comparator_library(directory)
            self.assertEqual(calls[0][0],'/synthetic/cc')
            self.assertIn('-dynamiclib' if sys.platform=='darwin' else '-shared',calls[0])


class SkipGuardTests(unittest.TestCase):
    def test_missing_public_source_skips_rather_than_errors(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            loader=Path(directory)/'loader.c';loader.write_text('x')
            with patch.object(model,'LOADER',loader),patch.object(model,'PUBLIC',Path(directory)/'missing.c'):
                self.assertRaises(unittest.SkipTest,BootstrapTests.setUpClass)


class BankContractTests(unittest.TestCase):
    def test_external_banks_are_contiguous_and_layout_aligned(self):
        import json
        from pathlib import Path
        contract=json.loads((Path(__file__).parent/'bank-contract.json').read_text())
        for regions in contract['options'].values():
            cursor=0
            for name, low, high in regions:
                self.assertEqual(low,cursor)
                self.assertEqual(low % 65536,0)
                self.assertEqual(high % 65536,0)
                self.assertGreater(high,low)
                cursor=high
            self.assertEqual(cursor,2097152)
        self.assertFalse(contract['hardware_authority'])
        self.assertFalse(contract['firmware_link_proof'])

    def test_secure_flash_boundaries_meet_spu_granularity(self):
        import json
        from pathlib import Path
        contract=json.loads((Path(__file__).parent/'bank-contract.json').read_text())
        for name,low,high in contract['internal_A'][:5]:
            self.assertEqual(low % 16384,0)
            self.assertEqual(high % 16384,0)
        start,end=contract['recovery_secure_ram']
        self.assertEqual((end-start)//1024,440)

if __name__=='__main__': unittest.main()
