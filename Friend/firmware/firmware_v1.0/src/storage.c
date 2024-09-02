#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/sys/atomic.h>
#include "config.h"
#include "utils.h"
#include "btutils.h"
#include "speaker.h"
#include "sdcard.h"
#include <string.h>
#include <stdio.h>
static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static struct bt_uuid_128 storage_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001540, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 storage_write_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001541, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static struct bt_uuid_128 storage_read_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x00001542, 0x1212, 0xEFDE, 0x1523, 0x785FEABCD123));
static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

K_THREAD_STACK_DEFINE(storage_stack, 2048);
static struct k_thread storage_thread;



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
static char num_buffer[32];
bool storage_is_on = false;


static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) {
    printk("hoi \n");
    // snprintf(hello, sizeof(hello), "%d",   get_file_size(5) );

    storage_is_on = true;

}

static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) {
    printk("hello\n");
    k_msleep(10);
    // printk("%d\n",get_file_size(5));
    // get_info_file_data_();
    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, hello, 256);
    return result;
}




static uint32_t remaining_length = 0;
static bool transport_started = false;
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) {
  
    printk("%s\n",((char*)buf)[0]);

    printk("about to schedule the storage\n");
    k_msleep(1000);
    transport_started = true;
    
    return len;
}
static uint16_t packet_next_index = 0;


//start num is assumed to be 2 
static uint8_t lowest_num = 2;
static uint8_t storage_write_buffer[256];

static uint32_t offset = 0;
static uint8_t index = 0;
static uint8_t current_packet_size = 0;
static uint8_t tx_buffer_size = 0;
bool storage_is_subscribed() {

    
    return bt_gatt_is_subscribed(get_current_connection(), &storage_service.attrs[1], BT_GATT_CCC_NOTIFY);

}
#define MAX_PACKET_LENGTH 256
static uint8_t starting_num[2];
void storage_write(void) {
  while (1) {
    if ( transport_started) {
        offset = 1;
        index = 0;
        move_read_pointer(7);
        // remaining_length = (uint32_t)get_file_size(7);
         remaining_length = 1000;
        printk("remaining length: %d \n",remaining_length);
        transport_started=false;
        
        read_audio_data(&starting_num,2,0);
        tx_buffer_size = starting_num[0];
        printk("first number is %d\n",tx_buffer_size);
    }
    // printk("hello\n");

    if(remaining_length > 0) {
        uint32_t id = packet_next_index++;
        
        storage_write_buffer[0] = id & 0xFF;
        storage_write_buffer[1] = (id >> 8) & 0xFF;
        storage_write_buffer[2] = index;
        printk("current buffer size is %d\n",tx_buffer_size);
        uint32_t packet_size = MIN(remaining_length,tx_buffer_size+1);
        
        int r = read_audio_data(storage_write_buffer+3,packet_size,offset);
        tx_buffer_size=storage_write_buffer[3+packet_size-1];
        // printk("next tx buffer os %d\n",tx_buffer_size);
        offset = offset + packet_size;
        remaining_length = MAX(remaining_length - packet_size,0);
        index++;
        
        // printk("current offset: %d\n",offset);
        printk("current reamining length: %d\n",remaining_length);
        struct bt_conn *conn = get_current_connection();
        if (conn == NULL)  {
            printk("invalid connection\n");
            k_sleep(K_MSEC(10));
        }
        int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size+3-1);

        k_sleep(K_MSEC(10));
        }
        // printk("hullo\n");
        k_yield();
  }
}

int storage_init() {
    k_thread_create(&storage_thread, storage_stack, K_THREAD_STACK_SIZEOF(storage_stack), (k_thread_entry_t)storage_write, NULL, NULL, NULL, K_PRIO_PREEMPT(7), 0, K_NO_WAIT);
    return 0;
}