/* Actual persistence adapter, pure classification and wire codec; OS/NVS doubled. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#undef CONFIG_OMI_NATIVE_SIM
#include "../omi/src/boot_telemetry.c"

static uint8_t disk[OMI_BOOT_RECORD_SIZE];
static bool disk_valid;
static unsigned writes, reads;
static int save_error, load_error, init_error;
static int64_t now;
static int header_error;
static unsigned header_reads;
int boot_read_bank_header(uint8_t area_id, struct mcuboot_img_header *header, size_t header_size)
{
    assert(area_id == 0 && header_size == sizeof(*header));
    ++header_reads;
    *header = (struct mcuboot_img_header){
        .mcuboot_version = 1, .h.v1.sem_ver = {.major = 3, .minor = 0, .revision = 23, .build_num = 0x12345678}};
    return header_error;
}

uint32_t safe_mode_total_boots(void)
{
    return 1;
}
uint32_t safe_mode_restore_total_boots(uint32_t persisted_count)
{
    return omi_counter_increment(persisted_count);
}
int64_t k_uptime_get(void)
{
    return now;
}
int settings_subsys_init(void)
{
    return init_error;
}
int settings_save_one(const char *key, const void *value, size_t len)
{
    assert(!strcmp(key, "omi/boot_telemetry") && len == sizeof(disk));
    ++writes;
    if (save_error)
        return save_error;
    memcpy(disk, value, len);
    disk_valid = true;
    return 0;
}
static ssize_t read_disk(void *arg, void *value, size_t len)
{
    (void) arg;
    assert(len == sizeof(disk));
    memcpy(value, disk, len);
    return len;
}
int settings_load_subtree_direct(const char *key, settings_load_direct_cb cb, void *param)
{
    assert(!strcmp(key, "omi/boot_telemetry"));
    ++reads;
    if (load_error)
        return load_error;
    return disk_valid ? cb(NULL, sizeof(disk), read_disk, NULL, param) : 0;
}
static void reboot(bool safe)
{
    memset(&record, 0, sizeof(record));
    started = opened = writable = dirty = attempted = false;
    last_attempt_ms = now = 0;
    omi_boot_telemetry_start(0x12345678, false, safe, safe ? 2 : 0);
}
static void test_codec(void)
{
    struct omi_boot_record a = {.flags = 31,
                                .outcome = OMI_UPDATE_UPDATED,
                                .pending_before_boot = true,
                                .boot_count = 0x12345678,
                                .reset_reason = 0x87654321,
                                .last_fatal = 1,
                                .safe_reason = 2,
                                .nor_read_failures = UINT32_MAX,
                                .sd_init_failures = 0xabcdef,
                                .current = {.fw = "new", .header_version = {1, 2, 3, 4, 5, 6, 7, 8}},
                                .previous = {.fw = "old", .header_version = {9, 8, 7, 6, 5, 4, 3, 2}},
                                .upload_pending = true};
    uint8_t bytes[OMI_BOOT_RECORD_SIZE], again[OMI_BOOT_RECORD_SIZE];
    struct omi_boot_record b;
    omi_boot_record_encode(bytes, &a);
    assert(bytes[0] == 1 && bytes[4] == 0x78 && bytes[7] == 0x12);
    assert(bytes[8] == 0x21 && bytes[11] == 0x87 && bytes[12] == 1);
    assert(!memcmp(bytes + 28, "new", 4) && !memcmp(bytes + 52, "old", 4));
    assert(!memcmp(bytes + 44, a.current.header_version, 8) && bytes[76] == 1);
    assert(omi_boot_record_decode(&b, bytes, sizeof(bytes)));
    omi_boot_record_encode(again, &b);
    assert(!memcmp(bytes, again, sizeof(bytes)));
    assert(!omi_boot_record_decode(&b, bytes, sizeof(bytes) - 1));
    const unsigned offsets[] = {0, 1, 2, 3, 12, 16, 76, 77, 78, 79};
    for (unsigned i = 0; i < sizeof(offsets) / sizeof(offsets[0]); ++i) {
        uint8_t old = bytes[offsets[i]];
        bytes[offsets[i]] = 0xff;
        assert(!omi_boot_record_decode(&b, bytes, sizeof(bytes)));
        bytes[offsets[i]] = old;
    }
    memset(bytes + 28, 'x', 16);
    assert(!omi_boot_record_decode(&b, bytes, sizeof(bytes)));
    omi_boot_record_encode(bytes, &a);
    memset(bytes + 52, 'x', 16);
    assert(!omi_boot_record_decode(&b, bytes, sizeof(bytes)));
}
static void test_outcomes(void)
{
    struct omi_boot_record old = {.flags = OMI_BOOT_VALID | OMI_BOOT_HEADER_VALID,
                                  .current = {.fw = "3.0.23", .header_version = {3, 0, 23}}};
    struct omi_image_identity running = old.current;
    assert(omi_update_classify(&old, &running, true) == OMI_UPDATE_UNCHANGED);
    old.upload_pending = true;
    assert(omi_update_classify(&old, &running, true) == OMI_UPDATE_NOT_INSTALLED);
    running.header_version[4] = 1;
    assert(omi_update_classify(&old, &running, true) == OMI_UPDATE_UPDATED);
    assert(omi_update_classify(&old, &running, false) == OMI_UPDATE_UNKNOWN);
    running.fw[5] = '4';
    assert(omi_update_classify(&old, &running, false) == OMI_UPDATE_UPDATED);
    old.flags = 0;
    assert(omi_update_classify(&old, &running, true) == OMI_UPDATE_UNKNOWN);
    old.flags = OMI_BOOT_VALID;
    running = old.current;
    assert(omi_update_classify(&old, &running, true) == OMI_UPDATE_UNKNOWN);
}
int main(void)
{
    test_codec();
    test_outcomes();
    assert(omi_counter_increment(0) == 1);
    assert(omi_counter_increment(UINT32_MAX - 1) == UINT32_MAX);
    assert(omi_counter_increment(UINT32_MAX) == UINT32_MAX);
    assert(!omi_boot_save_due(false, false, 0, 0));
    assert(omi_boot_save_due(true, false, 0, 0));
    assert(!omi_boot_save_due(true, true, 1, 0));
    assert(!omi_boot_save_due(true, true, 0, OMI_BOOT_SAVE_INTERVAL_MS - 1));
    assert(omi_boot_save_due(true, true, 0, OMI_BOOT_SAVE_INTERVAL_MS));
    reboot(false);
    omi_boot_telemetry_open();
    assert(writes == 1 && reads == 1 && record.boot_count == 1 && record.reset_reason == 0x12345678);
    omi_boot_telemetry_open();
    assert(writes == 1 && reads == 1);
    for (unsigned i = 0; i < 10000; ++i) {
        omi_boot_telemetry_sd_failure();
        omi_boot_telemetry_nor_failure();
        omi_boot_telemetry_poll();
    }
    assert(writes == 1 && record.sd_init_failures == 10000 && record.nor_read_failures == 10000);
    now = OMI_BOOT_SAVE_INTERVAL_MS;
    omi_boot_telemetry_poll();
    assert(writes == 2);
    reboot(true);
    omi_boot_telemetry_sd_failure();
    omi_boot_telemetry_nor_failure();
    omi_boot_telemetry_open();
    assert(record.boot_count == 2 && record.sd_init_failures == 10001 && record.nor_read_failures == 10001);
    assert(record.flags & OMI_BOOT_SAFE);
    assert(record.safe_reason == 2);
    omi_boot_telemetry_upload_pending();
    unsigned uploaded = writes;
    omi_boot_telemetry_upload_pending();
    assert(writes == uploaded);
    struct omi_boot_record saved;
    assert(omi_boot_record_decode(&saved, disk, sizeof(disk)) && saved.upload_pending);
    reboot(false);
    omi_boot_telemetry_open();
    assert(record.pending_before_boot && !record.upload_pending && record.boot_count == 3);
    assert(record.outcome == OMI_UPDATE_NOT_INSTALLED);
    assert(record.current.header_version[2] == 23 && record.current.header_version[4] == 0x78);
    assert(record.current.header_version[7] == 0x12 && header_reads == 3);
    record.sd_init_failures = record.nor_read_failures = UINT32_MAX;
    omi_boot_telemetry_sd_failure();
    omi_boot_telemetry_nor_failure();
    assert(record.sd_init_failures == UINT32_MAX && record.nor_read_failures == UINT32_MAX);
    omi_boot_telemetry_sd_failure();
    dirty = true;
    save_error = -5;
    now = OMI_BOOT_SAVE_INTERVAL_MS;
    omi_boot_telemetry_poll();
    unsigned failed = writes;
    for (unsigned i = 0; i < 10000; ++i)
        omi_boot_telemetry_poll();
    assert(writes == failed && dirty);
    now += OMI_BOOT_SAVE_INTERVAL_MS;
    save_error = 0;
    omi_boot_telemetry_poll();
    assert(writes == failed + 1 && !dirty);
    reboot(false);
    load_error = -5;
    unsigned before = writes;
    omi_boot_telemetry_open();
    assert(writes == before && !writable);
    omi_boot_telemetry_poll();
    omi_boot_telemetry_open();
    assert(writes == before);
    load_error = 0;
    disk[0] = 9;
    reboot(false);
    omi_boot_telemetry_open();
    assert(record.boot_count == 1 && writable && writes == before + 1);
    assert(omi_boot_record_decode(&saved, disk, sizeof(disk)));
    memcpy(saved.current.fw, "3.0.22", 7);
    saved.last_fatal = 1;
    omi_boot_record_encode(disk, &saved);
    reboot(false);
    omi_boot_telemetry_open();
    assert(record.outcome == OMI_UPDATE_UPDATED && !strcmp(record.previous.fw, "3.0.22"));
    assert(!strcmp(record.current.fw, "3.0.23") && record.last_fatal == 1);
    reboot(false);
    omi_boot_telemetry_open();
    assert(record.outcome == OMI_UPDATE_UNCHANGED && record.last_fatal == 1);
    header_error = -5;
    reboot(false);
    omi_boot_telemetry_open();
    assert(!(record.flags & OMI_BOOT_HEADER_VALID) && record.outcome == OMI_UPDATE_UNKNOWN);
    puts("boot telemetry: codec, outcomes, persistence, saturation and throttling passed");
}
