import unittest,json
from pathlib import Path
from radio_packet import decode
class TestRadioPacket(unittest.TestCase):
 def setUp(self):
  self.f=json.loads((Path(__file__).parent/'radio-fixture.json').read_text());self.b=bytes.fromhex(self.f['sanitized_ram_hex']);self.p=self.f['pcnf0']
 def test_real_fixture(self):self.assertEqual(decode(self.b,self.p),{'pdu_type':'ADV_IND','random_address':True,'payload_bytes':32,'name':'Omi','omi_service':True,'flags':6})
 def test_s1_ram_padding(self):self.assertEqual(decode(self.b[:2]+self.b[3:],self.p&~(1<<20)),decode(self.b,self.p))
 def test_truncation(self):
  for n in range(len(self.b)):
   with self.assertRaises(ValueError):decode(self.b[:n],self.p)
 def test_wrong_pdu(self):
  with self.assertRaises(ValueError):decode(bytes([0x64])+self.b[1:],self.p)
 def test_wrong_format(self):
  with self.assertRaises(ValueError):decode(self.b,self.p^1)
 def test_invalid_length(self):
  with self.assertRaises(ValueError):decode(self.b[:1]+bytes([38])+self.b[2:],self.p)
 def test_length_byte_read_in_full_not_masked_to_six_bits(self):
  with self.assertRaises(ValueError):decode(self.b[:1]+bytes([0x60])+self.b[2:],self.p)
 def test_corrupt_ad_length(self):
  b=bytearray(self.b);b[9]=255
  with self.assertRaises(ValueError):decode(b,self.p)
 def test_wrong_uuid_is_not_match(self):
  b=bytearray(self.b);b[14]^=1;self.assertFalse(decode(b,self.p)['omi_service'])
 def test_trailing_ram_is_not_payload(self):self.assertEqual(decode(self.b+bytes([255])*100,self.p),decode(self.b,self.p))
if __name__=='__main__':unittest.main()
