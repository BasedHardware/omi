#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/bluetooth/gatt.h>

#include "capture_mute.h"

typedef enum {
    OMI_POWER_CMD_ACTIVE = 0x00,
    OMI_POWER_CMD_POWER_OFF = 0x01,
    OMI_POWER_CMD_PAUSE_CAPTURE = 0x02,
} omi_power_cmd_t;

/* Implemented by the transport's dedicated shutdown thread. */
static int power_control_schedule_off(void);
static bool power_control_off_pending(void);

static inline ssize_t power_control_gatt_write(const void *buf, uint16_t len, uint16_t offset)
{
    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (len != 1) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    uint8_t command = ((const uint8_t *) buf)[0];
    if (command == OMI_POWER_CMD_POWER_OFF) {
        return power_control_schedule_off() < 0 ? BT_GATT_ERR(BT_ATT_ERR_UNLIKELY) : len;
    }
    if (command != OMI_POWER_CMD_ACTIVE && command != OMI_POWER_CMD_PAUSE_CAPTURE) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    if (power_control_off_pending()) {
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    }
    /* One durable pause owner for both UUIDs: disconnect/AAD cannot unmute.
     * Keep sampling policy owned by mic.c; explicit mute gates TX and storage. */
    if (capture_mute_set(command == OMI_POWER_CMD_PAUSE_CAPTURE)) {
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }
    return len;
}

static inline uint8_t power_control_gatt_state(bool off)
{
    if (off || power_control_off_pending()) {
        return OMI_POWER_CMD_POWER_OFF;
    }
    return capture_mute_is_set() ? OMI_POWER_CMD_PAUSE_CAPTURE : OMI_POWER_CMD_ACTIVE;
}
