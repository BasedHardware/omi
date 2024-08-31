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

void broadcast_storage_packet(struct k_work *work_item);
K_WORK_DELAYABLE_DEFINE(storage_work, broadcast_storage_packet);

static struct bt_gatt_attr storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&storage_write_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, storage_write_handler, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&storage_read_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, storage_read_characteristic, NULL, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),

};

static struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);


static info_file_t info_file;
static char hello[256];

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) {
    printk("hoi \n");
}
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
    return result;
}

int register_storage_service() {
    bt_gatt_service_register(&storage_service);
    return 0;
}

static uint8_t storage_write_buffer[256];
static uint32_t remaining_length = 0;
static bool transport_started = false;
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) {
    //get the requested file and download it. need to use work orders
    printk("%s\n",((char*)buf)[0]);

    printk("about to schedule the storage\n");
    k_msleep(10);
    get_info_file_data_();
    transport_started = true;
    
    k_work_schedule(&storage_work, K_MSEC(1000));

    return len;
}

static uint32_t offset = 0;
#define MAX_PACKET_LENGTH 256
void broadcast_storage_packet(struct k_work *work_item) { //staggerable
   if (transport_started == true) {
        remaining_length = get_file_size();
        transport_started=false;
   }
    printk("about to broadcast the storage packet\n");

    uint32_t packet_size = MIN(remaining_length,MAX_PACKET_LENGTH);
    int r = read_audio_data(storage_write_buffer,MAX_PACKET_LENGTH,offset);
    offset = offset + packet_size;
    remaining_length = MAX(remaining_length - packet_size,0);
    printk("current offset: %d\n",offset);
    printk("current reamining length: %d\n",remaining_length);
    struct bt_conn *conn = get_current_connection();
    if (conn == NULL)  {
        printk("invalid connection\n");
    }
    printk("almost there/...\n");
    int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size);
    printk("finished broadcast\n");
    if (remaining_length > 0) {
        k_work_reschedule(&storage_work,K_MSEC(1000));
    }
    else {
        printk("finished broadcasting audio file\n");
    }
}

