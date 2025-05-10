#ifndef ACCEL_H
#define ACCEL_H

#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>

// Struct to hold sensor data
struct sensors {
    struct sensor_value a_x;
    struct sensor_value a_y;
    struct sensor_value a_z;
    struct sensor_value g_x;
    struct sensor_value g_y;
    struct sensor_value g_z;
};

// Public functions
int accel_start(void);
void accel_off(void);
void register_accel_service(struct bt_conn *conn);

#endif /* ACCEL_H */
