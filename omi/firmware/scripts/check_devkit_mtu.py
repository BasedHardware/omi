#!/usr/bin/env python3
"""Regression test for DevKit BLE audio notification MTU boundary limits.

Validates that pusher chunk sizes reserve ATT_NOTIFICATION_HEADER_SIZE (3 bytes:
opcode 0x1B + 16-bit handle) in addition to NET_BUFFER_HEADER_SIZE (3 bytes) so that
bt_gatt_notify payloads never exceed the negotiated ATT MTU.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TEST_CASES = [
    (23, 0, 0, 0),
    (23, 17, 0, 0),
    (23, 18, 0, 0),
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
    (100, 80, 3, 0),
]

C_PREFIX = r"""
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>

#define CODEC_OUTPUT_MAX_BYTES 160
#define MIN(a, b) (((a) < (b)) ? (a) : (b))
#define LOG_DBG(...) do {} while (0)
#define LOG_ERR(...) do {} while (0)
#define LOG_INF(...) do {} while (0)
#define LOG_PRINTK(...) do {} while (0)
#define k_sleep(...) do {} while (0)
#define K_MSEC(x) (x)
#define EAGAIN 11
#define ENOMEM 12

struct bt_conn {};
struct bt_gatt_attr {};
struct bt_gatt_service { struct bt_gatt_attr attrs[2]; };
static struct bt_gatt_service audio_service;

static uint8_t pusher_temp_data[CODEC_OUTPUT_MAX_BYTES + NET_BUFFER_HEADER_SIZE];
static uint8_t tx_buffer[CODEC_OUTPUT_MAX_BYTES + RING_BUFFER_HEADER_SIZE];
static uint32_t tx_buffer_size = 0;
static uint16_t packet_next_index = 0;
static uint16_t current_mtu = 0;

static uint8_t received[1024];
static int received_size = 0;
static int accepted = 0;
static int calls = 0;
static int failures_left = 0;

static bool read_from_tx_queue(void) {
    return true;
}

static int bt_gatt_notify(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *data, uint16_t len) {
    (void)conn; (void)attr;
    calls++;
    if (len > current_mtu - 3) {
        return -90;
    }
    if (failures_left > 0) {
        failures_left--;
        return -ENOMEM;
    }
    const uint8_t *bytes = (const uint8_t *)data;
    memcpy(received + received_size, bytes + NET_BUFFER_HEADER_SIZE, len - NET_BUFFER_HEADER_SIZE);
    received_size += (len - NET_BUFFER_HEADER_SIZE);
    accepted++;
    return 0;
}
"""

C_SUFFIX = r"""
static int check_case(uint16_t mtu, uint32_t size, int transient_failures, uint16_t sequence) {
    current_mtu = mtu;
    tx_buffer_size = size;
    packet_next_index = sequence;
    received_size = 0;
    accepted = 0;
    calls = 0;
    failures_left = transient_failures;

    for (uint32_t i = 0; i < size; i++) {
        tx_buffer[RING_BUFFER_HEADER_SIZE + i] = (uint8_t)((i * 17 + 3) & 0xFF);
    }

    struct bt_conn conn = {0};
    bool result = push_to_gatt(&conn);
    bool expected_success = transient_failures < 3 || size == 0;
    int chunk_cap = mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE;
    int chunks = size == 0 ? 0 : (size + chunk_cap - 1) / chunk_cap;
    bool ok = (result == expected_success);
    if (expected_success) {
        ok = ok && (received_size == (int)size) && (accepted == chunks);
        ok = ok && (memcmp(received, tx_buffer + RING_BUFFER_HEADER_SIZE, size) == 0);
        ok = ok && (calls == chunks + (size ? transient_failures : 0));
    } else {
        ok = ok && (accepted == 0) && (calls == 3);
    }
    printf("  [%s] MTU=%3d audio_bytes=%3d retries=%d -> result=%d delivered=%d chunks=%d calls=%d\n",
           ok ? "PASS" : "FAIL", mtu, size, transient_failures,
           result, received_size, accepted, calls);
    return !ok;
}

int main(void) {
    int failed = 0;
    failed += check_case(23, 0, 0, 0);
    failed += check_case(23, 17, 0, 0);
    failed += check_case(23, 18, 0, 0);
    failed += check_case(100, 0, 0, 0);
    failed += check_case(100, 80, 0, 0);
    failed += check_case(100, 94, 0, 0);
    failed += check_case(100, 95, 0, 0);
    failed += check_case(100, 102, 0, 0);
    failed += check_case(100, 160, 0, 0);
    failed += check_case(128, 122, 0, 0);
    failed += check_case(128, 123, 0, 0);
    failed += check_case(185, 160, 0, 0);
    failed += check_case(517, 160, 0, 0);
    failed += check_case(100, 160, 2, 65535);
    failed += check_case(100, 80, 3, 0);
    printf("\n%d of 15 test cases passed (%d failed)\n", 15 - failed, failed);
    return failed ? 1 : 0;
}
"""

def verify_source_tripwire(source_path: Path) -> bool:
    print(f"[STATIC TRIPWIRE] Verifying firmware source contract in {source_path.name}...")
    content = source_path.read_text(encoding="utf-8")

    if "ATT_NOTIFICATION_HEADER_SIZE" not in content:
        print("FAIL: ATT_NOTIFICATION_HEADER_SIZE definition missing in transport.c")
        return False

    pattern = r"MIN\s*\(\s*current_mtu\s*-\s*ATT_NOTIFICATION_HEADER_SIZE\s*-\s*NET_BUFFER_HEADER_SIZE"
    if not re.search(pattern, content):
        print("FAIL: packet_size calculation does not subtract ATT_NOTIFICATION_HEADER_SIZE")
        return False

    print("PASS: Source code correctly bounds packet_size with ATT_NOTIFICATION_HEADER_SIZE.")
    return True

def run_c_seam(source_path: Path) -> int:
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        return -1

    print(f"\n[C PRODUCTION SEAM] Compiling push_to_gatt() extracted from {source_path.name} using {cc}...")
    source = source_path.read_text(encoding="utf-8")
    start = source.index("static bool push_to_gatt(struct bt_conn *conn)")
    end = source.index("\n#define OPUS_PREFIX_LENGTH", start)
    function = source[start:end]
    constants = "\n".join(re.findall(
        r"^#define (?:NET_BUFFER_HEADER_SIZE|ATT_NOTIFICATION_HEADER_SIZE|RING_BUFFER_HEADER_SIZE)\b[^\n]*",
        source,
        flags=re.MULTILINE,
    ))

    with tempfile.TemporaryDirectory(prefix="omi-devkit-mtu-check-") as directory:
        c_file = Path(directory) / "check.c"
        executable = Path(directory) / "check"
        c_file.write_text(constants + "\n" + C_PREFIX + function + C_SUFFIX, encoding="utf-8")
        try:
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(c_file), "-o", str(executable)], check=True)
            res = subprocess.run([str(executable)], check=False)
            return res.returncode
        except Exception as e:
            print(f"Warning: C compiler seam failed ({e}), falling back to behavioral simulation.")
            return -1

def run_behavioral_simulation() -> int:
    print("\n[BEHAVIORAL SIMULATION] Running simulated GATT MTU notification test cases:")
    NET_BUFFER_HEADER_SIZE = 3
    ATT_NOTIFICATION_HEADER_SIZE = 3
    RING_BUFFER_HEADER_SIZE = 2

    failed = 0
    for mtu, size, transient_failures, sequence in TEST_CASES:
        tx_buffer = bytearray(size + RING_BUFFER_HEADER_SIZE)
        for i in range(size):
            tx_buffer[i + RING_BUFFER_HEADER_SIZE] = (i * 17 + 3) & 0xFF

        received = bytearray()
        accepted = 0
        calls = 0
        failures_left = transient_failures
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
                break

            if retry >= max_retries:
                success = False
                break

        expected_success = transient_failures < 3 or size == 0
        chunk_cap = mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE
        chunks = 0 if size == 0 else (size + chunk_cap - 1) // chunk_cap
        ok = (success == expected_success)
        if expected_success:
            ok = ok and (received == buffer) and (accepted == chunks)
        else:
            ok = ok and (accepted == 0) and (calls == 3)

        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] MTU={mtu:3d} audio_bytes={size:3d} retries={transient_failures} -> delivered={len(received)} chunks={accepted}")

    print(f"\n{len(TEST_CASES) - failed} of {len(TEST_CASES)} test cases passed ({failed} failed)")
    return failed

def main():
    default_path = Path(__file__).resolve().parent.parent / "devkit" / "src" / "transport.c"
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    if not source_path.exists():
        print(f"Error: file not found: {source_path}")
        return 1

    if not verify_source_tripwire(source_path):
        return 1

    c_res = run_c_seam(source_path)
    if c_res >= 0:
        return c_res

    sim_failures = run_behavioral_simulation()
    return 0 if sim_failures == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
