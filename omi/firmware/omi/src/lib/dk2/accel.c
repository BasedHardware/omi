#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/drivers/sensor.h>
#include <nrfx.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>

#include "accel.h"

LOG_MODULE_REGISTER(accel, CONFIG_LOG_DEFAULT_LEVEL);

/**
 * Major issue here: the EVT2 uses a LSM6DS3TR-C with chip ID od 0x6A
 * From the EVT code:
 *   "need change sdk\modules\hal\st\sensor\stmemsc\lsm6dso_STdC\driver\lsm6dso_reg.h line 195 #define LSM6DSO_ID to 0x6A"
 * It will not be tractable to require source edits to the zephyr driver tree.
 * It also looks like STMicro has not shipped a driver for LSM6DS3TR-C into Zephyr yet.
 *
 * TOOD: It might be possible to ship a placeholer driver in our project.
 *   Given the note from Seeed about hacking the LSM6DSO driver, we might be able to just duplciate the whole LSM6DSO driver,
 *   and make minimal changes to make it act like a placeholder LSM6DS3TR-C driver.
 */

// Accelerometer part and DTS is different between DK2 and Omi2
#if defined(CONFIG_BOARD_OMI_NRF5340_CPUAPP)
static const struct device *const accel_dev = DEVICE_DT_GET(DT_NODELABEL(lsm6dso));
static const struct gpio_dt_spec accel_gpio_pin = GPIO_DT_SPEC_GET(DT_NODELABEL(lsm6dso_en_pin), gpios);
#else
static const struct device *const accel_dev = DEVICE_DT_GET_ONE(st_lsm6dsl);
static const struct gpio_dt_spec accel_gpio_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio1)), .pin=8, .dt_flags = GPIO_INT_DISABLE};
#endif

// Arbitrary uuid, feel free to change
static struct bt_uuid_128 accel_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403790,0x0000,0x1000,0x7450,0xBF445E5829A2));
static struct bt_uuid_128 accel_uuid_x = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x32403791,0x0000,0x1000,0x7450,0xBF445E5829A2));

static void accel_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t accel_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);

static struct bt_gatt_attr accel_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&accel_uuid),//primary description
    BT_GATT_CHARACTERISTIC(&accel_uuid_x.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, accel_data_read_characteristic, NULL, NULL),//data type
    BT_GATT_CCC(accel_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),//scheduler
};
static struct bt_gatt_service accel_service = BT_GATT_SERVICE(accel_service_attr);

static ssize_t accel_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset)
{
    LOG_INF("Acceleration data read characteristic");
    int axis_mode = 6; //3 for accel, 6 for (also) gyro
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &axis_mode, sizeof(axis_mode));
}

// Use d4,d5
static void accel_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
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

// Init hook to power up accel
static int accel_poweron(void)
{
    int ret;
    static const struct gpio_dt_spec lsm6dso_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(lsm6dso_en_pin), gpios, {0});

    LOG_DBG("IMU power on\n");
    ret = gpio_pin_configure_dt(&lsm6dso_en, (GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1));
    if (ret < 0)
    {
        LOG_ERR("Failed to configure pin %d\n", lsm6dso_en.pin);
        return ret;
    }

    ret = gpio_pin_set_dt(&lsm6dso_en, 1);
    if (ret < 0)
    {
        LOG_ERR("Failed to set pin %d\n", lsm6dso_en.pin);
        return ret;
    }
    k_sleep(K_MSEC(50));

    return 0;
}

// Register init hook to power on IMU
SYS_INIT(accel_poweron, POST_KERNEL, 89);


int accel_start(void)
{
    if (NULL == accel_dev)
    {
        LOG_ERR("Could not get LSM6DSL device");
        return -1;
    }

    if (!device_is_ready(accel_dev))
    {
        LOG_ERR("LSM6DSL: not ready");
        return -ENODEV;
    }

    struct sensor_value odr_attr;
    odr_attr.val1 = 26; // 26 Hz
    odr_attr.val2 = 0;
    if (sensor_attr_set(accel_dev, SENSOR_CHAN_ACCEL_XYZ,
        SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0)
    {
        LOG_ERR("Cannot set sampling frequency for Accelerometer.");
        return -1;
    }

    if (sensor_attr_set(accel_dev, SENSOR_CHAN_GYRO_XYZ,
        SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr) < 0) {
        LOG_ERR("Cannot set sampling frequency for gyro.");
        return -1;
    }
    if (sensor_sample_fetch(accel_dev) < 0)
    {
        LOG_ERR("Sensor sample update error");
        return -1;
    }

    LOG_INF("Accelerometer is ready for use \n");

    return 0;
}

int register_accel_service(struct bt_conn *conn)
{
    return bt_gatt_service_register(&accel_service);
}

void accel_off(void)
{
    gpio_pin_set_dt(&accel_gpio_pin, 0);
}

int accel_read( struct sensors* sensors )
{
    if( NULL == sensors )
    {
        return -1;
    }

    // TODO: add error checking on each of these
    sensor_sample_fetch_chan(accel_dev, SENSOR_CHAN_ACCEL_XYZ);
    sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_X, &sensors->a_x);
    sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_Y, &sensors->a_y);
    sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_Z, &sensors->a_z);

    sensor_sample_fetch_chan(accel_dev, SENSOR_CHAN_GYRO_XYZ);
    sensor_channel_get(accel_dev, SENSOR_CHAN_GYRO_X, &sensors->g_x);
    sensor_channel_get(accel_dev, SENSOR_CHAN_GYRO_Y, &sensors->g_y);
    sensor_channel_get(accel_dev, SENSOR_CHAN_GYRO_Z, &sensors->g_z);

    return 0;
}

/*** For testing IMU only ***/
#if 0

#define IMU_THREAD_STACK_SIZE 1024
#define IMU_THREAD_PRIORITY   5

static int imu_sample_interval_ms = 250;
static struct k_thread imu_thread_data;
static K_THREAD_STACK_DEFINE(imu_thread_stack, IMU_THREAD_STACK_SIZE);

static void imu_thread_fn(void *p1, void *p2, void *p3)
{
    int ret;
    struct sensor_value accel_data[3];
    struct sensor_value gyro_data[3];
    struct sensor_value odr_attr;

    /* set accel/gyro sampling frequency */
    odr_attr.val1 = 26; // 26 Hz
    odr_attr.val2 = 0;

    if (!device_is_ready(accel_dev)) {
        printk("IMU device not ready\n");
        return;
    }

    ret = sensor_attr_set(accel_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
    if (ret) {
        printk("Failed to set accel ODR\n");
        return;
    }

    ret = sensor_attr_set(accel_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
    if (ret) {
        printk("Failed to set gyro ODR\n");
        return;
    }

    while (1) {
        ret = sensor_sample_fetch(accel_dev);
        if (ret) {
            printk("Failed to fetch IMU sample\n");
            k_sleep(K_MSEC(imu_sample_interval_ms));
            continue;
        }

        ret = sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_XYZ, accel_data);
        (void)ret;
        ret = sensor_channel_get(accel_dev, SENSOR_CHAN_GYRO_XYZ, gyro_data);
        (void)ret;

        LOG_INF( "imu: accel %0.3f, %0.3f, %0.3f,  gyro %0.3f, %0.3f, %0.3f",
            sensor_value_to_float( &accel_data[0]), sensor_value_to_float( &accel_data[1]), sensor_value_to_float( &accel_data[2]),
            sensor_value_to_float( &gyro_data[0]), sensor_value_to_float( &gyro_data[1]), sensor_value_to_float( &gyro_data[2])
        );

        k_sleep(K_MSEC(imu_sample_interval_ms));
    }
}

/* Call this once to start the IMU thread */
static void imu_thread_start(void)
{
    k_thread_create(&imu_thread_data, imu_thread_stack,
        K_THREAD_STACK_SIZEOF(imu_thread_stack),
        imu_thread_fn,
        NULL, NULL, NULL,
        IMU_THREAD_PRIORITY, 0, K_NO_WAIT);
}

#endif

// Optionally, an "imu get" command can be added on to the shell
// TODO: decide if this should be optional in the main FW, or relegated ONLY to EVT/factory fw
#if defined(CONFIG_SHELL)
#include <zephyr/shell/shell.h>

static int cmd_imu_get(const struct shell *sh, size_t argc, char **argv)
{
    int ret;
    struct sensor_value accel_data[3];
    struct sensor_value gyro_data[3];
    struct sensor_value odr_attr;
    /* set accel/gyro sampling frequency to 12.5 Hz */
    odr_attr.val1 = 12.5;
    odr_attr.val2 = 0;

    if (!device_is_ready(accel_dev)) {
        shell_error(sh, "Device not ready\n");
        return -ENODEV;
    }

    ret = sensor_attr_set(accel_dev, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
    if (ret)
    {
        shell_error(sh, "Failed to set accel sampling frequency\n");
        return ret;
    }

    ret = sensor_attr_set(accel_dev, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr_attr);
    if (ret)
    {
        shell_error(sh, "Failed to set gyro sampling frequency\n");
        return ret;
    }

    ret = sensor_sample_fetch(accel_dev);
    if (ret)
    {
        shell_error(sh, "Failed to fetch sample\n");
        return ret;
    }

    ret = sensor_channel_get(accel_dev, SENSOR_CHAN_ACCEL_XYZ, accel_data);
    if (ret)
    {
        shell_error(sh, "Failed to get accel data\n");
        return ret;
    }

    ret = sensor_channel_get(accel_dev, SENSOR_CHAN_GYRO_XYZ, gyro_data);
    if (ret)
    {
        shell_error(sh, "Failed to get gyro data\n");
        return ret;
    }

    shell_print(sh, "imu: accel %0.3f, %0.3f, %0.3f,  gyro %0.3f, %0.3f, %0.3f",
        sensor_value_to_float( &accel_data[0]), sensor_value_to_float( &accel_data[1]), sensor_value_to_float( &accel_data[2]),
        sensor_value_to_float( &gyro_data[0]), sensor_value_to_float( &gyro_data[1]), sensor_value_to_float( &gyro_data[2])
    );

    return ret;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_imu_cmds,
                               SHELL_CMD(get, NULL, "Get IMU data", cmd_imu_get),
                               SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(imu, &sub_imu_cmds, "Get IMU data", NULL);

#endif