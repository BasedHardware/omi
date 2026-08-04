#include <errno.h>
#include <string.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

static struct bt_uuid_128 audio_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10000, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 dim_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10011, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 gain_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x19B10012, 0xE8F2, 0x537E, 0x4F6C, 0xD104768A1214));
static struct bt_uuid_128 button_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7925, 0x0000, 0x1000, 0x7450, 0x346EAC492E92));
static struct bt_conn *connection;
static struct k_sem operation;
static uint16_t discovered_handle;
static uint8_t read_value[8];
static uint16_t read_length;
static int operation_error;

static bool advertisement_data(struct bt_data *data, void *user_data)
{
    bool *found = user_data;

    if (data->type == BT_DATA_UUID128_ALL && data->data_len == 16 &&
        !memcmp(data->data, audio_uuid.val, sizeof(audio_uuid.val))) {
        *found = true;
        return false;
    }

    return true;
}

static void scan_received(const struct bt_le_scan_recv_info *info, struct net_buf_simple *buffer)
{
    bool found = false;
    bt_data_parse(buffer, advertisement_data, &found);
    if (!found || connection != NULL) {
        return;
    }

    if (bt_le_scan_stop()) {
        return;
    }

    if (bt_conn_le_create(info->addr, BT_CONN_LE_CREATE_CONN, BT_LE_CONN_PARAM_DEFAULT, &connection)) {
        connection = NULL;
    }
}

static void connected(struct bt_conn *conn, uint8_t err)
{
    operation_error = err;
    k_sem_give(&operation);
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    if (connection != NULL) {
        bt_conn_unref(connection);
        connection = NULL;
    }
}

BT_CONN_CB_DEFINE(connection_callbacks) = {
    .connected = connected,
    .disconnected = disconnected,
};

static uint8_t discovered(struct bt_conn *conn, const struct bt_gatt_attr *attr, struct bt_gatt_discover_params *params)
{
    if (attr == NULL) {
        operation_error = -ENOENT;
    } else {
        discovered_handle = bt_gatt_attr_value_handle(attr);
        operation_error = 0;
    }
    memset(params, 0, sizeof(*params));
    k_sem_give(&operation);
    return BT_GATT_ITER_STOP;
}

static int find_characteristic(const struct bt_uuid *uuid)
{
    static struct bt_gatt_discover_params params;
    discovered_handle = 0;
    operation_error = 0;
    params.uuid = uuid;
    params.func = discovered;
    params.start_handle = BT_ATT_FIRST_ATTRIBUTE_HANDLE;
    params.end_handle = BT_ATT_LAST_ATTRIBUTE_HANDLE;
    params.type = BT_GATT_DISCOVER_CHARACTERISTIC;

    int err = bt_gatt_discover(connection, &params);
    if (err) {
        return err;
    }
    k_sem_take(&operation, K_FOREVER);
    return operation_error;
}

static uint8_t
read_complete(struct bt_conn *conn, uint8_t err, struct bt_gatt_read_params *params, const void *data, uint16_t length)
{
    operation_error = err;
    read_length = MIN(length, sizeof(read_value));
    if (data != NULL) {
        memcpy(read_value, data, read_length);
    }
    memset(params, 0, sizeof(*params));
    k_sem_give(&operation);
    return BT_GATT_ITER_STOP;
}

static int read_characteristic(uint16_t handle)
{
    static struct bt_gatt_read_params params;
    read_length = 0;
    params.func = read_complete;
    params.handle_count = 1;
    params.single.handle = handle;
    params.single.offset = 0;
    int err = bt_gatt_read(connection, &params);
    if (err) {
        return err;
    }
    k_sem_take(&operation, K_FOREVER);
    return operation_error;
}

static void write_complete(struct bt_conn *conn, uint8_t err, struct bt_gatt_write_params *params)
{
    operation_error = err;
    memset(params, 0, sizeof(*params));
    k_sem_give(&operation);
}

static int write_characteristic(uint16_t handle, const uint8_t *value)
{
    static struct bt_gatt_write_params params;
    params.handle = handle;
    params.offset = 0;
    params.data = value;
    params.length = 1;
    params.func = write_complete;
    int err = bt_gatt_write(connection, &params);
    if (err) {
        return err;
    }
    k_sem_take(&operation, K_FOREVER);
    return operation_error;
}

static int verify_setting(const struct bt_uuid *uuid, uint8_t written, uint8_t expected)
{
    int err = find_characteristic(uuid);
    uint16_t handle = discovered_handle;
    if (err) {
        return err;
    }
    err = write_characteristic(handle, &written);
    if (err) {
        return err;
    }
    err = read_characteristic(handle);
    if (err) {
        return err;
    }
    return read_length == 1 && read_value[0] == expected ? 0 : -EINVAL;
}

static int verify_contract(void)
{
    int err = find_characteristic(&button_uuid.uuid);
    if (err) {
        return err;
    }
    err = read_characteristic(discovered_handle);
    if (err || read_length != 8 || read_value[0] != 0) {
        return err ? err : -EINVAL;
    }
    err = verify_setting(&dim_uuid.uuid, 64, 64);
    if (err) {
        return err;
    }
    return verify_setting(&gain_uuid.uuid, 9, 8);
}

int main(void)
{
    k_sem_init(&operation, 0, 1);
    int err = bt_enable(NULL);
    if (err) {
        printk("OMI_BSIM_FAIL bt_enable %d\n", err);
        return err;
    }

    static struct bt_le_scan_cb scan_callbacks = {
        .recv = scan_received,
    };
    bt_le_scan_cb_register(&scan_callbacks);
    err = bt_le_scan_start(BT_LE_SCAN_ACTIVE, NULL);
    if (err) {
        printk("OMI_BSIM_FAIL scan %d\n", err);
        return err;
    }

    k_sem_take(&operation, K_FOREVER);
    if (operation_error) {
        printk("OMI_BSIM_FAIL connect %d\n", operation_error);
        return operation_error;
    }

    err = verify_contract();
    if (err) {
        printk("OMI_BSIM_FAIL contract %d\n", err);
        return err;
    }

    printk("OMI_BSIM_PASS\n");
    bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
    return 0;
}
