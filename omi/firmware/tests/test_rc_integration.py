#!/usr/bin/env python3
"""Compile production deferred-init and recovery GATT seams with host doubles."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "omi/src"


class IntegrationTests(unittest.TestCase):
    def compile_run(self, source, headers, flags=()):
        with tempfile.TemporaryDirectory(prefix="cv1-integration-") as temp:
            out = Path(temp)
            for name, text in headers.items():
                path = out / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            (out / "test.c").write_text(source)
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all", *flags,
                            "-I" + str(out), "-I" + str(SRC), "-I" + str(HERE / "stubs"),
                            str(out / "test.c"), "-o", str(out / "test")], check=True)
            subprocess.run([str(out / "test")], check=True)

    def test_bus_before_children_for_stock_and_cmd12_host(self):
        headers = {
            "zephyr/device.h": """#include <stddef.h>
struct device { const char *name; };
extern struct device devices[8];
int device_init(const struct device *dev);
static inline int device_is_ready(const struct device *dev) { (void)dev; return 0; }
#define DEVICE_DT_GET(n) (&devices[n])
""",
            "zephyr/devicetree.h": """#define DT_NODELABEL(n) n
#define DT_NODE_HAS_STATUS(n, s) 1
#define DT_CHILD(n, c) 7
#define i2c2 1
#define pdm0 2
#define i2s0 3
#define adc 4
#define lsm6ds3tr_c 5
#define sdhc0 6
""",
            "zephyr/kernel.h": "#define printk(...) ((void)0)\n#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))\n",
            "zephyr/storage/disk_access.h": "int disk_access_init(const char *name);\n",
        }
        source = '#include <assert.h>\n#include "' + str(SRC / "safe_mode_devices.c") + '"\n' + """
struct device devices[8];
void watchdog_feed(void) {}
void omi_boot_telemetry_sd_failure(void) {}
int disk_access_init(const char *name) { (void)name; return 0; }
static unsigned calls, fail_at;
int device_init(const struct device *dev) {
    assert(dev == &devices[++calls]);
    return calls == fail_at ? -5 : 0;
}
int main(void) {
    assert(safe_mode_devices_init() == 0 && calls == 7);
    calls = 0; fail_at = 6;
    assert(safe_mode_devices_init() == -5 && calls == 6);
    return 0;
}
"""
        flags = ["-DCONFIG_" + name + "=1" for name in (
            "I2C", "AUDIO_DMIC_NRFX_PDM", "I2S_NRFX", "ADC_NRFX_SAADC", "LSM6DSL", "DISK_DRIVER_SDMMC")]
        for driver in ("SPI_SDHC", "OMI_SDHC_SPI_CMD12_FIX"):
            with self.subTest(driver=driver):
                self.compile_run(source, headers, flags + ["-DCONFIG_" + driver + "=1"])

    def test_safe_sd_only_order_errors_and_fault_exclusion(self):
        headers = {
            "zephyr/device.h": """#include <stddef.h>
struct device { const char *name; };
extern struct device devices[3];
int device_init(const struct device *dev);
int device_is_ready(const struct device *dev);
#define DEVICE_DT_GET(n) (&devices[n])
#define DEVICE_DT_DEFINE(n, fn, ...) static int (*fault_device_init)(const struct device *) = fn
""",
            "zephyr/devicetree.h": """#define DT_NODELABEL(n) n
#define DT_NODE_HAS_STATUS(n, s) 1
#define DT_CHILD(n, c) 2
#define safe_mode_fault 0
#define sdhc0 1
""",
            "zephyr/kernel.h": """#define printk(...) ((void)0)
static inline void k_busy_wait(unsigned int us) { (void)us; }
#define ARG_UNUSED(x) (void)(x)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
""",
            "zephyr/storage/disk_access.h": "int disk_access_init(const char *name);",
        }
        source = '#include <assert.h>\n#include <string.h>\n#include "' + str(SRC / "safe_mode_devices.c") + '"\n' + """
struct device devices[3];
static unsigned stage, failures, feeds;
static int injected, ready;
int device_is_ready(const struct device *dev) { assert(dev != &devices[0]); return ready; }
int device_init(const struct device *dev) {
    assert(dev == &devices[++stage] && stage <= 2);
    assert(feeds == stage);
    return injected;
}
void watchdog_feed(void) { ++feeds; }
void omi_boot_telemetry_sd_failure(void) { ++failures; }
int disk_access_init(const char *name) {
    assert(!strcmp(name, "SDMMC") && stage == (ready ? 0 : 2) && feeds == 3);
    return injected;
}
int main(void) {
    assert(fault_device_init != NULL);
    safe_mode_sd_bus_init(); assert(stage == 2 && feeds == 4 && failures == 0);
    stage = feeds = 0; injected = -134;
    safe_mode_sd_bus_init(); assert(stage == 2 && feeds == 4 && failures == 3);
    stage = feeds = failures = 0; ready = 1; injected = 0;
    safe_mode_sd_bus_init(); assert(stage == 0 && feeds == 4 && failures == 0);
    return 0;
}
"""
        for driver in ("SPI_SDHC", "OMI_SDHC_SPI_CMD12_FIX"):
            with self.subTest(driver=driver):
                self.compile_run(source, headers, ["-DCONFIG_DISK_DRIVER_SDMMC=1",
                    "-DCONFIG_OMI_FAULT_INJECT_DRIVER_HANG=1", "-DCONFIG_" + driver + "=1"])

    def test_secondary_read_check_counts_errors_and_mismatches(self):
        safe = (SRC / "safe_mode.c").read_text()
        start = safe.index("static bool secondary_readable(void)")
        end = safe.index("void safe_mode_run(void)", start)
        body = safe[end:]
        self.assertLess(body.index("safe_mode_sd_bus_init();"), body.index("secondary_readable()"))
        prefix = """
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#define FIXED_PARTITION_ID(n) 1
struct flash_area { int unused; };
static struct flash_area area;
static unsigned failures, reads, closes;
static int open_error, read_error, mismatch;
static void watchdog_feed(void) {}
static void omi_boot_telemetry_nor_failure(void) { ++failures; }
static int flash_area_open(int id, const struct flash_area **out) {
    assert(id == 1); *out = &area; return open_error;
}
static int flash_area_read(const struct flash_area *a, unsigned offset, void *out, unsigned size) {
    assert(a == &area && offset == 0 && size == 32); ++reads;
    memset(out, mismatch ? reads : 0xff, size); return read_error;
}
static void flash_area_close(const struct flash_area *a) { assert(a == &area); ++closes; }
"""
        suffix = """
int main(void) {
    assert(secondary_readable() && reads == 2 && closes == 1 && failures == 0);
    mismatch = 1; assert(!secondary_readable() && failures == 1 && closes == 2);
    mismatch = 0; read_error = -5; assert(!secondary_readable() && failures == 2 && closes == 3);
    open_error = -5; assert(!secondary_readable() && failures == 3 && closes == 3);
    return 0;
}
"""
        self.compile_run(prefix + safe[start:end] + suffix, {})

    def test_recovery_wire_layout_and_safe_service_without_bonds(self):
        transport = (SRC / "lib/core/transport.c").read_text()
        uuid_start = transport.index("static struct bt_uuid_128 diagnostics_service_uuid")
        cache_start = transport.index("/* One snapshot per connection.", uuid_start)
        attrs_start = transport.index("static struct bt_gatt_attr diagnostics_service_attr[]")
        attrs_end = transport.index("// Advertisement data", attrs_start)
        identity_start = transport.index("static int ensure_local_ble_identity(void)")
        identity_end = transport.index("//\n// Ring Buffer", identity_start)
        safe_start = transport.index("int transport_start_safe(void)")
        safe_end = transport.index("// periodic advertising", safe_start)
        headers = {"zephyr/sys/byteorder.h": """#include <stdint.h>
static inline void sys_put_le32(uint32_t v, uint8_t *p) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (uint8_t)(v >> (8 * i));
}
"""}
        prefix = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include "recovery_diagnostics.h"
#include <zephyr/kernel.h>
#define CONFIG_BT_MAX_CONN 2
#define BT_GATT_ERR(e) (-(e))
#define BT_ATT_ERR_INVALID_OFFSET 7
#define BT_ATT_ERR_UNLIKELY 14
#define CONFIG_BT_SETTINGS 1
#define CONFIG_BT_ID_MAX 1
#define CONFIG_BT_DEVICE_NAME "Omi"
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define LOG_ERR(...) ((void)0)
#define LOG_INF(...) ((void)0)
struct bt_uuid { uint32_t value; };
struct bt_uuid_128 { struct bt_uuid uuid; };
#define BT_UUID_128_ENCODE(a, b, c, d, e) (a)
#define BT_UUID_INIT_128(v) { .uuid = { (v) } }
struct bt_conn { unsigned index; };
static unsigned bt_conn_index(struct bt_conn *c) { return c->index; }
struct bt_conn_cb { void (*connected)(struct bt_conn *, uint8_t); void (*disconnected)(struct bt_conn *, uint8_t); };
static struct bt_conn_cb *connection_callbacks;
static void bt_conn_cb_register(struct bt_conn_cb *cb) { connection_callbacks = cb; }
struct bt_gatt_attr;
typedef ssize_t (*reader)(struct bt_conn *, const struct bt_gatt_attr *, void *, uint16_t, uint16_t);
struct bt_gatt_attr { const struct bt_uuid *uuid; reader read; };
struct bt_gatt_service { struct bt_gatt_attr *attrs; size_t count; };
#define BT_GATT_CHRC_READ 1
#define BT_GATT_PERM_READ 1
#define BT_GATT_PRIMARY_SERVICE(u) { &(u)->uuid, NULL }
#define BT_GATT_CHARACTERISTIC(u, properties, permissions, callback, w, data) {u, NULL}, {u, callback}
#define BT_GATT_SERVICE(a) {a, ARRAY_SIZE(a)}
static bool safe_active = true, advertising_started;
static unsigned settings_reads, identities, registrations;
static int enable_error, register_error;
static struct bt_gatt_service *registered;
bool safe_mode_active(void) { return safe_active; }
int settings_load(void) { ++settings_reads; return 0; }
typedef int bt_addr_le_t;
static void bt_id_get(bt_addr_le_t *a, size_t *n) { (void)a; *n = 0; }
static int bt_id_create(void *a, void *b) { (void)a; (void)b; ++identities; return 0; }
static int bt_enable(void *cb) { (void)cb; return enable_error; }
static void log_local_ble_addresses(void) {}
static int bt_gatt_service_register(struct bt_gatt_service *service) {
    ++registrations; registered = service; return register_error;
}
struct bt_data { unsigned type; const void *data; size_t size; };
#define BT_DATA_UUID16_ALL 1
#define BT_DATA_NAME_COMPLETE 2
#define BT_UUID_DIS_VAL 0x180a
#define BT_UUID_16_ENCODE(v) (v)
#define BT_DATA_BYTES(t, ...) {t, NULL, 0}
#define BT_DATA(t, p, n) {t, p, n}
#define BT_LE_ADV_OPT_CONNECTABLE 1
struct adv_param { unsigned options, min, max; };
#define BT_LE_ADV_PARAM(o, a, b, p) (&(struct adv_param){o, a, b})
static const struct bt_data bt_ad[] = {{0, NULL, 0}};
static int bt_le_adv_start(const struct adv_param *p, const struct bt_data *ad, size_t an,
                          const struct bt_data *sd, size_t sn) {
    assert(p->options == 1 && p->min == 1600 && p->max == 3200);
    assert(ad == bt_ad && an == 1 && sn == 2);
    assert(sd[1].type == BT_DATA_NAME_COMPLETE && sd[1].size == 3);
    assert(memcmp(sd[1].data, "Omi", 3) == 0);
    return 0;
}
static struct safe_mode_snapshot state = {
    .active = true, .latched = true, .bootstate = 1,
    .boot_count = 0x12345678, .reset_reason = 0x87654321, .latch_reason = 2
};
void safe_mode_snapshot_get(struct safe_mode_snapshot *out) { *out = state; }
static unsigned generation;
void omi_boot_telemetry_snapshot(struct omi_boot_record *out) {
    memset(out, 0, sizeof(*out)); out->boot_count = ++generation;
}
void omi_boot_record_encode(uint8_t out[OMI_BOOT_RECORD_SIZE], const struct omi_boot_record *r) {
    memset(out, 0, OMI_BOOT_RECORD_SIZE); out[0] = 1; out[4] = r->boot_count;
}
static ssize_t bt_gatt_attr_read(struct bt_conn *c, const struct bt_gatt_attr *a, void *buf,
                                uint16_t len, uint16_t offset, const void *value, uint16_t size) {
    (void)c; (void)a;
    if (offset > size) return -7;
    if (len > size - offset) len = size - offset;
    memcpy(buf, (const uint8_t *)value + offset, len); return len;
}
static ssize_t diagnostics_read_handler(struct bt_conn *c, const struct bt_gatt_attr *a, void *b,
                                       uint16_t l, uint16_t o) {
    (void)c; (void)a; (void)b; (void)l; (void)o; return 25;
}
'''
        suffix = r'''
int main(void) {
    assert(diagnostics_service.count == 5 && safe_diagnostics_service.count == 3);
    assert(diagnostics_service.attrs[0].uuid->value == 0x19b10040);
    assert(diagnostics_service.attrs[2].uuid->value == 0x19b10041);
    assert(diagnostics_service.attrs[4].uuid->value == 0x19b10042);
    assert(diagnostics_service.attrs[2].read == diagnostics_read_handler);
    assert(safe_diagnostics_service.attrs[2].uuid->value == 0x19b10042);
    uint8_t packet[OMI_RECOVERY_DIAGNOSTICS_SIZE];
    struct bt_conn conn = {0}, other = {1}, invalid = {2};
    const uint8_t expected[] = {2, 1, 1, 1, 0x78, 0x56, 0x34, 0x12,
                                0x21, 0x43, 0x65, 0x87, 2, 0, 0, 0};
    assert(recovery_diagnostics_read(&conn, NULL, packet, 16, 0) == 16);
    assert(memcmp(packet, expected, 16) == 0);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 4, 8) == 4);
    assert(memcmp(packet, expected + 8, 4) == 0);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 80, 16) == 80);
    assert(packet[0] == 1 && packet[4] == 1 && generation == 1);
    assert(recovery_diagnostics_read(&other, NULL, packet, 16, 0) == 16 && generation == 2);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 4, 20) == 4 && packet[0] == 1);
    recovery_reset_read_cache(&conn);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 4, 20) == 4 && packet[0] == 3);
    recovery_reset_read_cache(NULL); recovery_reset_read_cache(&invalid);
    assert(recovery_diagnostics_read(NULL, NULL, packet, 16, 0) == -14);
    assert(recovery_diagnostics_read(&invalid, NULL, packet, 16, 0) == -14);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 16, 96) == 0);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 16, 97) == -7);
    assert(transport_start_safe() == 0 && advertising_started);
    assert(connection_callbacks == &recovery_callbacks);
    connection_callbacks->disconnected(&conn, 0);
    connection_callbacks->connected(&conn, 0);
    assert(recovery_diagnostics_read(&conn, NULL, packet, 4, 20) == 4 && packet[0] == 4);
    assert(registered == &safe_diagnostics_service && registrations == 1);
    assert(settings_reads == 0 && identities == 1);
    safe_active = false;
    assert(ensure_local_ble_identity() == 0 && settings_reads == 1);
    enable_error = -5;
    assert(transport_start_safe() == -5 && registrations == 1);
    enable_error = 0; register_error = -12;
    assert(transport_start_safe() == -12 && registrations == 2);
    return 0;
}
'''
        production = (transport[uuid_start:cache_start] + transport[attrs_start:attrs_end]
                      + transport[identity_start:identity_end] + transport[safe_start:safe_end])
        self.compile_run(prefix + production + suffix, headers)


if __name__ == "__main__":
    unittest.main()
