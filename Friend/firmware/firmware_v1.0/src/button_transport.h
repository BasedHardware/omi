#ifndef BUTTON_TRANSPORT_H
#define BUTTON_TRANSPORT_H

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>

int notify_gatt(const int attr_idx, const void *data, uint16_t len);

int notify_gatt_button_state(const int state);

int register_gatt_service();

#endif
