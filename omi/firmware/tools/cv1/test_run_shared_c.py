"""run_shared_c runner regressions using a synthetic compiler shim; no firmware build."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
class RunSharedCTests(unittest.TestCase):
 def shim(self,d):
  p=Path(d)/'cc-shim';p.write_text('#!/bin/sh\nfor last do :; done\nprintf "%s\\n" "$@"\ntouch "$last"\n');p.chmod(0o755);return str(p)
 def run_tool(self,cc,sanitizer='none'):
  q=subprocess.run([sys.executable,str(Path(__file__).parent/'run_shared_c.py'),'--cc',cc,'--sanitizer',sanitizer],capture_output=True,text=True,timeout=60)
  return q,json.loads(q.stdout) if q.stdout else None
 def test_sanitizer_build_disables_recover(self):
  with tempfile.TemporaryDirectory() as d:
   q,r=self.run_tool(self.shim(d),'undefined')
   self.assertEqual(r['results'][0]['stage'],'compile');self.assertIn('-fno-sanitize-recover=all',r['results'][0]['stdout'].split())
   self.assertNotEqual(q.returncode,0)
 def test_missing_compiler_reports_failed_stage_not_traceback(self):
  q,r=self.run_tool(str(Path('/nonexistent-cv1-compiler/cc')))
  self.assertNotEqual(q.returncode,0);self.assertNotIn('Traceback',q.stderr)
  self.assertEqual(r['results'][0]['stage'],'compile');self.assertEqual(r['results'][0]['state'],'os_error')
if __name__=='__main__':unittest.main()
