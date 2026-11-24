/* Owns the boot telemetry cache; settings IO is isolated from increment and BLE read paths. */
#include "boot_telemetry.h"

#include <errno.h>
#include <string.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>

#include "safe_mode.h"
#ifndef CONFIG_OMI_NATIVE_SIM
#include <zephyr/dfu/mcuboot.h>
#include <zephyr/storage/flash_map.h>
#endif

static struct omi_boot_record record;
static bool started, opened, writable, dirty, attempted;
static int64_t last_attempt_ms;
K_MUTEX_DEFINE(telemetry_lock);

void omi_boot_telemetry_start(uint32_t reset_reason, bool fatal, bool safe, uint32_t safe_reason)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    if (!started) {
        record.flags = OMI_BOOT_VALID | (safe ? OMI_BOOT_SAFE : 0);
        record.reset_reason = reset_reason;
        record.last_fatal = fatal;
        record.safe_reason = safe_reason;
        record.boot_count = safe_mode_total_boots();
        memcpy(record.current.fw, CONFIG_BT_DIS_FW_REV_STR, sizeof(CONFIG_BT_DIS_FW_REV_STR));
        _Static_assert(sizeof(CONFIG_BT_DIS_FW_REV_STR) <= OMI_BOOT_FW_SIZE, "firmware string too long");
#ifndef CONFIG_OMI_NATIVE_SIM
        /* Primary header only: no secondary/NOR access for identity discovery. */
        struct mcuboot_img_header header;
        if (!boot_read_bank_header(FIXED_PARTITION_ID(slot0_partition), &header, sizeof(header)) &&
            header.mcuboot_version == 1) {
            const struct mcuboot_img_sem_ver *v = &header.h.v1.sem_ver;
            uint8_t *p = record.current.header_version;
            p[0] = v->major;
            p[1] = v->minor;
            p[2] = (uint8_t) v->revision;
            p[3] = (uint8_t) (v->revision >> 8);
            for (unsigned int i = 0; i < 4; ++i) {
                p[4 + i] = (uint8_t) (v->build_num >> (8 * i));
            }
            record.flags |= OMI_BOOT_HEADER_VALID;
        }
#endif
        started = true;
        dirty = true;
    }
    k_mutex_unlock(&telemetry_lock);
}

static int load_record(const char *name, size_t len, settings_read_cb read_cb, void *arg, void *param)
{
    ARG_UNUSED(param);
    if (name && *name) {
        return 0;
    }
    uint8_t bytes[OMI_BOOT_RECORD_SIZE];
    struct omi_boot_record previous;
    if (len != sizeof(bytes)) {
        printk("Boot telemetry record size invalid; starting a new record\n");
        return 0;
    }
    int rc = read_cb(arg, bytes, sizeof(bytes));
    if (rc != sizeof(bytes)) {
        return rc < 0 ? rc : -EIO;
    }
    if (!omi_boot_record_decode(&previous, bytes, sizeof(bytes))) {
        printk("Boot telemetry record invalid; starting a new record\n");
        return 0;
    }
    record.outcome = omi_update_classify(&previous, &record.current, record.flags & OMI_BOOT_HEADER_VALID);
    record.previous = previous.current;
    if (previous.flags & OMI_BOOT_VALID) {
        record.flags |= OMI_BOOT_PREVIOUS_VALID;
    }
    if (previous.flags & OMI_BOOT_HEADER_VALID) {
        record.flags |= OMI_BOOT_PREVIOUS_HEADER_VALID;
    }
    record.boot_count = safe_mode_restore_total_boots(previous.boot_count);
    record.pending_before_boot = previous.upload_pending;
    record.last_fatal |= previous.last_fatal;
    /* Preserve failures counted before settings became available in SAFE. */
    uint32_t nor = record.nor_read_failures;
    uint32_t sd = record.sd_init_failures;
    record.nor_read_failures =
        UINT32_MAX - previous.nor_read_failures < nor ? UINT32_MAX : previous.nor_read_failures + nor;
    record.sd_init_failures = UINT32_MAX - previous.sd_init_failures < sd ? UINT32_MAX : previous.sd_init_failures + sd;
    return 0;
}

static void save_record(bool force)
{
    int64_t now = k_uptime_get();
    if (!writable || !dirty || (!force && !omi_boot_save_due(dirty, attempted, last_attempt_ms, now))) {
        return;
    }
    uint8_t bytes[OMI_BOOT_RECORD_SIZE];
    omi_boot_record_encode(bytes, &record);
    /* Throttle failures too: never hammer a failing NVS backend. */
    attempted = true;
    last_attempt_ms = now;
    int err = settings_save_one("omi/boot_telemetry", bytes, sizeof(bytes));
    if (!err) {
        dirty = false;
    } else {
        printk("Boot telemetry save failed (%d)\n", err);
    }
}

void omi_boot_telemetry_open(void)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    if (started && !opened) {
        opened = true;
        int err = settings_subsys_init();
        if (!err) {
            err = settings_load_subtree_direct("omi/boot_telemetry", load_record, NULL);
        }
        /* Bad record is replaceable; failed backend access is not. */
        writable = err == 0;
        if (writable) {
            /* Also seed a first/missing record, after observing this boot. */
            (void) safe_mode_restore_total_boots(0);
        }
        save_record(false);
    }
    k_mutex_unlock(&telemetry_lock);
}

void omi_boot_telemetry_poll(void)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    save_record(false);
    k_mutex_unlock(&telemetry_lock);
}

void omi_boot_telemetry_upload_pending(void)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    if (!record.upload_pending) {
        record.upload_pending = true;
        dirty = true;
        /* One transition per boot, persisted before the client can reboot us. */
        save_record(true);
    }
    k_mutex_unlock(&telemetry_lock);
}

void omi_boot_telemetry_snapshot(struct omi_boot_record *out)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    *out = record;
    k_mutex_unlock(&telemetry_lock);
}

void omi_boot_telemetry_nor_failure(void)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    uint32_t next = omi_counter_increment(record.nor_read_failures);
    dirty |= next != record.nor_read_failures;
    record.nor_read_failures = next;
    k_mutex_unlock(&telemetry_lock);
}

void omi_boot_telemetry_sd_failure(void)
{
    k_mutex_lock(&telemetry_lock, K_FOREVER);
    uint32_t next = omi_counter_increment(record.sd_init_failures);
    dirty |= next != record.sd_init_failures;
    record.sd_init_failures = next;
    k_mutex_unlock(&telemetry_lock);
}
