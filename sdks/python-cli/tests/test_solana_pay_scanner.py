import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Load solana_pay_scanner dynamically using importlib.util
script_path = Path(__file__).resolve().parent.parent / "examples" / "solana_pay_scanner.py"
spec = importlib.util.spec_from_file_location("solana_pay_scanner", script_path)
sps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sps)


class TestSolanaPayScanner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.scan_file = Path(self.test_dir) / "ocr_log.txt"

        sample_lines = [
            "# Optical scan session 2026-09-24",
            "Customer presented terminal at 14:02:",
            "QR content: solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=4.50&label=Coffee%20Roasters&memo=Order%23101",
            "Ignored non-solana barcode: https://example.com/receipt/123",
            "Second QR: solana:EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v?amount=10.0&spl-token=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&label=Bookstore",
        ]
        self.scan_file.write_text("\n".join(sample_lines), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_convert_generates_valid_manifest(self):
        dest = Path(self.test_dir) / "payments.json"
        sps.convert(str(self.scan_file), str(dest))

        self.assertTrue(dest.exists())
        data = json.loads(dest.read_text(encoding="utf-8"))

        self.assertEqual(data["total_detected"], 2)
        self.assertEqual(data["total_volume_sol"], 4.50)
        self.assertEqual(data["total_volume_usdc"], 10.0)

        p1 = data["payments"][0]
        self.assertEqual(p1["recipient"], "FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8")
        self.assertEqual(p1["amount"], 4.50)
        self.assertEqual(p1["token"], "SOL")
        self.assertEqual(p1["label"], "Coffee Roasters")
        self.assertEqual(p1["memo"], "Order#101")
        self.assertEqual(p1["source_line"], 3)

        p2 = data["payments"][1]
        self.assertEqual(p2["token"], "USDC")
        self.assertEqual(p2["label"], "Bookstore")
        self.assertEqual(p2["amount"], 10.0)

    def test_destination_already_exists_raises(self):
        dest = Path(self.test_dir) / "existing.json"
        dest.write_text("{}", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            sps.convert(str(self.scan_file), str(dest))

    def test_missing_source_file_raises(self):
        dest = Path(self.test_dir) / "out.json"
        with self.assertRaises(ValueError):
            sps.convert(str(Path(self.test_dir) / "nonexistent.txt"), str(dest))

    def test_destination_is_directory_raises(self):
        with self.assertRaises(ValueError):
            sps.convert(str(self.scan_file), str(self.test_dir))

    def test_base58_validation(self):
        self.assertTrue(sps.is_valid_base58("FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8"))
        self.assertFalse(sps.is_valid_base58("invalid!0OIl"))
        self.assertFalse(sps.is_valid_base58(""))


if __name__ == "__main__":
    unittest.main()
