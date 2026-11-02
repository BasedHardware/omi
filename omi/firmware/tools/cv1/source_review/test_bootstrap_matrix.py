import unittest
import bootstrap_matrix as model

class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not model.LOADER.exists(): raise unittest.SkipTest('pinned NCS source not found; set OMI_NCS_ROOT')
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

    def test_cleanup_requires_complete_primary(self):
        for row in model.snapshots(model.MAX,(0,0,0,0)):
            if row[0]=='secondary_cleanup': self.assertTrue(row[3])

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
