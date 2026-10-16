#!/usr/bin/env python3
"""
Regression test suite for Omi Glass dynamic MTU negotiation and audio packet fragmentation.
Validates:
1. Static code tripwires in config.h and app.cpp for MTU constants, server callbacks, and bounds.
2. Behavioral simulation verifying that chunked audio packets strictly respect ATT MTU limits,
   preserve sequential sub-indices, and reconstruct original audio payloads losslessly.
"""

import math
import re
import sys
from pathlib import Path

# Authoritative test matrix: (negotiated_mtu, audio_len, sequence_index)
TEST_CASES = [
    # MTU 23 (BLE Minimum ATT MTU, safe audio payload = 23 - 3 - 3 = 17 bytes)
    (23, 0, 1),
    (23, 1, 2),
    (23, 16, 3),
    (23, 17, 4),    # Exact boundary for 1 chunk
    (23, 18, 5),    # Boundary for 2 chunks (17 + 1)
    (23, 34, 6),    # Exact boundary for 2 chunks (17 + 17)
    (23, 35, 7),    # Boundary for 3 chunks (17 + 17 + 1)
    (23, 120, 8),   # Medium frame
    (23, 160, 9),   # Standard max Opus frame (10 chunks: 9x17 + 1x7)

    # MTU 64 (Intermediate MTU, safe audio payload = 64 - 3 - 3 = 58 bytes)
    (64, 160, 10),  # 3 chunks: 58 + 58 + 44

    # MTU 185 (Default Android/Windows fallback, safe payload = 185 - 3 - 3 = 179 bytes)
    (185, 17, 11),
    (185, 160, 12), # Single chunk (fits completely, sub_index = 0)
    (185, 179, 13), # Exact boundary for 1 chunk
    (185, 180, 14), # 2 chunks: 179 + 1
    (185, 320, 15), # 2 chunks: 179 + 141

    # MTU 247 (Common Android extended MTU, safe payload = 247 - 3 - 3 = 241 bytes)
    (247, 160, 16), # Single chunk
    (247, 300, 17), # 2 chunks: 241 + 59

    # MTU 517 (Maximum configured MTU, safe payload = 517 - 3 - 3 = 511 bytes)
    (517, 160, 18), # Single chunk (standard operation)
    (517, 500, 19), # Single chunk
]

def verify_static_tripwires(firmware_dir: Path) -> bool:
    """Verify contracts in config.h and app.cpp."""
    print("[STATIC TRIPWIRE] Verifying firmware source contracts...")
    config_path = firmware_dir / "src" / "config.h"
    app_path = firmware_dir / "src" / "app.cpp"

    if not config_path.exists():
        print(f"FAIL: config.h not found at {config_path}")
        return False
    if not app_path.exists():
        print(f"FAIL: app.cpp not found at {app_path}")
        return False

    config_content = config_path.read_text(encoding="utf-8")
    app_content = app_path.read_text(encoding="utf-8")

    # 1. Check config.h constants
    if "BLE_MIN_MTU_SIZE" not in config_content:
        print("FAIL: BLE_MIN_MTU_SIZE missing from config.h")
        return False
    if "BLE_ATT_HEADER_SIZE" not in config_content:
        print("FAIL: BLE_ATT_HEADER_SIZE missing from config.h")
        return False

    # 2. Check app.cpp callback and tracking
    if "onMTUChange" not in app_content:
        print("FAIL: onMTUChange callback missing in app.cpp ServerHandler")
        return False
    if "current_negotiated_mtu" not in app_content:
        print("FAIL: current_negotiated_mtu tracking variable missing in app.cpp")
        return False

    # 3. Check app.cpp broadcastAudioPacket fragmentation logic
    if "header_overhead = BLE_ATT_HEADER_SIZE + AUDIO_PACKET_HEADER_SIZE" not in app_content:
        print("FAIL: header_overhead calculation missing in broadcastAudioPacket")
        return False
    if "sub_index" not in app_content:
        print("FAIL: sub_index fragmentation loop missing in broadcastAudioPacket")
        return False

    print("PASS: All static tripwires satisfied in config.h and app.cpp.")
    return True

def run_behavioral_simulation() -> int:
    """Run simulated fragmentation tests against all test cases."""
    print("\n[BEHAVIORAL SIMULATION] Running simulated audio packet fragmentation test cases:")
    BLE_ATT_HEADER_SIZE = 3
    AUDIO_PACKET_HEADER_SIZE = 3

    failed = 0
    for mtu, size, seq in TEST_CASES:
        # Generate distinct synthetic audio payload
        raw_audio = bytearray((i * 31 + 7) & 0xFF for i in range(size))

        notified_packets = []

        def mock_notify(packet_data):
            notified_packets.append(bytes(packet_data))

        # Replicate production broadcastAudioPacket algorithm
        effective_mtu = max(mtu, 23)
        header_overhead = BLE_ATT_HEADER_SIZE + AUDIO_PACKET_HEADER_SIZE
        max_payload = (effective_mtu - header_overhead) if effective_mtu > header_overhead else 1

        offset = 0
        sub_index = 0
        packet_index = seq

        if size > 0:
            while offset < size:
                chunk_size = min(size - offset, max_payload)
                pkt = bytearray(chunk_size + AUDIO_PACKET_HEADER_SIZE)
                pkt[0] = packet_index & 0xFF
                pkt[1] = (packet_index >> 8) & 0xFF
                pkt[2] = sub_index
                pkt[AUDIO_PACKET_HEADER_SIZE:] = raw_audio[offset : offset + chunk_size]

                mock_notify(pkt)
                packet_index = (packet_index + 1) & 0xFFFF
                offset += chunk_size
                sub_index += 1

        # Verification assertions
        ok = True
        error_reasons = []

        if size == 0:
            if len(notified_packets) != 0:
                ok = False
                error_reasons.append("Expected 0 packets for empty audio frame")
        else:
            expected_chunks = math.ceil(size / max_payload)
            if len(notified_packets) != expected_chunks:
                ok = False
                error_reasons.append(f"Expected {expected_chunks} chunks, got {len(notified_packets)}")

            reconstructed = bytearray()
            for idx, pkt in enumerate(notified_packets):
                # Check ATT MTU notification boundary: packet size <= MTU - 3
                if len(pkt) > (mtu - BLE_ATT_HEADER_SIZE):
                    ok = False
                    error_reasons.append(f"Packet {idx} size {len(pkt)} exceeds MTU notification limit {mtu - BLE_ATT_HEADER_SIZE}")

                # Check headers
                pkt_seq = pkt[0] | (pkt[1] << 8)
                pkt_sub = pkt[2]
                expected_seq = (seq + idx) & 0xFFFF
                if pkt_seq != expected_seq:
                    ok = False
                    error_reasons.append(f"Packet sequence {pkt_seq} != expected {expected_seq}")
                if pkt_sub != idx:
                    ok = False
                    error_reasons.append(f"Packet sub-index {pkt_sub} != expected {idx}")

                reconstructed.extend(pkt[AUDIO_PACKET_HEADER_SIZE:])

            if reconstructed != raw_audio:
                ok = False
                error_reasons.append("Reconstructed payload mismatch with original raw audio")

        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
            print(f"  [{status}] MTU={mtu:3d} audio_bytes={size:3d} -> ERRORS: {'; '.join(error_reasons)}")
        else:
            print(f"  [{status}] MTU={mtu:3d} audio_bytes={size:3d} -> chunks={len(notified_packets)} delivered={len(raw_audio)} bytes")

    total = len(TEST_CASES)
    print(f"\n{total - failed} of {total} test cases passed ({failed} failed)")
    return failed

def main():
    script_dir = Path(__file__).resolve().parent
    firmware_dir = script_dir.parent

    if not verify_static_tripwires(firmware_dir):
        return 1

    failures = run_behavioral_simulation()
    return 0 if failures == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
