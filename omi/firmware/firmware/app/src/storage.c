#include <string.h>
#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include "utils.h"
#include "sdcard.h"
#include "storage.h"
#include "transport.h"

LOG_MODULE_REGISTER(storage, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_PACKET_LENGTH 256
#define OPUS_ENTRY_LENGTH 80
#define FRAME_PREFIX_LENGTH 3

#define READ_COMMAND 0
#define DELETE_COMMAND 1
#define NUKE 2
#define STOP_COMMAND 3

#define INVALID_FILE_SIZE 3
#define ZERO_FILE_SIZE 4
#define INVALID_COMMAND 6

#define MAX_HEARTBEAT_FRAMES 100
#define HEARTBEAT 50
static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

static struct bt_uuid_128 storage_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295780, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_write_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295781, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static struct bt_uuid_128 storage_read_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x30295782, 0x4301, 0xEABD, 0x2904, 0x2849ADFEAE43));
static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

K_THREAD_STACK_DEFINE(storage_stack, 4096);
static struct k_thread storage_thread;

extern uint8_t file_count;
extern uint32_t file_num_array[2];
void broadcast_storage_packet(struct k_work *work_item);

static struct bt_gatt_attr storage_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&storage_service_uuid),
    BT_GATT_CHARACTERISTIC(&storage_write_uuid.uuid, BT_GATT_CHRC_WRITE | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_WRITE, NULL, storage_write_handler, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
    BT_GATT_CHARACTERISTIC(&storage_read_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, storage_read_characteristic, NULL, NULL),
    BT_GATT_CCC(storage_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),

};

struct bt_gatt_service storage_service = BT_GATT_SERVICE(storage_service_attr);

bool storage_is_on = false;

static void storage_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) 
{

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

static ssize_t storage_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) 
{
    k_msleep(10);
    uint32_t amount[2] = {0};
    for (int i = 0; i < 2; i++) {
           amount[i] = file_num_array[i];
        }
    ssize_t result = bt_gatt_attr_read(conn, attr, buf, len, offset, amount, 2 * sizeof(uint32_t));
    return result;
}

uint8_t transport_started = 0;


static uint16_t packet_next_index = 0;
#define SD_BLE_SIZE 440
static uint8_t storage_write_buffer[SD_BLE_SIZE];

static uint32_t offset = 0;
static uint8_t index = 0;
static uint8_t current_packet_size = 0;
static uint8_t tx_buffer_size = 0;
static uint8_t stop_started = 0;
static uint8_t delete_started = 0;
static uint8_t current_read_num = 1;
uint32_t remaining_length = 0;

static int setup_storage_tx() 
{
    transport_started = (uint8_t)0; 
    // offset = 0;
    LOG_INF("about to transmit storage\n");
    k_msleep(1000);
    int res = move_read_pointer(current_read_num);
    if (res) 
    {
        LOG_INF("bad pointer");
        transport_started = 0;
        current_read_num = 1;
        remaining_length = 0;
        return -1;
    }

    LOG_INF("current read ptr %d",current_read_num);
   
    remaining_length = file_num_array[current_read_num-1];
    if(current_read_num == file_count) 
    {
        remaining_length = get_file_size(file_count);
    }

    remaining_length = remaining_length - offset;
    
    // offset=offset_;
    LOG_INF("remaining length: %d",remaining_length);
    LOG_INF("offset: %d",offset);
    LOG_INF("file: %d",current_read_num);
    
    return 0;

}
uint8_t delete_num = 0;
uint8_t nuke_started = 0;
static uint8_t heartbeat_count = 0;
static uint8_t parse_storage_command(void *buf,uint16_t len) 
{

    if (len != 6 && len != 2) 
    {
        LOG_INF("invalid command");
        return INVALID_COMMAND;
    }
    const uint8_t command = ((uint8_t*)buf)[0];
    const uint8_t file_num = ((uint8_t*)buf)[1];
    uint32_t size = 0;
    if ( len == 6 ) 
    {
        size = ((uint8_t*)buf)[2] <<24 |((uint8_t*)buf)[3] << 16 | ((uint8_t*)buf)[4] << 8 | ((uint8_t*)buf)[5];
    }
    LOG_PRINTK("command successful: command: %d file: %d size: %d \n",command,file_num,size);

    if (file_num == 0) 
    {
        LOG_INF("invalid file count 0");
        return INVALID_FILE_SIZE;
    }
    if (file_num > file_count)  //invalid file count 
    {
        LOG_INF("invalid file count");
        return INVALID_FILE_SIZE;
    //add audio all?
    }
    if (command == READ_COMMAND) //read 
    { 
        uint32_t temp = file_num_array[file_num-1];
        if ( file_num == ( file_count ) ) 
        {
            LOG_INF("file_count == final file");
            offset = size - (size % SD_BLE_SIZE); //round down to nearest SD_BLE_SIZE
            current_read_num = file_num;
            transport_started = 1;           
        }
        else if (temp == 0) 
        {
            LOG_INF("file size is 0");
            return ZERO_FILE_SIZE;
        }
        else if (size > temp) 
        {
            LOG_INF("requested size is too large");
            return 5;
        }
        else 
        {
            LOG_INF("valid command, setting up ");
            offset = size - (size % SD_BLE_SIZE);
            current_read_num = file_num;
            transport_started = 1;
        }
    }
    else if (command == DELETE_COMMAND) 
    {
        delete_num = file_num;
        delete_started = 1;
    }
    else if (command == NUKE) 
    {
        nuke_started = 1;
    }
    else if (command == STOP_COMMAND) //should be no explicit stop command, send heartbeats to keep connection alive
    {
        remaining_length = 0;
        stop_started = 1;
    }
    else if (command == HEARTBEAT)
    {
        heartbeat_count = 0;
    }
    else 
    {
        LOG_INF("invalid command \n");
        return 6;
    }
    return 0;

}

static ssize_t storage_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags) 
{
    LOG_INF("about to schedule the storage");
    LOG_INF("was sent %d  ", ((uint8_t*)buf)[0] );

    uint8_t result_buffer[1] = {0};
    uint8_t result = parse_storage_command(buf,len);
    result_buffer[0] = result; 
    LOG_INF("length of storage write: %d",len);
    LOG_INF("result: %d ", result);
    bt_gatt_notify(conn, &storage_service.attrs[1], &result_buffer,1);
    k_msleep(500);
    return len;
}

// static void write_to_gatt(struct bt_conn *conn) 
// {
//     uint32_t id = packet_next_index++;
//     index = 0;
//     storage_write_buffer[0] = id & 0xFF;
//     storage_write_buffer[1] = (id >> 8) & 0xFF;
//     storage_write_buffer[2] = index;

//     const uint32_t packet_size = MIN(remaining_length,OPUS_ENTRY_LENGTH);

//     int r = read_audio_data(storage_write_buffer+FRAME_PREFIX_LENGTH,packet_size,offset);
//     offset = offset + packet_size;

//     index++;

//     int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size+FRAME_PREFIX_LENGTH);
//     if (err) 
//     {
//         LOG_PRINTK("error writing to gatt: %d\n",err);
//     }
//     else 
//     {
//     remaining_length = remaining_length - OPUS_ENTRY_LENGTH;
//     }
// }

static void write_to_gatt(struct bt_conn *conn) { //unsafe. designed for max speeds. udp?

    uint32_t packet_size = MIN(remaining_length,SD_BLE_SIZE);

    int r = read_audio_data(storage_write_buffer,packet_size,offset);
    offset = offset + packet_size;
    int err = bt_gatt_notify(conn, &storage_service.attrs[1], &storage_write_buffer,packet_size);
    if (err) 
    {
        LOG_PRINTK("error writing to gatt: %d\n",err);
    }
    else 
    {
    remaining_length = remaining_length - SD_BLE_SIZE;
    }
    // LOG_PRINTK("wrote to gatt %d\n",err);
}

void storage_write(void) 
{
  while (1) 
  {
    struct bt_conn *conn = get_current_connection();
    
    if ( transport_started ) 
    {
        LOG_INF("transpor started in side : %d",transport_started);
        setup_storage_tx();
    }
    //probably prefer to implement using work orders for delete,nuke,etc...
    if (delete_started) 
    { 
        LOG_INF("delete:%d\n",delete_started);
        int err = clear_audio_file(1);
        offset = 0;
        save_offset(offset);
        
        if (err) 
        {
            LOG_PRINTK("error clearing\n");
        }
        else 
        {
            uint8_t result_buffer[1] = {200};
            if (conn) 
            {
                bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &result_buffer,1);
            }
        }
        delete_started = 0;
        k_msleep(10);
    }
    if (nuke_started) 
    {
        clear_audio_directory();
        save_offset(0);
        nuke_started = 0;
    }
    if (stop_started) 
    { 
        remaining_length = 0;
        stop_started = 0;
        save_offset(offset);
    }
    if (heartbeat_count == MAX_HEARTBEAT_FRAMES)
    {
        LOG_PRINTK("no heartbeat sent\n");
        save_offset(offset);
        // k_yield();
        // continue;
    }

    if(remaining_length > 0 ) 
    {
        if (conn == NULL)  
        {
            LOG_ERR("invalid connection");
            remaining_length = 0;
            save_offset(offset);
            //save offset to flash
            continue;
            // k_yield();
        }
        // LOG_PRINTK("remaining length: %d\n",remaining_length);

        write_to_gatt(conn);
        heartbeat_count = (heartbeat_count + 1) % (MAX_HEARTBEAT_FRAMES + 1);
        
        transport_started = 0;
        if (remaining_length == 0 ) 
        {
            if(stop_started)
            {
                stop_started = 0;
            }
            else
            {
                LOG_PRINTK("done. attempting to download more files\n");
                uint8_t stop_result[1] = {100};
                int err = bt_gatt_notify(get_current_connection(), &storage_service.attrs[1], &stop_result,1);
                k_sleep(K_MSEC(10));
            }

        }   
     }
     k_yield();

  }

}

int storage_init() 
{
    k_thread_create(&storage_thread, storage_stack, K_THREAD_STACK_SIZEOF(storage_stack), (k_thread_entry_t)storage_write, NULL, NULL, NULL, K_PRIO_PREEMPT(7), 0, K_NO_WAIT);
    return 0;
}
