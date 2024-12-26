#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/ring_buffer.h>
#include "transport.h"
#include "config.h"
#include "utils.h"
// #include "nfc.h"
#include "speaker.h"
#include "sdcard.h"
#include "storage.h"
#include "button.h"
#include "mic.h"
#include "accel.h"
#include "lib/battery/battery.h"

LOG_MODULE_REGISTER(accel, CONFIG_LOG_DEFAULT_LEVEL);

static struct device *lsm6dsl_dev;
static struct sensors mega_sensor;

struct gpio_dt_spec accel_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio1)), .pin=8, .dt_flags = GPIO_INT_DISABLE};

struct sensors *accel_read()
{
    sensor_sample_fetch_chan(lsm6dsl_dev, SENSOR_CHAN_ACCEL_XYZ);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_X, &mega_sensor.a_x);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_Y, &mega_sensor.a_y);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_ACCEL_Z, &mega_sensor.a_z);

    sensor_sample_fetch_chan(lsm6dsl_dev, SENSOR_CHAN_GYRO_XYZ);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_X, &mega_sensor.g_x);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_Y, &mega_sensor.g_y);
	sensor_channel_get(lsm6dsl_dev, SENSOR_CHAN_GYRO_Z, &mega_sensor.g_z);

    return &mega_sensor;
}

int accel_start() 
{
    struct sensor_value odr_attr;
    lsm6dsl_dev = DEVICE_DT_GET_ONE(st_lsm6dsl);
    k_msleep(50);
    if (lsm6dsl_dev == NULL) 
    {
        LOG_ERR("Could not get LSM6DSL device");
        return 0;
	}
    if (!device_is_ready(lsm6dsl_dev)) 
    {
		LOG_ERR("LSM6DSL: not ready");
		return 0;
	}
    odr_attr.val1 = 10;
	odr_attr.val2 = 0;

    if (gpio_is_ready_dt(&accel_gpio_pin)) 
    {
		printk("Speaker Pin ready\n");
	}
    else 
    {
		printk("Error setting up speaker Pin\n");
        return -1;
	}
	if (gpio_pin_configure_dt(&accel_gpio_pin, GPIO_OUTPUT_INACTIVE) < 0) 
    {
		printk("Error setting up Haptic Pin\n");
        return -1;
	}
    gpio_pin_set_dt(&accel_gpio_pin, 1);
    if (sensor_attr_set(lsm6dsl_dev, SENSOR_CHAN_ACCEL_XYZ,
		SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) 
    {
	    LOG_ERR("Cannot set sampling frequency for Accelerometer.");
		return 0;
	}
    if (sensor_attr_set(lsm6dsl_dev, SENSOR_CHAN_GYRO_XYZ,
		SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
	    LOG_ERR("Cannot set sampling frequency for gyro.");
	    return 0;
	}
    if (sensor_sample_fetch(lsm6dsl_dev) < 0) 
    {
        LOG_ERR("Sensor sample update error");
        return 0;
	}

    LOG_INF("Accelerometer is ready for use \n");
    
    return 1;
}

void accel_off()
{
    gpio_pin_set_dt(&accel_gpio_pin, 0);
}
