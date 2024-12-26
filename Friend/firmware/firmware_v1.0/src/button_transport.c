#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/logging/log.h>
#include "button.h"
#include "transport.h"
LOG_MODULE_REGISTER(button_transport, CONFIG_LOG_DEFAULT_LEVEL);

static int final_button_state[2] = {0,0};

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t button_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

static struct bt_uuid_128 button_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7924,0x0000,0x1000,0x7450,0x346EAC492E92));
static struct bt_uuid_128 button_characteristic_data_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7925 ,0x0000,0x1000,0x7450,0x346EAC492E92));

static struct bt_gatt_attr button_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&button_uuid),
    BT_GATT_CHARACTERISTIC(&button_characteristic_data_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, button_data_read_characteristic, NULL, NULL),
    BT_GATT_CCC(button_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service button_service = BT_GATT_SERVICE(button_service_attr);

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) 
{
    if (value == BT_GATT_CCC_NOTIFY)
    {
        LOG_INF("Client subscribed for notifications");
    }
    else if (value == 0)
    {
        LOG_INF("Client unsubscribed from notifications");
    }
    else
    {
        LOG_ERR("Invalid CCC value: %u", value);
    }

}

static ssize_t button_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) 
{
    LOG_INF("button_data_read_characteristic");
    printf("was_pressed: %d\n", final_button_state[0]);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &final_button_state, sizeof(final_button_state));
}

int notify_gatt(const int attr_idx, const void *data, uint16_t len) {
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL)
    { 
        return bt_gatt_notify(conn, &button_service.attrs[attr_idx], data, len);
    }

    return -1;
}

int notify_gatt_button_state(const int state) 
{
    final_button_state[0] = state; 
    notify_gatt(1, &final_button_state, sizeof(final_button_state));
}

int register_gatt_service() {
    return bt_gatt_service_register(&button_service);
}
