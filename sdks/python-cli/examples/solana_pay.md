# Solana Pay Optical QR Scanner

Extracts, validates, and decodes Solana Pay payment QR codes and URI strings into structured JSON manifests from Omi optical logs or memory exports.

---

## Where Scan Logs Come From

When using Omi smart glasses (`omiGlass`) or AI necklaces equipped with camera or optical scanning plugins, QR codes in the wearer's field of view (e.g. coffee shop terminals, merchant POS displays, event invoices) are detected and logged as raw Solana Pay URIs in session capture logs.

---

## Prerequisites

- Python 3.8+
- Standard library only — no external packages (`requests`, `pydantic`, etc.) required.

---

## Usage

### Positional Syntax
```bash
python sdks/python-cli/examples/solana_pay_scanner.py /path/to/scan_log.txt payment_manifest.json
```

### Flag Syntax (`-o`)
```bash
python sdks/python-cli/examples/solana_pay_scanner.py /path/to/scan_log.txt -o payment_manifest.json
```

---

## Output Schema

The tool generates a validated JSON file structured as follows:

```json
{
  "source_file": "/path/to/scan_log.txt",
  "total_detected": 1,
  "total_volume_sol": 0.0,
  "total_volume_usdc": 4.5,
  "payments": [
    {
      "raw_uri": "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=4.5&spl-token=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&label=Coffee%20Shop&memo=Order%2312",
      "recipient": "FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8",
      "amount": 4.5,
      "token": "USDC",
      "spl_token_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
      "label": "Coffee Shop",
      "memo": "Order#12",
      "reference": null,
      "source_line": 3
    }
  ]
}
```

---

## Verification & Safety Guarantees

- **Stdlib Only**: Runs anywhere without virtual environments or dependency installations.
- **Base58 Check**: Verifies recipient addresses conform to Solana base58 character sets and valid 32–44 character bounds.
- **Atomic Replacement**: Writes to a temporary `.partial` file and atomically replaces the target with `os.replace()`, preventing half-written files.
- **Overwrite Guard**: Raises a clean `FileExistsError` if the destination file already exists.
