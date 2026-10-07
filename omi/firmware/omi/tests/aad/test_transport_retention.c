#define SD_SEM_TAKE_EXTERNAL
#define main sd_tests_main
#include "test_sd_retention.c"
#undef main
#include "lib/core/features.h"

#define CODEC_OUTPUT_MAX_BYTES 160U
#define NETWORK_RING_BUF_SIZE 32U
#define MINIMAL_PACKET_SIZE 100U
#define BT_GATT_CCC_NOTIFY 1
#undef IS_ENABLED
#ifdef CONFIG_OMI_ENABLE_CONNECTED_RETENTION
#define IS_ENABLED(v) 1
#else
#define IS_ENABLED(v) 0
#endif

struct bt_conn {
    int references;
};
struct bt_gatt_attr {
    int unused;
};
struct bt_gatt_notify_params {
    const struct bt_gatt_attr *attr;
    const void *data;
    uint16_t len;
    void (*func)(struct bt_conn *, void *);
    void *user_data;
};
static struct bt_gatt_attr attrs[4];
static struct {
    struct bt_gatt_attr *attrs;
} audio_service = {attrs};
static struct bt_conn link;
static struct bt_conn *current_connection = &link;
static uint16_t current_mtu = 100;
static atomic_t pusher_stop_flag;
static struct k_sem audio_tx_sem = {1};
static bool subscribed = true, live = true, quiet;
static uint16_t sent_ids[32];
static unsigned sent_count;
static bool tx_stalled;

static struct bt_conn *bt_conn_ref(struct bt_conn *conn)
{
    ++conn->references;
    return conn;
}
static void bt_conn_unref(struct bt_conn *conn)
{
    --conn->references;
}
static bool bt_gatt_is_subscribed(struct bt_conn *conn, const struct bt_gatt_attr *attr, int ccc)
{
    (void) conn;
    (void) attr;
    (void) ccc;
    return subscribed;
}
static int bt_gatt_notify_cb(struct bt_conn *conn, const struct bt_gatt_notify_params *params)
{
    const uint8_t *data = params->data;
    sent_ids[sent_count++] = data[0] | ((uint16_t) data[1] << 8);
    params->func(conn, params->user_data);
    return 0;
}
static uint32_t capture_boot_id = 42;
static struct bt_conn *audio_connection_ref(void)
{
    return current_connection ? bt_conn_ref(current_connection) : NULL;
}
static bool transport_audio_live_mode(void)
{
    return live;
}
static bool mic_in_aad_sleep(void)
{
    return quiet;
}
uint64_t rtc_get_utc_time_ms(void)
{
    return 1800000000000ULL + (uint64_t) test_now;
}

struct ring_buf {
    uint8_t *data;
    size_t capacity, read, write;
};
static void ring_buf_init(struct ring_buf *r, size_t capacity, uint8_t *data)
{
    r->data = data;
    r->capacity = capacity;
}
static size_t ring_buf_put(struct ring_buf *r, const uint8_t *data, size_t size)
{
    if (r->write - r->read + size > r->capacity)
        return 0;
    for (size_t i = 0; i < size; ++i)
        r->data[(r->write + i) % r->capacity] = data[i];
    r->write += size;
    return size;
}
static size_t ring_buf_get(struct ring_buf *r, uint8_t *data, size_t size)
{
    if (r->write - r->read < size)
        return 0;
    for (size_t i = 0; i < size; ++i)
        data[i] = r->data[(r->read + i) % r->capacity];
    r->read += size;
    return size;
}

/* Include fresh, unedited slices of production transport.c. Zephyr's large
 * GATT registration surface stays outside this bounded host seam. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-variable"
#include "transport_pusher.inc"
#pragma GCC diagnostic pop

int k_sem_take(struct k_sem *s, int64_t timeout)
{
    (void) timeout;
    if (s == &tx_queue_sem && s->count == 0) {
        atomic_set(&pusher_stop_flag, 1); /* deterministic stop after drain */
        return 0;
    }
    if (s == &audio_tx_sem && tx_stalled)
        return -EAGAIN;
    if (!s->count)
        return -EAGAIN;
    --s->count;
    return 0;
}
static void sys_put_le32(uint32_t v, uint8_t *out)
{
    out[0] = v;
    out[1] = v >> 8;
    out[2] = v >> 16;
    out[3] = v >> 24;
}
static ssize_t bt_gatt_attr_read(struct bt_conn *conn,
                                 const struct bt_gatt_attr *attr,
                                 void *out,
                                 uint16_t len,
                                 uint16_t offset,
                                 const void *value,
                                 uint16_t value_len)
{
    (void) conn;
    (void) attr;
    if (offset >= value_len)
        return 0;
    size_t size = MIN(len, value_len - offset);
    memcpy(out, (const uint8_t *) value + offset, size);
    return (ssize_t) size;
}
#include "transport_features.inc"

static void run_frame(void)
{
    uint8_t audio[160];
    memset(audio, 77, sizeof(audio));
    atomic_clear(&pusher_stop_flag);
    assert(write_to_tx_queue(audio, sizeof(audio)));
    pusher();
    assert(link.references == 0);
}
static struct cq_frame read_frame(uint64_t seq)
{
    uint8_t record[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes, packets;
    struct cq_frame frame;
    assert(read_packets_internal(seq, record, sizeof(record), &bytes, &packets) == 0);
    assert(cq_unpack(record + 4, &frame));
    return frame;
}
int main(void)
{
    reboot();
    ring_buf_init(&ring_buf, sizeof(tx_queue), tx_queue);
    test_now = 0;
    uint8_t features[9];
    assert(features_read_handler(&link, attrs, features, sizeof(features), 0) == 9);
    assert(features[4] == cq_capability(IS_ENABLED(CONFIG_OMI_ENABLE_CONNECTED_RETENTION), sd_retention_ready()));
    assert((features[0] & OMI_FEATURE_OFFLINE_STORAGE) != 0);
    assert(features[5] == 42 && features[6] == 0 && features[7] == 0 && features[8] == 0);
    sd_write_paused = true;
    assert(features_read_handler(&link, attrs, features, sizeof(features), 0) == 9);
    assert(features[4] == 0);
    sd_write_paused = false;
    if (!IS_ENABLED(CONFIG_OMI_ENABLE_CONNECTED_RETENTION)) {
        puts("Connected retention: production features byte zero when disabled passed");
        return 0;
    }
    run_frame(); /* live + subscribed: durable before BLE */
    assert(sent_count == 2 && sent_ids[0] == 0 && sent_ids[1] == 1);
    struct cq_frame first = read_frame(0);
    assert(first.sequence == 0 && first.first_fragment == 0 && first.fragments == 2);
    subscribed = false;
    run_frame(); /* phone pause */
    assert(sent_count == 2);
    struct cq_frame gap = read_frame(1);
    assert(gap.sequence == 1 && gap.first_fragment == 2 && gap.fragments == 2);
    assert(gap.captured_ms > first.captured_ms);
    subscribed = true;
    run_frame();
    assert(sent_count == 4 && sent_ids[2] == 4 && sent_ids[3] == 5);
    struct cq_frame resumed = read_frame(2);
    assert(resumed.sequence == 2 && resumed.first_fragment == 4);
    tx_stalled = true;
    run_frame(); /* CCC still set, no TX slots: survives in SD */
    assert(sent_count == 4 && read_frame(3).first_fragment == 6);
    tx_stalled = false;
    quiet = true;
    run_frame(); /* residual queued frame when AAD enters quiet */
    assert(sent_count == 4 && read_frame(4).first_fragment == 8);
    quiet = false;
    packet_next_index = 65535;
    run_frame();
    assert(sent_ids[4] == 65535 && sent_ids[5] == 0);
    assert(read_frame(5).first_fragment == 65535);
    reboot();
    assert(read_frame(1).first_fragment == 2); /* retained gap durable after reset */
    /* Batch subscription keeps its existing path: successful sends do not
     * mirror to SD; CCC-off packs multiple frames in legacy 440-byte records. */
    uint64_t batch_start = ring_state.write_seq;
    unsigned sent_before_batch = sent_count;
    live = false;
    run_frame();
    assert(sent_count == sent_before_batch + 2 && ring_state.write_seq == batch_start);
    subscribed = false;
    run_frame();
    run_frame();
    run_frame();
    assert(flush_current_batch(true) == 0);
    assert(ring_state.write_seq == batch_start + 1);
    uint8_t legacy_record[RAW_AUDIO_PACKET_BYTES];
    uint32_t bytes, packets;
    assert(read_packets_internal(batch_start, legacy_record, sizeof(legacy_record), &bytes, &packets) == 0);
    struct cq_frame legacy_frame;
    assert(!cq_unpack(legacy_record + RAW_AUDIO_TIMESTAMP_BYTES, &legacy_frame));
    assert(legacy_record[4] == 160 && legacy_record[4 + 161] == 160);
    puts("Connected retention: production pusher unsubscribe/stall/quiet, batch matrix, fragment continuity/wrap, "
         "timestamps and "
         "features read passed");
    return 0;
}
