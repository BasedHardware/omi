#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CONFIG_OMI_ENABLE_OFFLINE_STORAGE 1
#define CONFIG_SDMMC_VOLUME_NAME "SD:"
#define CONFIG_LOG_DEFAULT_LEVEL 0
#define CONFIG_LOG 1
#define CONFIG_BT_L2CAP_TX_MTU 247

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/pm/device.h>
#include <zephyr/storage/disk_access.h>

#define FAKE_SECTORS (64 + 8 * 32)
static uint8_t fake_disk[FAKE_SECTORS][512];
int64_t z_stub_now_ms;
static uint64_t saved_epoch;

uint64_t app_settings_get_rtc_epoch(void)
{
    return saved_epoch;
}

int app_settings_save_rtc_epoch(uint64_t epoch)
{
    saved_epoch = epoch;
    return 0;
}

int disk_access_read(const char *drive, uint8_t *buf, uint32_t start, uint32_t count)
{
    (void) drive;
    assert(start + count <= FAKE_SECTORS);
    memcpy(buf, fake_disk[start], count * 512);
    return 0;
}

int disk_access_write(const char *drive, const uint8_t *buf, uint32_t start, uint32_t count)
{
    (void) drive;
    assert(start + count <= FAKE_SECTORS);
    memcpy(fake_disk[start], buf, count * 512);
    return 0;
}

int disk_access_ioctl(const char *drive, uint8_t cmd, void *buf)
{
    (void) drive;
    if (cmd == DISK_IOCTL_GET_SECTOR_COUNT) {
        *(uint32_t *) buf = FAKE_SECTORS;
    } else if (cmd == DISK_IOCTL_GET_SECTOR_SIZE) {
        *(uint32_t *) buf = 512;
    }
    return 0;
}

struct device z_stub_dev_sdhc0 = {"sdhc0"};
struct device z_stub_dev_gpio1 = {"gpio1"};
struct device z_stub_dev_spi3 = {"spi3"};
struct device z_stub_dev_sdcard_en_pin = {"sd_en"};

int gpio_pin_configure(const struct device *dev, uint32_t pin, uint32_t flags)
{
    (void) dev;
    (void) pin;
    (void) flags;
    return 0;
}

int gpio_pin_configure_dt(const struct gpio_dt_spec *spec, uint32_t flags)
{
    (void) spec;
    (void) flags;
    return 0;
}

int gpio_pin_set_dt(const struct gpio_dt_spec *spec, int value)
{
    (void) spec;
    (void) value;
    return 0;
}

int gpio_pin_set_raw(const struct device *dev, uint32_t pin, int value)
{
    (void) dev;
    (void) pin;
    (void) value;
    return 0;
}

int pm_device_action_run(const struct device *dev, enum pm_device_action action)
{
    (void) dev;
    (void) action;
    return 0;
}

struct bt_conn *get_current_connection(void)
{
    return NULL;
}

int transport_bulk_tx_acquire(k_timeout_t timeout)
{
    (void) timeout;
    return 0;
}

void transport_bulk_tx_release(void) {}

int bt_gatt_notify_cb(struct bt_conn *conn, struct bt_gatt_notify_params *params)
{
    if (params->func) {
        params->func(conn, params->user_data);
    }
    return 0;
}

int bt_gatt_notify(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *data, uint16_t len)
{
    (void) conn;
    (void) attr;
    (void) data;
    (void) len;
    return 0;
}

uint16_t bt_gatt_get_mtu(struct bt_conn *conn)
{
    (void) conn;
    return 247;
}

ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                          const struct bt_gatt_attr *attr,
                          void *buf,
                          uint16_t len,
                          uint16_t offset,
                          const void *value,
                          size_t value_len)
{
    (void) conn;
    (void) attr;
    if (offset >= value_len) {
        return 0;
    }
    size_t n = value_len - offset < len ? value_len - offset : len;
    memcpy(buf, (const uint8_t *) value + offset, n);
    return n;
}

/* Compile the real clock and SD writer together, rather than mirroring either
 * implementation. Only settings, scheduling and the physical disk are faked. */
#include "../../src/lib/core/storage.c"
#include "../../src/rtc.c"
#include "../../src/sd_card.c"

static void assert_status(uint32_t expected_trust)
{
    uint32_t status[4];
    assert(storage_read_characteristic(NULL, NULL, status, sizeof(status), 0) == sizeof(status));
    assert(status[3] == expected_trust);
}

static uint32_t write_record(uint8_t value)
{
    sd_req_t req = {.type = REQ_WRITE_DATA};
    req.u.write.len = MAX_WRITE_SIZE;
    memset(req.u.write.buf, value, sizeof(req.u.write.buf));
    uint32_t before = current_batch_packets;
    process_write_data_req(&req);
    assert(current_batch_packets == before + 1);
    uint8_t *record = current_batch + RAW_BATCH_HEADER_BYTES + before * RAW_AUDIO_PACKET_BYTES;
    assert(memcmp(record + RAW_AUDIO_TIMESTAMP_BYTES, req.u.write.buf, MAX_WRITE_SIZE) == 0);
    return sys_get_be32(record);
}

static void test_restore_and_capture(void)
{
    saved_epoch = 0;
    z_stub_now_ms = 0;
    init_rtc();
    assert(sd_mount() == 0);
    assert(!rtc_is_valid() && !rtc_is_trusted());
    storage_status_cache_set(&ring_state);
    assert_status(0);
    assert(write_record(1) == RTC_TIMESTAMP_UPTIME_FLAG);

    /* Reboot after days powered off: settings still contain the old epoch. */
    saved_epoch = 1800000000;
    z_stub_now_ms = 12000;
    init_rtc();
    assert(rtc_is_valid() && !rtc_is_trusted());
    assert_status(0);
    z_stub_now_ms += 65000;
    assert(get_utc_time() == saved_epoch + 65); /* diagnostic clock survives */
    assert(write_record(2) == (RTC_TIMESTAMP_UPTIME_FLAG | 77));
    assert(saved_epoch == 1800000000);
    assert(strcmp(compat_current_name, "00000000.txt") == 0);

    /* The IMU boot adjustment must not establish trust either. */
    assert(rtc_restore_utc_time_ms(1800000123456ULL) == 0);
    assert(rtc_is_valid() && !rtc_is_trusted());
    assert_status(0);
    assert(write_record(3) == (RTC_TIMESTAMP_UPTIME_FLAG | 77));

    /* Phone sync changes future records only, including in the same batch. */
    assert(rtc_set_utc_time(1800200000) == 0);
    assert(rtc_is_valid() && rtc_is_trusted());
    assert_status(1); /* no status-cache refresh after sync */
    assert(write_record(4) == 1800200000);
    z_stub_now_ms += 2100;
    assert(write_record(5) == 1800200002);
    assert(rtc_persist_work.pending);
    rtc_persist_work.handler(&rtc_persist_work);
    assert(saved_epoch == 1800200000);

    /* Even a bad phone clock cannot prevent recording. */
    assert(rtc_set_utc_time(1) == 0);
    assert(write_record(6) == (RTC_TIMESTAMP_UPTIME_FLAG | 79));
    assert(rtc_set_utc_time(0x80000000ULL) == 0);
    assert(write_record(7) == (RTC_TIMESTAMP_UPTIME_FLAG | 79));
    assert(rtc_set_utc_time(RTC_MIN_VALID_EPOCH) == 0);
    assert(write_record(8) == RTC_MIN_VALID_EPOCH);
    assert(rtc_set_utc_time(0x7FFFFFFFULL) == 0);
    assert(write_record(9) == 0x7FFFFFFFU);
    z_stub_now_ms += 1000;
    assert(write_record(10) == (RTC_TIMESTAMP_UPTIME_FLAG | 80));
    assert(rtc_set_utc_time(0) == -EINVAL);
    assert(rtc_restore_utc_time_ms(0) == -EINVAL);

    /* Persist and decode every payload, including records captured before sync. */
    assert(flush_current_batch(true) == 0);
    assert(ring_state.write_seq == 10 && ring_state.dropped_packets == 0);
    struct raw_batch_header header;
    assert(load_batch_for_seq(0, batch_read_buffer, &header) == 0);
    assert(header.packet_count == 10);
    const uint32_t expected[] = {RTC_TIMESTAMP_UPTIME_FLAG,
                                 RTC_TIMESTAMP_UPTIME_FLAG | 77,
                                 RTC_TIMESTAMP_UPTIME_FLAG | 77,
                                 1800200000,
                                 1800200002,
                                 RTC_TIMESTAMP_UPTIME_FLAG | 79,
                                 RTC_TIMESTAMP_UPTIME_FLAG | 79,
                                 RTC_MIN_VALID_EPOCH,
                                 0x7FFFFFFF,
                                 RTC_TIMESTAMP_UPTIME_FLAG | 80};
    for (unsigned i = 0; i < 10; i++) {
        uint8_t *record = batch_read_buffer + RAW_BATCH_HEADER_BYTES + i * RAW_AUDIO_PACKET_BYTES;
        assert(sys_get_be32(record) == expected[i]);
        for (unsigned j = 0; j < MAX_WRITE_SIZE; j++) {
            assert(record[RAW_AUDIO_TIMESTAMP_BYTES + j] == i + 1);
        }
    }
    /* A second boot revokes phone trust; the persisted epoch remains available. */
    init_rtc();
    assert(rtc_is_valid() && !rtc_is_trusted());
    assert_status(0); /* no stale trusted status after another boot */
    assert(get_utc_time() == saved_epoch);
    assert((rtc_get_record_timestamp() & RTC_TIMESTAMP_UPTIME_FLAG) != 0);
    puts("restore, IMU adjustment, phone sync, invalid clocks: all 10 records retained");
}

static void *change_clock(void *arg)
{
    (void) arg;
    for (unsigned i = 0; i < 20000; i++) {
        assert(rtc_restore_utc_time_ms(1800000000000ULL) == 0);
        assert(rtc_set_utc_time(1800200000) == 0);
    }
    return NULL;
}

static void test_atomic_trust_snapshot(void)
{
    pthread_t writer;
    assert(rtc_set_utc_time(1800200000) == 0);
    assert(pthread_create(&writer, NULL, change_clock, NULL) == 0);
    for (unsigned i = 0; i < 50000; i++) {
        uint32_t ts = rtc_get_record_timestamp();
        assert(ts == 1800200000 || ts == (RTC_TIMESTAMP_UPTIME_FLAG | 80));
    }
    assert(pthread_join(writer, NULL) == 0);
    puts("concurrent restore/sync: no restored epoch labeled trusted");
}

int main(void)
{
    test_restore_and_capture();
    test_atomic_trust_snapshot();
    return 0;
}
