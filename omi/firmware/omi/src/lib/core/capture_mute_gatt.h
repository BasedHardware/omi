#pragma once

#include <stdint.h>
#include <zephyr/bluetooth/gatt.h>

#include "capture_mute.h"

/* The ATT acknowledgement is a durability promise, not just a RAM update. */
static inline ssize_t capture_mute_gatt_write(const void *buf, uint16_t len, uint16_t offset)
{
    if (offset != 0) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    if (len != 1) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }
    if (capture_mute_set(((const uint8_t *) buf)[0] != 0)) {
        return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    }
    return len;
}
