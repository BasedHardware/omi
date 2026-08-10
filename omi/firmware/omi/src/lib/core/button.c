#include "button.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/input/input.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/pm/device_runtime.h>
#include <zephyr/sys/poweroff.h>

#include "button_gesture.h"
#include "haptic.h"
#include "imu.h"
#include "led.h"
#include "mic.h"
#include "speaker.h"
#include "transport.h"
#include "wdog_facade.h"
#ifdef CONFIG_OMI_ENABLE_OFFLINE_STORAGE
#include "sd_card.h"
#endif

LOG_MODULE_REGISTER(button, CONFIG_LOG_DEFAULT_LEVEL);

extern bool is_off;

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t button_data_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);

static struct bt_uuid_128 button_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7924, 0x0000, 0x1000, 0x7450, 0x346EAC492E92));
static struct bt_uuid_128 button_characteristic_data_uuid =
    BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7925, 0x0000, 0x1000, 0x7450, 0x346EAC492E92));

static struct bt_gatt_attr button_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&button_uuid),
    BT_GATT_CHARACTERISTIC(&button_characteristic_data_uuid.uuid,
                           BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ,
                           button_data_read_characteristic,
                           NULL,
                           NULL),
    BT_GATT_CCC(button_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service button_service = BT_GATT_SERVICE(button_service_attr);

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value)
{
    if (value == BT_GATT_CCC_NOTIFY) {
        LOG_INF("Client subscribed for notifications");
    } else if (value == 0) {
        LOG_INF("Client unsubscribed from notifications");
    } else {
        LOG_ERR("Invalid CCC value: %u", value);
    }
}
static const struct device *const buttons = DEVICE_DT_GET(DT_ALIAS(buttons));
static const struct gpio_dt_spec usr_btn = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(usr_btn), gpios, {0});

static bool was_pressed = false;

// Using GPIO callback due to the lower priority of the input subsystem vs. storage.c's thread that prevents the
// callback from working properly.
#define BUTTON_CHECK_INTERVAL 40 // 0.04 seconds, 25 Hz

void check_button_level(struct k_work *work_item);

K_WORK_DELAYABLE_DEFINE(button_work, check_button_level);

#define DEFAULT_STATE 0
#define SINGLE_TAP 1
#define DOUBLE_TAP 2
#define LONG_TAP 3
#define BUTTON_PRESS 4
#define BUTTON_RELEASE 5

// 4 is button down, 5 is button up
static FSM_STATE_T current_button_state = IDLE;
static uint32_t inc_count_1 = 0;
static uint32_t inc_count_0 = 0;

static int final_button_state[2] = {0, 0};
const static int threshold = 10;

static void reset_count()
{
    inc_count_0 = 0;
    inc_count_1 = 0;
}
static inline void notify_press()
{
    final_button_state[0] = BUTTON_PRESS;
    LOG_INF("Button pressed");
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_gatt_notify(conn, &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
    }
}

static inline void notify_unpress()
{
    final_button_state[0] = BUTTON_RELEASE;
    LOG_INF("Button released");
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_gatt_notify(conn, &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
    }
}

static inline void notify_tap()
{
    final_button_state[0] = SINGLE_TAP;
    LOG_INF("Button single tap");
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_gatt_notify(conn, &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
    }
}

static inline void notify_double_tap()
{
    final_button_state[0] = DOUBLE_TAP; // button press
    LOG_INF("Button double tap");
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_gatt_notify(conn, &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
    }
}

static inline void notify_long_tap()
{
    final_button_state[0] = LONG_TAP; // button press
    LOG_INF("Button long tap");
    struct bt_conn *conn = get_current_connection();
    if (conn != NULL) {
        bt_gatt_notify(conn, &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
    }
}

static button_gesture_state_t gesture_state = {.tick_interval_ms = BUTTON_CHECK_INTERVAL};

K_THREAD_STACK_DEFINE(bond_clear_stack, 2048);
static struct k_work_q bond_clear_work_q;
static bool bond_clear_work_q_started;

static void clear_ble_bonds(void)
{
    LOG_INF("User requested BLE bond clear");

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    play_haptic_milli(100);
#endif

    set_led_blue(true);

    int err = transport_clear_bonds();
    if (err) {
        LOG_ERR("Bond clear failed (err %d)", err);
        set_led_red(true);
        k_msleep(500);
        led_off();
        return;
    }

    for (int i = 0; i < 3; i++) {
        set_led_blue(true);
        k_msleep(200);
        led_off();
        k_msleep(200);
    }

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    play_haptic_milli(50);
#endif
}

static void clear_ble_bonds_work(struct k_work *work)
{
    ARG_UNUSED(work);
    clear_ble_bonds();
}

static K_WORK_DEFINE(bond_clear_work, clear_ble_bonds_work);

static void schedule_clear_ble_bonds(void)
{
    if (!bond_clear_work_q_started) {
        k_work_queue_init(&bond_clear_work_q);
        k_work_queue_start(
            &bond_clear_work_q, bond_clear_stack, K_THREAD_STACK_SIZEOF(bond_clear_stack), K_PRIO_PREEMPT(8), NULL);
        k_thread_name_set(&bond_clear_work_q.thread, "bond_clear");
        bond_clear_work_q_started = true;
    }

    if (k_work_busy_get(&bond_clear_work) != 0) {
        LOG_WRN("Bond clear already in progress");
        return;
    }

    (void) k_work_submit_to_queue(&bond_clear_work_q, &bond_clear_work);
}

void check_button_level(struct k_work *work_item)
{
    button_gesture_result_t gesture = button_gesture_step(&gesture_state, was_pressed, k_uptime_get());

    switch (gesture.event) {
    case BUTTON_GESTURE_SINGLE_TAP:
        LOG_INF("single tap detected\n");
        notify_tap();
        break;

    case BUTTON_GESTURE_DOUBLE_TAP:
        LOG_INF("double tap detected\n");
        notify_double_tap();
        break;

    case BUTTON_GESTURE_LONG_PRESS:
        // A completed double-tap within the arm window is what turns this long press
        // into a bond clear; otherwise a long press is the ordinary power-off gesture.
        if (gesture.one_shot) {
            LOG_INF("long press detected\n");
            if (gesture.clear_bonds) {
                schedule_clear_ble_bonds();
            } else {
                turnoff_all();
            }
        }
        break;

    case BUTTON_GESTURE_RELEASE:
        if (gesture.one_shot) {
            LOG_PRINTK("release detected\n");
            notify_unpress();
        }
        current_button_state = GRACE;
        break;

    default:
        break;
    }

    k_work_reschedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));
}

static ssize_t button_data_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset)
{
    LOG_INF("button_data_read_characteristic");
    LOG_PRINTK("was_pressed: %d\n", final_button_state[0]);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &final_button_state, sizeof(final_button_state));
}

static struct gpio_callback button_cb_data;

static void button_gpio_callback(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    was_pressed = (gpio_pin_get_dt(&usr_btn) == 1);
    LOG_INF("Button %s (GPIO callback)", was_pressed ? "pressed" : "released");
}

int button_regist_callback()
{
    int ret;

    // Configure GPIO as input with pull-up
    ret = gpio_pin_configure_dt(&usr_btn, GPIO_INPUT);
    if (ret < 0) {
        LOG_ERR("Failed to configure button GPIO (%d)", ret);
        return ret;
    }

    // Setup interrupt on both edges
    ret = gpio_pin_interrupt_configure_dt(&usr_btn, GPIO_INT_EDGE_BOTH);
    if (ret < 0) {
        LOG_ERR("Failed to configure button interrupt (%d)", ret);
        return ret;
    }

    // Register callback
    gpio_init_callback(&button_cb_data, button_gpio_callback, BIT(usr_btn.pin));
    gpio_add_callback(usr_btn.port, &button_cb_data);

    LOG_INF("Button initialized with GPIO interrupt");

    return 0;
}

int button_init()
{
    int ret;

    // Initialize the buttons device from evt
    if (!device_is_ready(buttons)) {
        LOG_ERR("Buttons device not ready");
        return -ENODEV;
    }

    // Enable runtime power management for the buttons device
    ret = pm_device_runtime_get(buttons);
    if (ret < 0) {
        LOG_ERR("Failed to enable buttons device (%d)", ret);
        return ret;
    }

    // Regist callback
    ret = button_regist_callback();
    if (ret < 0) {
        LOG_ERR("Failed to register buttons callback (%d)", ret);
        return ret;
    }

    return 0;
}

void activate_button_work()
{
    k_work_schedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));
}

void register_button_service()
{
    bt_gatt_service_register(&button_service);
}

FSM_STATE_T get_current_button_state()
{
    return current_button_state;
}

void turnoff_all()
{
    int rc;

    // Immediate feedback: LED off and haptic
    led_off();
    // Set is_off immediately so set_led_state() keeps LEDs off
    is_off = true;

#ifdef CONFIG_OMI_ENABLE_HAPTIC
    play_haptic_milli(100);
    k_msleep(300);
    haptic_off();
#endif

    // Delays for stability
    k_msleep(1000);

    // // Enter the low power mode
    transport_off();
    k_msleep(300);

    // Always turn off microphone
    mic_off();
    k_msleep(100);

    // Turn off speaker if enabled
#ifdef CONFIG_OMI_ENABLE_SPEAKER
    speaker_off();
    k_msleep(100);
#endif

    // Turn off accelerometer if enabled
#ifdef CONFIG_OMI_ENABLE_ACCELEROMETER
    accel_off();
    k_msleep(100);
#endif

    if (is_sd_on()) {
        app_sd_off();
    }
    k_msleep(300);

    // Put the buttons device to sleep if button is enabled
#ifdef CONFIG_OMI_ENABLE_BUTTON
    pm_device_runtime_put(buttons);
    k_msleep(100);
#endif

    // Disable USB if enabled
#ifdef CONFIG_OMI_ENABLE_USB
    NRF_USBD->INTENCLR = 0xFFFFFFFF;
#endif

    // Log system power off
    LOG_INF("System powering off");

    // Configure usr_btn as input with interrupt to allow wake-up
    rc = gpio_pin_configure_dt(&usr_btn, GPIO_INPUT);
    if (rc < 0) {
        LOG_ERR("Could not configure usr_btn GPIO (%d)", rc);
        return;
    }

    rc = gpio_pin_interrupt_configure_dt(&usr_btn, GPIO_INT_LEVEL_LOW);
    if (rc < 0) {
        LOG_ERR("Could not configure usr_btn GPIO interrupt (%d)", rc);
        return;
    }
    rc = watchdog_deinit();
    if (rc < 0) {
        LOG_ERR("Failed to deinitialize watchdog (%d)", rc);
        return;
    }

    /* Persist an IMU timestamp base so we can estimate time across system_off. */
    lsm6dsl_time_prepare_for_system_off();
    k_msleep(1000);
    LOG_INF("Entering system off; press usr_btn to restart");

    // Power off the system using sys_poweroff
    sys_poweroff();
}

void force_button_state(FSM_STATE_T state)
{
    current_button_state = state;
}
