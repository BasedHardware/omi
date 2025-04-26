#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/logging/log.h>

static const struct gpio_dt_spec motor =
   GPIO_DT_SPEC_GET_OR(DT_NODELABEL(motor_pin), gpios, {0});

#define MAX_HAPTIC_DURATION 5000

LOG_MODULE_REGISTER(haptic, CONFIG_LOG_DEFAULT_LEVEL);

// Haptic Off Work Item
static struct k_work_delayable haptic_off_work;

// Work handler to turn off haptic motor
static void haptic_off_work_handler(struct k_work *work)
{
    haptic_off();
    LOG_INF("Haptic turned off by work handler");
}


// BLE Service definitions
static void haptic_ccc_cfg_changed(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t haptic_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags);

// Define a unique UUID for the Haptic Service
static struct bt_uuid_128 haptic_service_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB95, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));
static struct bt_uuid_128 haptic_char_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0xCAB1AB96, 0x2EA5, 0x4F4D, 0xBB56, 0x874B72CFC984));

// Define the Haptic GATT Service structure
static struct bt_gatt_attr haptic_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&haptic_service_uuid),
    BT_GATT_CHARACTERISTIC(&haptic_char_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL, haptic_write_handler, NULL),
};

static struct bt_gatt_service haptic_service = BT_GATT_SERVICE(haptic_attrs);

// Haptic Write Handler
static ssize_t haptic_write_handler(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{
    if (len < 1) {
        LOG_WRN("Haptic write: Invalid length %d", len);
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    uint8_t value = ((uint8_t*)buf)[0];
    LOG_INF("Haptic write received: value %d", value);

    // Map received value to haptic duration
    // 1 -> 100ms, 2 -> 300ms, 3 -> 500ms
    switch (value) {
        case 1:
            play_haptic_milli(100);
            break;
        case 2:
            play_haptic_milli(300);
            break;
        case 3:
            play_haptic_milli(500);
            break;
        default:
            LOG_WRN("Haptic write: Invalid value %d", value);
            return len;
    }

    return len;
}

// Public Functions

int init_haptic_pin()
{
    if (!gpio_is_ready_dt(&haptic_pin)) {
        LOG_ERR("Haptic GPIO device %s is not ready", haptic_pin.port->name);
        return -ENODEV;
    }
    
	if (gpio_pin_configure_dt(&motor, GPIO_OUTPUT_INACTIVE) < 0)
    {
		LOG_ERR("Error setting up Haptic Pin");
        return -1;
	}

    gpio_pin_set_dt(&motor, 0);

    // Initialize the delayable work item
    k_work_init_delayable(&haptic_off_work, haptic_off_work_handler);

    return 0;
}

void play_haptic_milli(uint32_t duration)
{
if (!gpio_is_ready_dt(&haptic_pin)) {
        LOG_ERR("Haptic GPIO device not ready");
        return;
    }
    
    if (duration > MAX_HAPTIC_DURATION)
    {
        LOG_ERR("Duration is too long");
        return;
    }

    // Cancel any pending off work before proceeding
    k_work_cancel_delayable(&haptic_off_work);

    if (duration == 0) {
        // If duration is 0, ensure the pin is off and we are done.
        gpio_pin_set_dt(&haptic_pin, 0);
        LOG_INF("Haptic explicitly stopped (duration 0)");
        return;
    }

    // Configure GPIO pin just before turning it on
    int err = gpio_pin_configure_dt(&haptic_pin, GPIO_OUTPUT);
    if (err) {
        LOG_ERR("Failed to configure haptic pin for output (err %d)", err);
        return;
    }


    if (duration > MAX_HAPTIC_DURATION) {
        LOG_WRN("Requested haptic duration %u exceeds max %d, capping.", duration, MAX_HAPTIC_DURATION);
        duration = MAX_HAPTIC_DURATION;
    }

    LOG_INF("Playing haptic for %u ms", duration);
    gpio_pin_set_dt(&haptic_pin, 1);
    // Schedule the work item to turn the haptic off after the duration
    k_work_schedule(&haptic_off_work, K_MSEC(duration));
}

void register_haptic_service(void)
{
    int err = bt_gatt_service_register(&haptic_service);
    if (err) {
        LOG_ERR("Failed to register Haptic GATT service (err %d)", err);
    } else {
        LOG_INF("Haptic GATT service registered");
    }
}

void haptic_off()
{
    gpio_pin_set_dt(&haptic_pin, 0);
}