import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote

BASE58_ALPHABET = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

BANNER = r"""
   ___                     ________               
  / _ \ _ __ ___  (_)     / ____/ /___ ___________
 / // // '  \ _ \/ / --- / / __/ / __ `/ ___/ ___/
/____//_/_/_//_/_/      \____/_/\__,_/____/____/  
   Omi AI Wearables — Solana Pay Scanner v1.0.0
"""


def is_valid_base58(addr: str) -> bool:
    if not isinstance(addr, str):
        return False
    clean = addr.strip()
    return 32 <= len(clean) <= 44 and set(clean).issubset(BASE58_ALPHABET)


def parse_solana_pay_uri(uri_str: str):
    clean = uri_str.strip()
    if not clean.startswith("solana:"):
        return None

    remainder = clean[len("solana:"):]
    if "?" in remainder:
        recipient, query = remainder.split("?", 1)
    else:
        recipient, query = remainder, ""

    recipient = unquote(recipient).strip()
    if not is_valid_base58(recipient):
        return None

    params = parse_qs(query)
    amount_val = params.get("amount", [None])[0]
    raw_label = unquote(params.get("label", ["Merchant"])[0])
    raw_memo = unquote(params.get("memo", [""])[0]) if params.get("memo") else None
    reference = params.get("reference", [None])[0]
    spl_token = params.get("spl-token", [None])[0]

    label = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_label)[:64].strip() or "Merchant"
    memo = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_memo)[:128].strip() if raw_memo else None

    if reference and not is_valid_base58(reference):
        return None
    if spl_token and not is_valid_base58(spl_token):
        return None

    amount = None
    if amount_val is not None:
        try:
            amount = float(amount_val)
            if amount < 0 or math.isnan(amount) or math.isinf(amount):
                return None
        except ValueError:
            return None

    token = "SOL"
    if spl_token:
        if spl_token == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
            token = "USDC"
        else:
            token = f"SPL-{spl_token[:4]}..{spl_token[-4:]}"

    return {
        "raw_uri": clean,
        "recipient": recipient,
        "amount": amount,
        "token": token,
        "spl_token_mint": spl_token,
        "label": label,
        "memo": memo,
        "reference": reference,
    }


def convert(source_file, destination):
    src = Path(source_file)
    if not src.is_file():
        raise ValueError(f"Source must be a readable text file: {src}")

    dest = Path(destination)
    if dest.is_dir():
        raise ValueError(f"Destination must be a file, not a directory: {dest}")
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")

    tmp = dest.with_suffix(dest.suffix + ".partial")
    try:
        content = src.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        parsed_payments = []
        for line_num, line in enumerate(lines, 1):
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("#"):
                continue

            matches = re.findall(r"solana:[^\s'\"<>]+", line_clean)
            for m in matches:
                item = parse_solana_pay_uri(m)
                if item:
                    item["source_line"] = line_num
                    parsed_payments.append(item)

        output = {
            "source_file": str(src.resolve()),
            "total_detected": len(parsed_payments),
            "total_volume_sol": sum(p["amount"] for p in parsed_payments if p["amount"] and p["token"] == "SOL"),
            "total_volume_usdc": sum(p["amount"] for p in parsed_payments if p["amount"] and p["token"] == "USDC"),
            "payments": parsed_payments,
        }

        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def run_demo():
    print(BANNER)
    print("▶ Running simulated optical QR code capture from Omi smart glasses...\n")
    sample_qr = "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=4.50&spl-token=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&label=Coffee%20Roasters&memo=Order%2312"
    print(f"Captured QR URI: {sample_qr}")
    decoded = parse_solana_pay_uri(sample_qr)
    print("\nDecoded Transaction Parameters:")
    print(f"  • Recipient:  {decoded['recipient']}")
    print(f"  • Amount:     {decoded['amount']} {decoded['token']}")
    print(f"  • Merchant:   {decoded['label']}")
    print(f"  • Memo:       {decoded['memo']}")
    print("\n🔊 Omi Wearable Audio Prompt:")
    print(f"  \"Found payment to {decoded['label']} for {decoded['amount']} {decoded['token']}. Say 'Confirm' to approve.\"")
    print("\n✅ Verification successful. Ready for live scanning.")


def main():
    parser = argparse.ArgumentParser(
        description="Extract and structure Solana Pay QR codes and payment URIs from Omi optical logs."
    )
    parser.add_argument("source", nargs="?", default=None, help="Path to input text or scan log file containing Solana Pay URIs.")
    parser.add_argument("destination", nargs="?", default=None, help="Destination JSON manifest path.")
    parser.add_argument("-o", "--output", dest="output_opt", default=None, help="Destination JSON manifest path (flag form).")
    parser.add_argument("--demo", action="store_true", help="Run simulated optical QR scanner demo.")

    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if not args.source:
        parser.print_help()
        sys.exit(1)

    dest = args.output_opt or args.destination
    if not dest:
        parser.error("A destination path must be provided as either a second argument or via -o/--output.")

    try:
        convert(args.source, dest)
        print(f"✅ Successfully converted '{args.source}' -> '{dest}'")
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
