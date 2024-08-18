#include "nfc.h"
#include <zephyr/logging/log.h>
#include <zephyr/drivers/hwinfo.h>
#include <nfc_t2t_lib.h>
#include <nfc/ndef/msg.h>
#include <nfc/ndef/uri_msg.h>

LOG_MODULE_REGISTER(nfc, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_URI_LENGTH 64
#define MAX_DEVICE_ID_LENGTH 7  // 6 chars + null terminator
#define NDEF_MSG_BUF_SIZE 256
#define MAX_REC_COUNT 1

static uint8_t ndef_msg_buf[NDEF_MSG_BUF_SIZE];
static char device_id[MAX_DEVICE_ID_LENGTH];
static char uri_buffer[MAX_URI_LENGTH];

// int get_device_id(char *device_id_out, size_t len)
// {
//     if (len < MAX_DEVICE_ID_LENGTH) {
//         return -EINVAL;
//     }

//     uint8_t dev_id[8];
//     ssize_t ret;

//     ret = hwinfo_get_device_id(dev_id, sizeof(dev_id));
//     if (ret < 0) {
//         LOG_ERR("Failed to get device ID, error: %d", ret);
//         return ret;
//     }

//     snprintf(device_id_out, len, "%02X%02X%02X", dev_id[5], dev_id[6], dev_id[7]);
//     LOG_INF("Device ID: %s", device_id_out);

//     return 0;
// }
int get_device_id(char *device_id_out, size_t len)
{
    if (len < MAX_DEVICE_ID_LENGTH) {
        return -EINVAL;
    }

    // Hardcoded device ID for testing
    const char *test_device_id = "ABC123";

    strncpy(device_id_out, test_device_id, len - 1);
    device_id_out[len - 1] = '\0';  // Ensure null-termination

    LOG_INF("Device ID (hardcoded): %s", device_id_out);

    return 0;
}

int nfc_sleep(void)
{
    int err = nfc_t2t_emulation_stop();
    if (err != 0) {
        LOG_ERR("Failed to stop NFC emulation, error: %d", err);
        return err;
    }
    LOG_INF("NFC entered sleep mode");
    return 0;
}

int nfc_wake(void)
{
    int err = nfc_t2t_emulation_start();
    if (err != 0) {
        LOG_ERR("Failed to start NFC emulation, error: %d", err);
        return err;
    }
    LOG_INF("NFC woke from sleep mode");
    return 0;
}

static void nfc_callback(void *context, nfc_t2t_event_t event, const uint8_t *data, size_t data_length)
{
    LOG_INF("NFC Event: %d", event);
}

static int nfc_create_message(void)
{
    int err;

    if (get_device_id(device_id, sizeof(device_id)) != 0) {
        LOG_ERR("Failed to get device ID");
        return -EIO;
    }

    snprintf(uri_buffer, sizeof(uri_buffer), "https://friend.based.com/pair?id=%s", device_id);

    NFC_NDEF_MSG_DEF(nfc_msg, MAX_REC_COUNT);
    NFC_NDEF_URI_RECORD_DESC_DEF(uri_rec, 0, uri_buffer, strlen(uri_buffer));

    err = nfc_ndef_msg_record_add(&NFC_NDEF_MSG(nfc_msg), &NFC_NDEF_URI_RECORD_DESC(uri_rec));
    if (err != 0) {
        LOG_ERR("Failed to add record to NDEF message, error: %d", err);
        return -EIO;
    }

    uint32_t msg_len = sizeof(ndef_msg_buf);
    err = nfc_ndef_msg_encode(&NFC_NDEF_MSG(nfc_msg), ndef_msg_buf, &msg_len);
    if (err != 0) {
        LOG_ERR("Failed to encode NDEF message, error: %d", err);
        return -EIO;
    }

    return 0;
}

int nfc_init(void)
{
    int err;

    err = nfc_create_message();
    if (err != 0) {
        LOG_ERR("Failed to create NFC message, error: %d", err);
        return err;
    }

    /* Set up NFC */
    err = nfc_t2t_setup(nfc_callback, NULL);
    if (err != 0) {
        LOG_ERR("Failed to setup NFC T2T library, error: %d", err);
        return err;
    }

    /* Set payload */
    err = nfc_t2t_payload_set(ndef_msg_buf, sizeof(ndef_msg_buf));
    if (err != 0) {
        LOG_ERR("Failed to set NFC payload, error: %d", err);
        return err;
    }

    /* Start sensing NFC field */
    err = nfc_t2t_emulation_start();
    if (err != 0) {
        LOG_ERR("Failed to start NFC emulation, error: %d", err);
        return err;
    }

    LOG_INF("NFC initialized successfully");
    return 0;
}

int nfc_update_payload(const uint8_t *new_data, size_t len)
{
    if (len > sizeof(ndef_msg_buf)) {
        LOG_ERR("New payload too large");
        return -EINVAL;
    }

    memcpy(ndef_msg_buf, new_data, len);

    int err = nfc_t2t_payload_set(ndef_msg_buf, len);
    if (err) {
        LOG_ERR("Failed to update NFC payload, error: %d", err);
        return err;
    }

    LOG_INF("NFC payload updated successfully");
    return 0;
}
