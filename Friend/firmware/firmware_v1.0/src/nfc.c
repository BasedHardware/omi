#include "nfc.h"
#include <zephyr/logging/log.h>
#include <nfc_t2t_lib.h>
#include <nfc/ndef/msg.h>
#include <nfc/ndef/uri_msg.h>
#include "transport.h"

LOG_MODULE_REGISTER(nfc, CONFIG_LOG_DEFAULT_LEVEL);

#define MAX_REC_COUNT 1
#define NDEF_MSG_BUF_SIZE 256

static uint8_t ndef_msg_buf[NDEF_MSG_BUF_SIZE];

static void nfc_callback(void *context, nfc_t2t_event_t event, const uint8_t *data, size_t data_length)
{
    // Handle NFC events here
}

static int nfc_create_message(void)
{
    int err;
    char device_id[7];  // 6 characters + null terminator

    // Get the device ID from the transport layer
    if (get_device_id(device_id, sizeof(device_id)) != 0) {
        LOG_ERR("Failed to get device ID");
        return -EIO;
    }

    LOG_INF("NFC Device ID: %s", device_id);

    // Construct the NDEF message
    NFC_NDEF_MSG_DEF(nfc_msg, MAX_REC_COUNT);
    NFC_NDEF_URI_RECORD_DESC_DEF(uri_rec, 0,
        "https://friend.based.com/pair?id=", sizeof("https://friend.based.com/pair?id=") - 1);

    err = nfc_ndef_msg_record_add(&NFC_NDEF_MSG(nfc_msg),
                                   &NFC_NDEF_URI_RECORD_DESC(uri_rec));
    if (err != 0) {
        LOG_ERR("Failed to add record to NDEF message");
        return -EIO;
    }

    uint32_t msg_len = sizeof(ndef_msg_buf);
    err = nfc_ndef_msg_encode(&NFC_NDEF_MSG(nfc_msg),
                               ndef_msg_buf,
                               &msg_len);
    if (err != 0) {
        LOG_ERR("Failed to encode NDEF message");
        return -EIO;
    }

    // Set up NFC
    err = nfc_t2t_setup(nfc_callback, NULL);
    if (err != 0) {
        LOG_ERR("Failed to setup NFC T2T library");
        return -EIO;
    }

    err = nfc_t2t_payload_set(ndef_msg_buf, msg_len);
    if (err != 0) {
        LOG_ERR("Failed to set NFC payload");
        return -EIO;
    }

    return 0;
}

int nfc_init(void)
{
    int err = nfc_create_message();
    if (err != 0) {
        LOG_ERR("Failed to create NFC message");
        return err;
    }

    // Start NFC
    err = nfc_t2t_emulation_start();
    if (err != 0) {
        LOG_ERR("Failed to start NFC emulation");
        return -EIO;
    }

    LOG_INF("NFC initialized successfully");
    return 0;
}

int nfc_update_payload(const uint8_t *new_data, size_t len)
{
    if (len > NDEF_MSG_BUF_SIZE) {
        LOG_ERR("New payload too large");
        return -EINVAL;
    }

    memcpy(ndef_msg_buf, new_data, len);

    int err = nfc_t2t_payload_set(ndef_msg_buf, len);
    if (err) {
        LOG_ERR("Failed to update NFC payload");
        return err;
    }

    LOG_INF("NFC payload updated successfully");
    return 0;
}
