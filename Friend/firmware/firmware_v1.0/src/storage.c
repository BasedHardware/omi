#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/sys/atomic.h>
#include "utils.h"
#include "btutils.h"
#include "sdcard.h"
#include <string.h>
#include <stdio.h>

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 100
#define FRAME_PREFIX_LENGTH 3

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static struct bt_uuid_128 storage_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_write_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_read_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

K_THREAD_STACK_DEFINE(storage_stack, 2048);
static struct k_thread storage_thread;

extern uint8_t file_count;
extern uint32_t file_num_array[20];
void broadcast_storage_packet(struct k_work *work_item);

static struct bt_gatt_attr storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&storage_write_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, storage_write_handler, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&storage_read_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, storage_read_characteristic, NULL, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),

};

static struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);

bool storage_is_on = false;


static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) {

    storage_is_on = true;
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

static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) {
    k_msleep(10);
    // char amount[1] = {file_count};
    uint32_t amount[20] = {0};
    for (int i = 0; i < file_count; i++) {
           amount[i] = file_num_array[i];
        }

    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, amount, file_count * sizeof(uint32_t));
    return result;
}

uint8_t transport_started = 0;

static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) {

    LOG_INF("about to schedule the storage");
    transport_started = 1;
    k_msleep(1000);
    
    
    return len;
}

static uint16_t packet_next_index = 0;

static uint8_t storage_write_buffer[256];

static uint32_t offset = 0;
static uint8_t index = 0;
static uint8_t current_packet_size = 0;
static uint8_t tx_buffer_size = 0;


static uint8_t current_read_num = 1;
uint32_t remaining_length = 0;

static int setup_storage_tx(void) {
    transport_started= (uint8_t)0; 
    offset = 0;

    int res = move_read_pointer(current_read_num);
    if (res) {
        printk("bad pointer\n");
        transport_started = 0;
        // current_read_num++;
        current_read_num = 1;
        remaining_length = 0;
        return -1;
    }
    else {
    if ((uint32_t)get_file_size(current_read_num) == 0 ) {
            // LOG_ERR("bad file size, moving again...");
            current_read_num++;
            move_read_pointer(current_read_num);
    }
    printk("current read ptr %d\n",current_read_num);

    remaining_length = get_file_size(current_read_num);
    LOG_INF("remaining length: %d",remaining_length);
    }
    return 0;

}


static void write_to_gatt(struct bt_conn *conn) {
    uint32_t id = packet_next_index++;
    index = 0;
    storage_write_buffer[0] = id & 0xFF;
    storage_write_buffer[1] = (id >> 8) & 0xFF;
    storage_write_buffer[2] = index;

    uint32_t packet_size = MIN(remaining_length,OPUS_ENTRY_LENGTH);

    int r = read_audio_data(storage_write_buffer+FRAME_PREFIX_LENGTH,packet_size,offset);
    offset = offset + packet_size;
    remaining_length = remaining_length - OPUS_ENTRY_LENGTH;
    index++;

    int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size+3);
}



void storage_write(void) {
  while (1) {
    
    if ( transport_started ) {
    LOG_INF("transpor started in side : %d",transport_started);
        setup_storage_tx();
    }

    if(remaining_length > 0 ) {

        struct bt_conn *conn = get_current_connection();
        if (conn == NULL)  {
            LOG_ERR("invalid connection");
            k_yield();
        }
        write_to_gatt(conn);

        transport_started = 0;
        if (remaining_length == 0) {
           printk("done. attempting to download more files\n");

        //    current_read_num++;
           k_sleep(K_MSEC(10));
        //    int res = setup_storage_tx();
        //    if (res) {

        //     printk("Error occuring while moving pointers. Exiting..\n");
        //    }
           
        }
        
        }
        

        k_yield();
  }

}

int storage_init() {

    bt_gatt_service_register(&storage_service);
    k_thread_create(&storage_thread, storage_stack, K_THREAD_STACK_SIZEOF(storage_stack), (k_thread_entry_t)storage_write, NULL, NULL, NULL, K_PRIO_PREEMPT(7), 0, K_NO_WAIT);

    return 0;

}