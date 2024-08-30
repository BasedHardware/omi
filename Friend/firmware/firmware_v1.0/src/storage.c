#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/sys/atomic.h>
#include "transport.h"
#include "config.h"
#include "utils.h"
#include "btutils.h"
#include "speaker.h"
#include "sdcard.h"
static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static struct bt_uuid_128 storage_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001540, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 storage_write_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001541, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 storage_read_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001542, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

static struct bt_gatt_attr storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&storage_read_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, storage_read_characteristic, NULL, NULL),
    // BT_GATT_CHARACTERISTIC(&storage_write_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, storage_write_handler, NULL),
    // BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);


static info_file_t info_file;
static char hello[256];


void update_info_buffer() {
      char* b = get_info_file_data_();  
      printk("hg\n");
      memcpy(hello,b,256);
      k_free(b);
}

static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) {
    printk("hello\n");
    k_msleep(10);
    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, hello, 256);
    printk("hello\n"); 
    k_msleep(10);
    return result;
}

int register_storage_service() {
    bt_gatt_service_register(&storage_service);
    return 0;
}

