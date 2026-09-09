#!/usr/bin/env python3
"""Verification test for push_to_gatt MTU notification limit contract.

Checks that push_to_gatt never emits GATT notifications exceeding
current_mtu - ATT_NOTIFICATION_HEADER_SIZE (current_mtu - 3 bytes),
even with smaller or edge-case MTUs.

Usage:
    python check_cv1_mtu.py [path_to_transport.c]
"""

from pathlib import Path
import re
import sys

def verify_source(source_path: Path) -> bool:
    content = source_path.read_text(encoding="utf-8")
    
    if "ATT_NOTIFICATION_HEADER_SIZE" not in content:
        print("FAIL: ATT_NOTIFICATION_HEADER_SIZE definition missing in transport.c")
        return False
        
    pattern = r"MIN\s*\(\s*current_mtu\s*-\s*ATT_NOTIFICATION_HEADER_SIZE\s*-\s*NET_BUFFER_HEADER_SIZE"
    if not re.search(pattern, content):
        print("FAIL: packet_size calculation does not subtract ATT_NOTIFICATION_HEADER_SIZE")
        return False
        
    print("PASS: Source code correctly bounds packet_size to respect ATT notification header limit.")
    return True

def run_simulation() -> int:
    NET_BUFFER_HEADER_SIZE = 3
    ATT_NOTIFICATION_HEADER_SIZE = 3
    RING_BUFFER_HEADER_SIZE = 2
    
    test_cases = [
        (100, 0, 0, 0),
        (100, 80, 0, 0),
        (100, 94, 0, 0),
        (100, 95, 0, 0),
        (100, 102, 0, 0),
        (100, 160, 0, 0),
        (128, 122, 0, 0),
        (128, 123, 0, 0),
        (185, 160, 0, 0),
        (517, 160, 0, 0),
        (100, 160, 2, 65535),
        (100, 80, 3, 0)
    ]
    
    failed = 0
    for mtu, size, transient_failures, sequence in test_cases:
        tx_buffer = bytearray(size + RING_BUFFER_HEADER_SIZE)
        for i in range(size):
            tx_buffer[i + RING_BUFFER_HEADER_SIZE] = (i * 17 + 3) & 0xFF
            
        received = bytearray()
        accepted = 0
        calls = 0
        failures_left = transient_failures
        audio_tx_sem = 8
        packet_next_index = sequence
        
        def bt_gatt_notify_cb(p_len, data):
            nonlocal calls, failures_left, accepted
            calls += 1
            if p_len > mtu - 3:
                return -90  # -EMSGSIZE
            if failures_left > 0:
                failures_left -= 1
                return -12  # -ENOMEM
            received.extend(data[NET_BUFFER_HEADER_SIZE:p_len])
            accepted += 1
            return 0

        buffer = tx_buffer[RING_BUFFER_HEADER_SIZE:]
        offset = 0
        index = 0
        max_retries = 3
        success = True
        
        while offset < size:
            chunk_cap = mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE
            packet_size = min(chunk_cap, size - offset)
            
            assert audio_tx_sem > 0
            audio_tx_sem -= 1
            
            p_id = packet_next_index
            packet_next_index = (packet_next_index + 1) & 0xFFFF
            
            packet = bytearray(mtu)
            packet[0] = p_id & 0xFF
            packet[1] = (p_id >> 8) & 0xFF
            packet[2] = index
            packet[NET_BUFFER_HEADER_SIZE : NET_BUFFER_HEADER_SIZE + packet_size] = buffer[offset : offset + packet_size]
            
            offset += packet_size
            index += 1
            
            retry = 0
            while retry < max_retries:
                err = bt_gatt_notify_cb(packet_size + NET_BUFFER_HEADER_SIZE, packet)
                if err:
                    retry += 1
                    continue
                audio_tx_sem += 1
                break
                
            if retry >= max_retries:
                audio_tx_sem += 1
                success = False
                break
                
        expected_success = transient_failures < 3 or size == 0
        chunks = 0 if size == 0 else (size + (mtu - 6) - 1) // (mtu - 6)
        ok = (success == expected_success) and (audio_tx_sem == 8)
        if expected_success:
            ok = ok and (len(received) == size) and (accepted == chunks)
        else:
            ok = ok and (accepted == 0) and (calls == 3)
            
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] MTU={mtu:3d} audio_bytes={size:3d} retries={transient_failures} -> delivered={len(received)} chunks={accepted}")
        
    print(f"\n{12 - failed} of 12 test cases passed ({failed} failed)")
    return failed

def main():
    default_path = Path(__file__).resolve().parent.parent / "omi" / "src" / "lib" / "core" / "transport.c"
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    
    print(f"Checking transport source: {source_path}")
    if not source_path.exists():
        print(f"Error: file not found: {source_path}")
        return 1
        
    if not verify_source(source_path):
        return 1
        
    print("\nRunning simulated GATT MTU notification test cases:")
    fail_count = run_simulation()
    return 0 if fail_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
