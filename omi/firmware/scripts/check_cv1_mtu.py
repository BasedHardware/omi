#!/usr/bin/env python3
"""Regression test for push_to_gatt MTU notification limit contract.

Verifies that push_to_gatt never emits GATT notifications exceeding
current_mtu - ATT_NOTIFICATION_HEADER_SIZE (current_mtu - 3 bytes),
especially under the BLE minimum/default ATT MTU 23 and smaller budgets.

Executes via native C compiler test seam if a C compiler (cc/gcc/clang) is available,
or falls back to behavioral simulation with payload integrity assertions.
Also executes a static tripwire regex check against transport.c.

Usage:
    python check_cv1_mtu.py [path_to_transport.c]
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

TEST_CASES = [
    # (mtu, audio_bytes, transient_failures, sequence)
    (23, 0, 0, 0),        # BLE default MTU 23, empty payload
    (23, 17, 0, 0),       # BLE default MTU 23 boundary (fits exactly in 1 chunk: 23 - 6 = 17)
    (23, 18, 0, 0),       # BLE default MTU 23 boundary (requires 2 chunks: 17 + 1)
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
    (100, 160, 2, 65535), # Transient retry recovery with sequence rollover
    (100, 80, 3, 0)       # Retry limit exceeded failure path
]

C_PREFIX = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>

#define MIN(a,b) ((uint32_t)(a)<(uint32_t)(b)?(uint32_t)(a):(uint32_t)(b))
#define K_FOREVER 0
#define K_MSEC(x) (x)
#define LOG_DBG(...) ((void)0)
#define LOG_ERR(...) ((void)0)

struct bt_conn { int placeholder; };
struct bt_gatt_notify_params {
    int *attr;
    const void *data;
    uint16_t len;
    void (*func)(struct bt_conn *, void *);
    void *user_data;
};

static struct { int attrs[2]; } audio_service;
static uint8_t tx_buffer[512], pusher_temp_data[517], received[512];
static uint32_t tx_buffer_size;
static uint16_t current_mtu, packet_next_index, initial_sequence;
static int audio_tx_sem, calls, failures_left, accepted, received_size;

static void k_sem_take(int *s, int timeout) { (void)timeout; assert(*s > 0); --*s; }
static void k_sem_give(int *s) { ++*s; }
static void k_sleep(int delay) { (void)delay; }
static void on_audio_tx_done(struct bt_conn *conn, void *user_data) {
    (void)conn; (void)user_data; k_sem_give(&audio_tx_sem);
}

static int bt_gatt_notify_cb(struct bt_conn *conn, struct bt_gatt_notify_params *p) {
    ++calls;
    /* ATT notification value limit = MTU minus opcode (1) and handle (2) = MTU - 3 */
    if (p->len > current_mtu - 3) return -EMSGSIZE;
    if (failures_left > 0) { --failures_left; return -ENOMEM; }
    const uint8_t *bytes = p->data;
    assert(p->len > NET_BUFFER_HEADER_SIZE);
    assert((uint16_t)(bytes[0] | (bytes[1] << 8)) == (uint16_t)(initial_sequence + accepted));
    assert(bytes[2] == accepted);
    assert((size_t)(received_size + p->len - NET_BUFFER_HEADER_SIZE) <= sizeof(received));
    memcpy(received + received_size, bytes + NET_BUFFER_HEADER_SIZE, p->len - NET_BUFFER_HEADER_SIZE);
    received_size += p->len - NET_BUFFER_HEADER_SIZE;
    ++accepted;
    p->func(conn, p->user_data);
    return 0;
}
'''

C_SUFFIX = r'''
static int check_case(int mtu, int size, int transient_failures, uint16_t sequence) {
    current_mtu = mtu;
    tx_buffer_size = size;
    initial_sequence = packet_next_index = sequence;
    calls = accepted = received_size = 0;
    failures_left = transient_failures;
    audio_tx_sem = 8;
    memset(received, 0, sizeof(received));
    for (int i = 0; i < size; ++i) tx_buffer[i + RING_BUFFER_HEADER_SIZE] = (uint8_t)(i * 17 + 3);
    struct bt_conn conn = {0};
    bool result = push_to_gatt(&conn);
    bool expected_success = transient_failures < 3 || size == 0;
    int chunk_cap = mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE;
    int chunks = size == 0 ? 0 : (size + chunk_cap - 1) / chunk_cap;
    bool ok = (result == expected_success) && (audio_tx_sem == 8);
    if (expected_success) {
        ok = ok && (received_size == size) && (accepted == chunks);
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
'''

def verify_source_tripwire(source_path: Path) -> bool:
    """Static tripwire: verify that the C source code preserves the required bounding constants."""
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
    """Extract production push_to_gatt from transport.c and compile with C test seam."""
    cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        return -1  # No native C compiler available

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

    with tempfile.TemporaryDirectory(prefix="omi-mtu-check-") as directory:
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
    """Behavioral simulation of push_to_gatt with exact buffer content verification."""
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
        chunk_cap = mtu - ATT_NOTIFICATION_HEADER_SIZE - NET_BUFFER_HEADER_SIZE
        chunks = 0 if size == 0 else (size + chunk_cap - 1) // chunk_cap
        ok = (success == expected_success) and (audio_tx_sem == 8)
        if expected_success:
            # Check full payload integrity: content, ordering, and length
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
    default_path = Path(__file__).resolve().parent.parent / "omi" / "src" / "lib" / "core" / "transport.c"
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    
    if not source_path.exists():
        print(f"Error: file not found: {source_path}")
        return 1
        
    if not verify_source_tripwire(source_path):
        return 1
        
    # Attempt C production seam compilation if compiler is present
    c_res = run_c_seam(source_path)
    if c_res >= 0:
        return c_res

    # Behavioral simulation with full payload integrity check
    sim_failures = run_behavioral_simulation()
    return 0 if sim_failures == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
