#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>
#include <zephyr/sys/atomic.h> // Include for atomic operations
#include <stdint.h>
#include <zephyr/timing/timing.h> // Include for timing

LOG_MODULE_REGISTER(transport_ble_test, CONFIG_LOG_DEFAULT_LEVEL);

#define TEST_PACKET_SIZE 50
#define WRITE_INTERVAL_MS 10
#define TEST_RING_BUF_SIZE (TEST_PACKET_SIZE * 150) // Store 100 packets
#define WRITER_STACK_SIZE 1024*10
#define READER_STACK_SIZE 2048*10
#define WRITER_PRIORITY K_PRIO_PREEMPT(7)
#define READER_PRIORITY K_PRIO_PREEMPT(6)

// --- Test-specific Globals ---
static struct ring_buf test_ring_buf;
static uint8_t test_tx_queue[TEST_RING_BUF_SIZE];
static struct bt_conn *test_conn = NULL;
static volatile bool test_subscribed = false;
static atomic_t test_write_count = ATOMIC_INIT(0);
static atomic_t test_gatt_notify_count = ATOMIC_INIT(0);
static atomic_t test_write_failed_count = ATOMIC_INIT(0);
static atomic_t test_notify_failed_count = ATOMIC_INIT(0);

K_THREAD_STACK_DEFINE(writer_stack_area, WRITER_STACK_SIZE);
static struct k_thread writer_thread_data;

K_THREAD_STACK_DEFINE(reader_stack_area, READER_STACK_SIZE);
static struct k_thread reader_thread_data;

#define LOGGER_STACK_SIZE 1024
#define LOGGER_PRIORITY K_PRIO_PREEMPT(8) // Lower priority than reader/writer
K_THREAD_STACK_DEFINE(logger_stack_area, LOGGER_STACK_SIZE);
static struct k_thread logger_thread_data;


// --- Test-specific BLE Definitions ---

// Use the same UUIDs as transport.c for compatibility with clients
static struct bt_uuid_128 test_audio_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 test_audio_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10001, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));

static void test_audio_ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value)
{
    test_subscribed = (value == BT_GATT_CCC_NOTIFY);
    LOG_INF("Client %s", test_subscribed ? "subscribed" : "unsubscribed");
}

// Minimal GATT service definition for the test
static struct bt_gatt_attr test_audio_service_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&test_audio_service_uuid),
    BT_GATT_CHARACTERISTIC(&test_audio_characteristic_data_uuid.uuid, BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, NULL, NULL, NULL),
    BT_GATT_CCC(test_audio_ccc_cfg_changed, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service test_audio_service = BT_GATT_SERVICE(test_audio_service_attrs);

// Minimal Advertisement data
static const struct bt_data test_ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA(BT_DATA_UUID128_ALL, test_audio_service_uuid.val, sizeof(test_audio_service_uuid.val)),
    BT_DATA(BT_DATA_NAME_COMPLETE, "OMI-BLE-TEST", sizeof("OMI-BLE-TEST") - 1),
};

// --- Test-specific Connection Callbacks ---

static void test_connected(struct bt_conn *conn, uint8_t err)
{
    if (err) {
        LOG_ERR("Connection failed (err 0x%02x)", err);
        if (test_conn) {
             bt_conn_unref(test_conn);
             test_conn = NULL;
        }
        test_subscribed = false;
    } else {
        LOG_INF("Connected");
        test_conn = bt_conn_ref(conn);
        test_subscribed = false; // Require subscription after connection
    }
}

static void test_disconnected(struct bt_conn *conn, uint8_t reason)
{
    LOG_INF("Disconnected (reason 0x%02x)", reason);
    if (test_conn == conn) {
        bt_conn_unref(test_conn);
        test_conn = NULL;
        test_subscribed = false;
    }
}

static struct bt_conn_cb test_conn_callbacks = {
    .connected = test_connected,
    .disconnected = test_disconnected,
};

// --- Test Threads ---

static void writer_thread_entry(void *p1, void *p2, void *p3)
{
    uint8_t dummy_data[TEST_PACKET_SIZE];
    uint8_t counter = 0;

    // Fill with initial pattern
    for (int i = 0; i < TEST_PACKET_SIZE; i++) {
        dummy_data[i] = i;
    }

    LOG_INF("Writer thread started");

    while (1) {
        k_msleep(WRITE_INTERVAL_MS);

        // Modify data slightly each time
        dummy_data[0] = counter++;

        int written = ring_buf_put(&test_ring_buf, dummy_data, TEST_PACKET_SIZE);
        if (written != TEST_PACKET_SIZE) {
            // LOG_WRN("Ring buffer full, discarding data!");
            atomic_inc(&test_write_failed_count); // Increment write failed counter
            // Optional: Add a small sleep here if buffer is often full
        }
        else {
            atomic_inc(&test_write_count); // Increment write counter on success
        }
    }
}

static void reader_notifier_thread_entry(void *p1, void *p2, void *p3)
{
    uint8_t data_buffer[TEST_PACKET_SIZE];
    int err;

    LOG_INF("Reader/Notifier thread started");

    while (1) {
        // Wait until connected and subscribed
        while (!test_conn || !test_subscribed) {
            k_msleep(100); // Check periodically
        }

        // Read data from ring buffer
        int read = ring_buf_get(&test_ring_buf, data_buffer, TEST_PACKET_SIZE);

        if (read == TEST_PACKET_SIZE) {
            // Send notification
            err = bt_gatt_notify(test_conn, &test_audio_service.attrs[1], data_buffer, TEST_PACKET_SIZE);
            if (err == -EAGAIN || err == -ENOMEM) {
                // Queue is full, retry after a short delay
                LOG_WRN("bt_gatt_notify failed (%d), retrying...", err);
                // Put data back into ring buffer (might fail if buffer became full)
                if (ring_buf_put(&test_ring_buf, data_buffer, TEST_PACKET_SIZE) != TEST_PACKET_SIZE) {
                     LOG_ERR("Failed to put data back into ring buffer after notify failure!");
                }
                k_msleep(5); // Small delay before retrying
                continue; // Skip yield at the end, try again immediately
            } else if (err) {
                LOG_ERR("bt_gatt_notify failed unexpectedly (err %d)", err);
                atomic_inc(&test_notify_failed_count); // Increment notify failed counter
                // Consider what to do on other errors - maybe stop test?
                // For now, just log and continue trying.
            } else {
                 // LOG_DBG("Sent %d bytes", TEST_PACKET_SIZE);
                 atomic_inc(&test_gatt_notify_count); // Increment notify counter on success
            }
        } else if (read == 0) {
            // Buffer is empty, wait a bit
            k_msleep(5);
        } else {
             // Should not happen if writes are always TEST_PACKET_SIZE
             LOG_ERR("Ring buffer read unexpected size: %d", read);
        }

        // Yield to other threads
        k_yield();
    }
}
 
// --- Logger Thread ---

static void logger_thread_entry(void *p1, void *p2, void *p3)
{
    uint32_t last_write_count = 0;
    uint32_t last_notify_count = 0;
    uint32_t current_write_count;
    uint32_t current_notify_count;
    uint32_t write_rate;
    uint32_t notify_rate;
    uint32_t last_write_failed_count = 0;
    uint32_t last_notify_failed_count = 0;
    uint32_t current_write_failed_count;
    uint32_t current_notify_failed_count;
    uint32_t write_failed_rate;
    uint32_t notify_failed_rate;
    int64_t last_time = k_uptime_get();
    int64_t current_time;
    int64_t delta_time;

    LOG_INF("Logger thread started");

    while (1) {
        k_msleep(1000); // Log every second

        current_time = k_uptime_get();
        delta_time = current_time - last_time;

        if (delta_time <= 0) {
            // Avoid division by zero or negative time delta if clock wraps or resolution is low
            continue;
        }

        current_write_count = atomic_get(&test_write_count);
        current_notify_count = atomic_get(&test_gatt_notify_count);
 
        current_write_failed_count = atomic_get(&test_write_failed_count);
        current_notify_failed_count = atomic_get(&test_notify_failed_count);
 
        // Calculate rate per second
        write_rate = ((current_write_count - last_write_count) * 1000) / delta_time;
        notify_rate = ((current_notify_count - last_notify_count) * 1000) / delta_time;
        write_failed_rate = ((current_write_failed_count - last_write_failed_count) * 1000) / delta_time;
        notify_failed_rate = ((current_notify_failed_count - last_notify_failed_count) * 1000) / delta_time;
 
        LOG_INF("BLE Test Rate -> Writes/s: %u (Fail: %u), Notifies/s: %u (Fail: %u)",
                write_rate, write_failed_rate, notify_rate, notify_failed_rate);
 
        last_write_count = current_write_count;
        last_notify_count = current_notify_count;
        last_write_failed_count = current_write_failed_count;
        last_notify_failed_count = current_notify_failed_count;
        last_time = current_time;
    }
}


// --- Main Test Function ---

int transport_ble_test(void)
{
    int err;

    LOG_INF("Starting BLE Transport Test...");

    // 0. Initialize test state
    test_conn = NULL;
    test_subscribed = false;
    atomic_set(&test_write_count, 0); // Ensure counters start at 0
    atomic_set(&test_gatt_notify_count, 0);
    atomic_set(&test_write_failed_count, 0);
    atomic_set(&test_notify_failed_count, 0);
    ring_buf_init(&test_ring_buf, sizeof(test_tx_queue), test_tx_queue);
 
    // 1. Turn Bluetooth On
    err = bt_enable(NULL);
    if (err) {
        LOG_ERR("Bluetooth init failed (err %d)", err);
        return err;
    }
    LOG_INF("Bluetooth initialized");

    bt_conn_cb_register(&test_conn_callbacks);

    // 2. Register GATT Service
    err = bt_gatt_service_register(&test_audio_service);
     if (err) {
        LOG_ERR("Failed to register test GATT service (err %d)", err);
        return err;
    }
    LOG_INF("Test GATT service registered");


    // 3. Advertise
    err = bt_le_adv_start(BT_LE_ADV_CONN, test_ad, ARRAY_SIZE(test_ad), NULL, 0);
    if (err) {
        LOG_ERR("Advertising failed to start (err %d)", err);
        return err;
    }
    LOG_INF("Advertising successfully started. Waiting for connection and subscription...");

    // 4. Wait for subscriber (handled within reader thread)
    //    The reader thread will wait until test_conn and test_subscribed are set.

    // 5. Start Threads
    // Writer Thread
    k_tid_t writer_tid = k_thread_create(&writer_thread_data, writer_stack_area,
                                       K_THREAD_STACK_SIZEOF(writer_stack_area),
                                       writer_thread_entry,
                                       NULL, NULL, NULL,
                                       WRITER_PRIORITY, 0, K_NO_WAIT);
    if (!writer_tid) {
        LOG_ERR("Failed to create writer thread");
        return -1; // Or appropriate error code
    }
     k_thread_name_set(writer_tid, "ble_test_writer");


    // Reader/Notifier Thread
    k_tid_t reader_tid = k_thread_create(&reader_thread_data, reader_stack_area,
                                       K_THREAD_STACK_SIZEOF(reader_stack_area),
                                       reader_notifier_thread_entry,
                                       NULL, NULL, NULL,
                                       READER_PRIORITY, 0, K_NO_WAIT);
     if (!reader_tid) {
        LOG_ERR("Failed to create reader thread");
        // Consider stopping the writer thread here
        return -1; // Or appropriate error code
    }
    k_thread_name_set(reader_tid, "ble_test_reader");

    // Logger Thread
    k_tid_t logger_tid = k_thread_create(&logger_thread_data, logger_stack_area,
                                       K_THREAD_STACK_SIZEOF(logger_stack_area),
                                       logger_thread_entry,
                                       NULL, NULL, NULL,
                                       LOGGER_PRIORITY, 0, K_NO_WAIT);
    if (!logger_tid) {
        LOG_ERR("Failed to create logger thread");
        // Consider stopping other threads here
        return -1; // Or appropriate error code
    }
    k_thread_name_set(logger_tid, "ble_test_logger");


    LOG_INF("Test threads started. Running indefinitely.");

    // The function returns, but the threads continue running.
    // You might want to add a mechanism to stop the test later.
    return 0;
}
