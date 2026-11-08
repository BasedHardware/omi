#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CONFIG_OMI_ENABLE_OFFLINE_STORAGE 1
#define CONFIG_LOG_DEFAULT_LEVEL 0
#define CONFIG_BT_L2CAP_TX_MTU 247

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include "sd_card.h"
#include "transport.h"

int64_t z_stub_now_ms;

static int failures;
#define CHECK(cond)                                                                                                    \
    do {                                                                                                               \
        if (!(cond)) {                                                                                                 \
            printf("FAIL %d: %s\n", __LINE__, #cond);                                                                  \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

static struct bt_conn z_conn_a = {.id = 1, .mtu = 64};
static struct bt_conn z_conn_b = {.id = 2, .mtu = 64};
static struct bt_conn z_conn_c = {.id = 3, .mtu = 64};
static struct bt_conn *z_conn;

#define Z_MAX_NOTIFIES 1024
static struct {
    struct bt_conn *conn;
    uint16_t len;
    uint8_t data[64];
} z_notifies[Z_MAX_NOTIFIES];
static int z_notify_count;
static int z_notify_err;

struct bt_conn *bt_conn_ref(struct bt_conn *conn)
{
    conn->refs++;
    return conn;
}
void bt_conn_unref(struct bt_conn *conn)
{
    conn->refs--;
}
int bt_conn_get_info(struct bt_conn *conn, struct bt_conn_info *info)
{
    memset(info, 0, sizeof(*info));
    return 0;
}
int bt_conn_disconnect(struct bt_conn *conn, uint8_t reason)
{
    return 0;
}

static void z_record_notify(struct bt_conn *conn, const void *data, uint16_t len)
{
    if (z_notify_count < Z_MAX_NOTIFIES) {
        z_notifies[z_notify_count].conn = conn;
        z_notifies[z_notify_count].len = len;
        memcpy(z_notifies[z_notify_count].data, data, len < 64 ? len : 64);
    }
    z_notify_count++;
}

bool bt_gatt_is_subscribed(struct bt_conn *conn, const struct bt_gatt_attr *attr, uint16_t ccc_value)
{
    return conn && conn->subscribed;
}
int bt_gatt_notify(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *data, uint16_t len)
{
    if (z_notify_err) {
        return z_notify_err;
    }
    z_record_notify(conn, data, len);
    return 0;
}
int bt_gatt_notify_cb(struct bt_conn *conn, struct bt_gatt_notify_params *params)
{
    if (z_notify_err) {
        return z_notify_err;
    }
    z_record_notify(conn, params->data, params->len);
    if (params->func) {
        params->func(conn, params->user_data);
    }
    return 0;
}
uint16_t bt_gatt_get_mtu(struct bt_conn *conn)
{
    return conn ? conn->mtu : 0;
}
ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                          const struct bt_gatt_attr *attr,
                          void *buf,
                          uint16_t buf_len,
                          uint16_t offset,
                          const void *value,
                          size_t value_len)
{
    size_t n = value_len;
    if (offset >= value_len) {
        return 0;
    }
    n -= offset;
    if (n > buf_len) {
        n = buf_len;
    }
    memcpy(buf, (const uint8_t *) value + offset, n);
    return n;
}

struct bt_conn *get_current_connection(void)
{
    return z_conn;
}
struct bt_conn *get_current_connection_ref(void)
{
    return z_conn ? bt_conn_ref(z_conn) : NULL;
}
int transport_bulk_tx_acquire(k_timeout_t timeout)
{
    return 0;
}
void transport_bulk_tx_release(void) {}

static sd_ring_info_t z_sd;
static bool z_sd_ready;
static int z_advance_calls;
static int z_clear_calls;
static void (*z_on_sd_read)(void);
static uint64_t z_read_calls;

bool sd_is_ready(void)
{
    return z_sd_ready;
}
int sd_ring_get_info(sd_ring_info_t *info)
{
    *info = z_sd;
    return 0;
}
int sd_ring_read(uint64_t start_seq, uint8_t *buf, uint32_t max_bytes, uint32_t *bytes_read, uint32_t *packets_read)
{
    z_read_calls++;
    if (z_on_sd_read) {
        void (*hook)(void) = z_on_sd_read;
        z_on_sd_read = NULL;
        hook();
    }
    uint32_t n = max_bytes / RAW_AUDIO_PACKET_BYTES;
    if (start_seq + n > z_sd.write_seq) {
        n = (uint32_t) (z_sd.write_seq - start_seq);
    }
    memset(buf, 0xA5, n * RAW_AUDIO_PACKET_BYTES);
    *bytes_read = n * RAW_AUDIO_PACKET_BYTES;
    *packets_read = n;
    return 0;
}
int sd_ring_advance(uint64_t new_read_seq)
{
    z_advance_calls++;
    if (new_read_seq > z_sd.write_seq) {
        return -ERANGE;
    }
    z_sd.read_seq = new_read_seq;
    return 0;
}
int sd_ring_advance_id(uint64_t ring_id, uint64_t new_read_seq)
{
    if (ring_id != z_sd.ring_id) {
        return -ESTALE;
    }
    return sd_ring_advance(new_read_seq);
}
int sd_ring_clear(void)
{
    z_clear_calls++;
    z_sd.read_seq = 0;
    z_sd.write_seq = 0;
    z_sd.ring_id = 0xCAFEULL;
    return 0;
}
bool rtc_is_valid(void)
{
    return false;
}

#include "../src/lib/core/storage.c"

static void z_connect(struct bt_conn *c)
{
    z_conn = c;
    c->subscribed = true;
    storage_connection_changed();
}
static void z_disconnect(void)
{
    z_conn = NULL;
    storage_connection_changed();
}
static int z_find_notify(uint8_t opcode, struct bt_conn *conn, int from)
{
    for (int i = from; i < z_notify_count && i < Z_MAX_NOTIFIES; i++) {
        if (z_notifies[i].conn == conn && z_notifies[i].data[0] == opcode) {
            return i;
        }
    }
    return -1;
}
static void z_send_cmd(struct bt_conn *c, const uint8_t *cmd, uint16_t len)
{
    storage_write_handler(c, NULL, cmd, len, 0, 0);
}
static void z_run(int iters)
{
    for (int i = 0; i < iters; i++) {
        storage_iteration();
    }
}
static void z_reset_all(void)
{
    memset(&z_conn_a, 0, sizeof(z_conn_a));
    memset(&z_conn_b, 0, sizeof(z_conn_b));
    memset(&z_conn_c, 0, sizeof(z_conn_c));
    z_conn_a.id = 1;
    z_conn_b.id = 2;
    z_conn_c.id = 3;
    z_conn_a.mtu = z_conn_b.mtu = z_conn_c.mtu = 64;
    z_conn = NULL;
    z_notify_count = 0;
    z_notify_err = 0;
    z_advance_calls = 0;
    z_clear_calls = 0;
    z_on_sd_read = NULL;
    z_read_calls = 0;
    z_sd.read_seq = 0;
    z_sd.dropped_packets = 0;
    z_sd.write_seq = 40;
    z_sd.capacity_packets = 288;
    z_sd.ring_id = 0x1122;
    z_sd_ready = true;
    custody_epoch = custody_granted_caps = custody_live_token = 0;
    worker_seen_epoch = 0;
    cached_ring_id = 0;
    info_requested = 0;
    read_request_pending = 0;
    atomic_set(&stop_requested, 0);
    reset_transfer_state();
    info_deadline = read_deadline = 0;
    storage_cmd_msgq.head = storage_cmd_msgq.used = 0;
    live_mark_msgq.head = live_mark_msgq.used = 0;
}

static void test_epoch_command_survival(void)
{
    z_reset_all();
    z_connect(&z_conn_a);
    uint8_t info_cmd = 0x10;
    z_send_cmd(&z_conn_a, &info_cmd, 1);
    z_disconnect();
    z_connect(&z_conn_b);
    z_send_cmd(&z_conn_b, &info_cmd, 1);
    z_run(1);
    int idx = z_find_notify(0x02, &z_conn_b, 0);
    CHECK(idx >= 0);
    CHECK(z_notifies[idx].len == 41);
    CHECK(z_notifies[idx].data[31] == 0x0F);
    CHECK(z_notifies[idx].data[32] == 1);
    CHECK(sys_get_be64(z_notifies[idx].data + 1) == z_sd.read_seq);
    CHECK(sys_get_be64(z_notifies[idx].data + 9) == z_sd.write_seq);
    CHECK(sys_get_be32(z_notifies[idx].data + 17) == z_sd.capacity_packets);
    CHECK(sys_get_be64(z_notifies[idx].data + 21) == z_sd.dropped_packets);
    CHECK(sys_get_be16(z_notifies[idx].data + 29) == RAW_AUDIO_PACKET_BYTES);
    CHECK(sys_get_be64(z_notifies[idx].data + 33) == z_sd.ring_id);
    CHECK(z_find_notify(0x02, &z_conn_a, 0) < 0);
    CHECK(z_sd.ring_id == 0x1122 && z_notifies[idx].data[40] == 0x22);
    printf("epoch_cmd_survival ok\n");
}

static void test_stale_enable_no_caps(void)
{
    z_reset_all();
    z_connect(&z_conn_a);
    uint8_t en[3] = {0x14, 1, 0x02};
    z_send_cmd(&z_conn_a, en, 3);
    z_disconnect();
    z_connect(&z_conn_b);
    z_run(1);
    CHECK(storage_live_session() == 0);
    CHECK((atomic_get(&custody_granted_caps) & 0x02) == 0);
    CHECK(z_find_notify(0x01, &z_conn_b, 0) < 0);
    printf("stale_enable ok\n");
}

static void test_enable_ack_layouts(void)
{
    z_reset_all();
    z_connect(&z_conn_b);
    uint8_t en[3] = {0x14, 1, 0x02};
    z_send_cmd(&z_conn_b, en, 3);
    z_run(1);
    int i = z_find_notify(0x01, &z_conn_b, 0);
    CHECK(i >= 0 && z_notifies[i].len == 3);
    CHECK(z_notifies[i].data[1] == 0 && z_notifies[i].data[2] == 0x02);
    uint32_t tok1 = storage_live_session();
    CHECK(tok1 != 0);

    en[1] = 2;
    z_send_cmd(&z_conn_b, en, 3);
    z_run(1);
    i = z_find_notify(0x01, &z_conn_b, i + 1);
    CHECK(i >= 0 && z_notifies[i].data[1] == 6);
    CHECK(storage_live_session() == tok1);

    z_send_cmd(&z_conn_b, en, 2);
    z_run(1);
    i = z_find_notify(0x01, &z_conn_b, i + 1);
    CHECK(i >= 0 && z_notifies[i].data[1] == 6);

    storage_queue_live_mark(z_sd.ring_id, 5, 9, tok1);
    en[1] = 1;
    z_send_cmd(&z_conn_b, en, 3);
    z_run(1);
    uint32_t tok2 = storage_live_session();
    CHECK(tok2 != 0 && tok2 != tok1);
    CHECK(z_find_notify(0x06, &z_conn_b, 0) < 0);

    storage_queue_live_mark(z_sd.ring_id, 5, 9, tok2);
    storage_queue_live_mark(0x9999, 5, 9, tok2);
    z_run(1);
    i = z_find_notify(0x06, &z_conn_b, 0);
    CHECK(i >= 0 && z_notifies[i].len == 19);
    CHECK(z_notifies[i].data[7] == 0x11 && z_notifies[i].data[8] == 0x22);
    CHECK(z_find_notify(0x06, &z_conn_b, i + 1) < 0);
    printf("enable_acks ok\n");
}

static void test_info_mtu_gate(void)
{
    z_reset_all();
    z_conn_b.mtu = 23;
    z_connect(&z_conn_b);
    uint8_t info_cmd = 0x10;
    z_send_cmd(&z_conn_b, &info_cmd, 1);
    z_run(2);
    CHECK(z_find_notify(0x02, &z_conn_b, 0) < 0);
    CHECK(z_find_notify(0x01, &z_conn_b, 0) < 0);
    z_conn_b.mtu = 64;
    z_run(1);
    int i = z_find_notify(0x02, &z_conn_b, 0);
    CHECK(i >= 0 && z_notifies[i].len == 41);
    printf("info_mtu ok\n");
}

static void test_info_mtu_timeout(void)
{
    z_reset_all();
    z_conn_b.mtu = 23;
    z_connect(&z_conn_b);
    uint8_t info_cmd = 0x10;
    z_send_cmd(&z_conn_b, &info_cmd, 1);
    z_run(1);
    z_stub_now_ms += 6000;
    z_run(1);
    int i = z_find_notify(0x01, &z_conn_b, 0);
    CHECK(i >= 0 && z_notifies[i].data[1] == 9);
    CHECK(z_find_notify(0x02, &z_conn_b, 0) < 0);
    printf("info_mtu_timeout ok\n");
}

static void test_read_advance_done(void)
{
    z_reset_all();
    z_sd.write_seq = 4;
    z_connect(&z_conn_b);
    uint8_t rd[9] = {0x11};
    sys_put_be64(0, rd + 1);
    z_send_cmd(&z_conn_b, rd, sizeof(rd));
    z_run(1);
    CHECK(transfer_active);
    CHECK(z_find_notify(0x05, &z_conn_b, 0) >= 0);
    CHECK(z_find_notify(0x03, &z_conn_b, 0) >= 0);

    z_send_cmd(&z_conn_b, rd, sizeof(rd));
    uint8_t adv[9] = {0x12};
    sys_put_be64(2, adv + 1);
    z_send_cmd(&z_conn_b, adv, sizeof(adv));
    z_run(1);
    CHECK(z_advance_calls == 1 && z_sd.read_seq == 2);
    int ack9 = -1;
    for (int i = 0; i < z_notify_count; i++) {
        if (z_notifies[i].conn == &z_conn_b && z_notifies[i].data[0] == 0x01 && z_notifies[i].data[1] == 9) {
            ack9 = i;
        }
    }
    CHECK(ack9 >= 0);

    z_run(4);
    CHECK(!transfer_active);
    int done = z_find_notify(0x04, &z_conn_b, 0);
    CHECK(done >= 0 && z_notifies[done].len == 10);
    CHECK(z_sd.read_seq == 2);
    printf("read_advance_done ok\n");
}

static void test_disconnect_mid_read(void)
{
    z_reset_all();
    z_sd.write_seq = 40;
    z_connect(&z_conn_a);
    uint8_t rd[9] = {0x11};
    sys_put_be64(0, rd + 1);
    z_send_cmd(&z_conn_a, rd, sizeof(rd));
    z_run(1);
    CHECK(transfer_active);

    z_on_sd_read = z_disconnect;
    z_run(1);
    CHECK(!transfer_active);
    CHECK(z_find_notify(0x04, &z_conn_a, 0) < 0);

    z_connect(&z_conn_b);
    uint8_t info_cmd = 0x10;
    z_send_cmd(&z_conn_b, &info_cmd, 1);
    z_run(1);
    CHECK(z_find_notify(0x02, &z_conn_b, 0) >= 0);
    CHECK(z_find_notify(0x02, &z_conn_a, 0) < 0);
    printf("disconnect_mid_read ok\n");
}

static void test_clear_terminates_read(void)
{
    z_reset_all();
    z_sd.write_seq = 40;
    z_connect(&z_conn_b);
    uint8_t rd[9] = {0x11};
    sys_put_be64(0, rd + 1);
    z_send_cmd(&z_conn_b, rd, sizeof(rd));
    z_run(1);
    CHECK(transfer_active);

    uint8_t clr[4] = {0x13, 0xAA, 0xBB, 0xCC};
    z_send_cmd(&z_conn_b, clr, sizeof(clr));
    z_run(1);
    CHECK(z_clear_calls == 1);
    CHECK(!transfer_active);
    int ack = z_find_notify(0x01, &z_conn_b, 0);
    CHECK(ack >= 0 && z_notifies[ack].data[1] == 0);
    printf("clear_read ok\n");
}

int main(void)
{
    test_epoch_command_survival();
    test_stale_enable_no_caps();
    test_enable_ack_layouts();
    test_info_mtu_gate();
    test_info_mtu_timeout();
    test_read_advance_done();
    test_disconnect_mid_read();
    test_clear_terminates_read();
    printf("storage harness: %d failures\n", failures);
    return failures ? 1 : 0;
}
