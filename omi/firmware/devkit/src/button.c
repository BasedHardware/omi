#include "button.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/poweroff.h>

#include "led.h"
#include "mic.h"
#include "sdcard.h"
#include "speaker.h"
#include "transport.h"
#include "wdog_facade.h"
LOG_MODULE_REGISTER(button, CONFIG_LOG_DEFAULT_LEVEL);

bool is_off = false;
static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t button_data_read_characteristic(struct bt_conn *conn,
                                               const struct bt_gatt_attr *attr,
                                               void *buf,
                                               uint16_t len,
                                               uint16_t offset);
static struct gpio_callback button_cb_data;

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
struct gpio_dt_spec d4_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                              .pin = 4,
                              .dt_flags = GPIO_OUTPUT_ACTIVE}; // 3.3
struct gpio_dt_spec d5_pin_input = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)),
                                    .pin = 5,
                                    .dt_flags = GPIO_INT_EDGE_RISING};

static bool was_pressed = false;

//
// button
//
void button_pressed_callback(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    int temp = gpio_pin_get_raw(dev, d5_pin_input.pin);
    LOG_PRINTK("button_pressed_callback %d\n", temp);
    if (temp) {
        was_pressed = false;
    } else {
        was_pressed = true;
    }
}
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

#define BUTTON_PRESSED 1
#define BUTTON_RELEASED 0

#define TAP_THRESHOLD 300     // 300 ms for single tap
#define DOUBLE_TAP_WINDOW 600 // 600 ms maximum for double-tap
#define LONG_PRESS_TIME 1000  // 1000 ms for long press

typedef enum {
    BUTTON_EVENT_NONE,
    BUTTON_EVENT_SINGLE_TAP,
    BUTTON_EVENT_DOUBLE_TAP,
    BUTTON_EVENT_LONG_PRESS,
    BUTTON_EVENT_RELEASE
} ButtonEvent;

static uint32_t current_time = 0;
static uint32_t btn_press_start_time;
static uint32_t btn_release_time;
static uint32_t btn_last_tap_time;
static bool btn_is_pressed;

static u_int8_t btn_last_event = BUTTON_EVENT_NONE;

void check_button_level(struct k_work *work_item)
{
    current_time = current_time + 1;

    u_int8_t btn_state = was_pressed ? BUTTON_PRESSED : BUTTON_RELEASED;

    ButtonEvent event = BUTTON_EVENT_NONE;

    // Debouncing pressed state
    if (btn_state == BUTTON_PRESSED && !btn_is_pressed) {
        btn_is_pressed = true;
        btn_press_start_time = current_time;
    } else if (btn_state == BUTTON_RELEASED && btn_is_pressed) {
        btn_is_pressed = false;
        btn_release_time = current_time;

        // Check for double tap
        uint32_t press_duration = (btn_release_time - btn_press_start_time) * BUTTON_CHECK_INTERVAL;
        if (press_duration < TAP_THRESHOLD) {
            if (btn_last_tap_time > 0 &&
                (current_time - btn_last_tap_time) * BUTTON_CHECK_INTERVAL < DOUBLE_TAP_WINDOW) {
                event = BUTTON_EVENT_DOUBLE_TAP;
                btn_last_tap_time = 0; // Reset double-tap / single-tap detection
            } else {
                btn_last_tap_time = current_time;
            }
        }
    }

    // Check for single tap
    if (btn_state == BUTTON_RELEASED && !btn_is_pressed) {
        uint32_t press_duration = (btn_release_time - btn_press_start_time) * BUTTON_CHECK_INTERVAL;
        if (press_duration < TAP_THRESHOLD && btn_last_tap_time > 0 &&
            (current_time - btn_press_start_time) * BUTTON_CHECK_INTERVAL > TAP_THRESHOLD) {
            event = BUTTON_EVENT_SINGLE_TAP;
            btn_last_tap_time = 0;
        } else if ((current_time - btn_press_start_time) * BUTTON_CHECK_INTERVAL > TAP_THRESHOLD) {
            event = BUTTON_EVENT_RELEASE;
        }
    }

    // Check for long press
    if (btn_is_pressed && (current_time - btn_press_start_time) * BUTTON_CHECK_INTERVAL >= LONG_PRESS_TIME) {
        event = BUTTON_EVENT_LONG_PRESS;
    }

    // Single tap
    if (event == BUTTON_EVENT_SINGLE_TAP) {
        LOG_PRINTK("single tap detected\n");
        btn_last_event = event;
        notify_tap();

        // Enter the low power mode
        is_off = true;
        bt_off();
        turnoff_all();
    }

    // Double tap
    if (event == BUTTON_EVENT_DOUBLE_TAP) {
        LOG_PRINTK("double tap detected\n");
        btn_last_event = event;
        notify_double_tap();
    }

    // Long press, one time event
    if (event == BUTTON_EVENT_LONG_PRESS && btn_last_event != BUTTON_EVENT_LONG_PRESS) {
        LOG_PRINTK("long press detected\n");
        btn_last_event = event;
        notify_long_tap();
    }

    // Releases, one time event
    if (event == BUTTON_EVENT_RELEASE && btn_last_event != BUTTON_EVENT_RELEASE) {
        LOG_PRINTK("release detected\n");
        btn_last_event = event;
        notify_unpress();

        // Reset
        current_time = 0;
        btn_press_start_time = 0;
        btn_release_time = 0;
        btn_last_tap_time = 0;
    }
    if (event == BUTTON_EVENT_RELEASE) {
        current_button_state = GRACE;
    }

    k_work_reschedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));
    return 0;
}

// @deprecated
// #define LONG_PRESS_INTERVAL 25
// #define SINGLE_PRESS_INTERVAL 2
// void check_button_level_2(struct k_work *work_item)
//{
//     //insert the current button state here
//    int state_ = was_pressed ? 1 : 0;
//    if (current_button_state == IDLE)
//    {
//        if (state_ == 0)
//        {
//            //Do nothing!
//        }
//        else if (state_ == 1)
//        {
//            //Also do nothing, but transition to the next state
//            notify_press();
//            current_button_state = ONE_PRESS;
//            if (is_off)
//           {
//             is_off = false;
//             bt_on();
//             play_haptic_milli(50);
//           }
//        }
//    }
//
//    else if (current_button_state == ONE_PRESS)
//    {
//        if (state_ == 0)
//        {
//
//            if(inc_count_0 == 0)
//            {
//                notify_unpress();
//            }
//            inc_count_0++; //button is unpressed
//            if (inc_count_0 > SINGLE_PRESS_INTERVAL)
//            {
//                //If button is not pressed for a little while.......
//                //transition to Two_press. button could be a single or double tap
//                current_button_state = TWO_PRESS;
//                reset_count();
//            }
//        }
//        if (state_ == 1)
//        {
//            inc_count_1++; //button is pressed
//
//            if (inc_count_1 > LONG_PRESS_INTERVAL)
//            {
//                //If button is pressed for a long time.......
//                notify_long_tap();
//                //play_haptic_milli(10);
//                //Fire the long mode notify and enter a grace period
//                //turn off herre
//                // TODO: FIXME
//                //if(!from_wakeup)
//                //{
//                //    is_off = !is_off;
//                //}
//                //else
//                //{
//                //    from_wakeup = false;
//                //}
//                //if (is_off)
//                //{
//                //    bt_off();
//                //    turnoff_all();
//                //}
//                current_button_state = GRACE;
//                reset_count();
//            }
//
//        }
//
//    }
//
//    else if (current_button_state == TWO_PRESS)
//    {
//        if (state_ == 0)
//        {
//            if (inc_count_1 > 0)
//            { // if button has been pressed......
//                notify_unpress();
//                notify_double_tap();
//
//                //Fire the notify and enter a grace period
//                current_button_state = GRACE;
//                reset_count();
//            }
//             //single button press
//            else if (inc_count_0 > 10)
//            {
//                notify_tap(); //Fire the notify and enter a grace period
//                if(!from_wakeup)
//                {
//                    is_off = !is_off;
//                }
//                else
//                {
//                    from_wakeup = false;
//                }
//                //Fire the notify and enter a grace period
//                if (is_off)
//                {
//                    bt_off();
//                    turnoff_all();
//                }
//                current_button_state = GRACE;
//                reset_count();
//            }
//            else
//            {
//                inc_count_0++; //not pressed
//            }
//        }
//        else if (state_ == 1 )
//        {
//            if (inc_count_1 == 0)
//            {
//                notify_press();
//                inc_count_1++;
//            }
//            if (inc_count_1 > threshold)
//            {
//                notify_long_tap();
//                //play_haptic_milli(10);
//                // TODO: FIXME
//                //if(!from_wakeup)
//                //{
//                //    is_off = !is_off;
//                //}
//                //else
//                //{
//                //    from_wakeup = false;
//                //}
//                ////Fire the notify and enter a grace period
//                //if (is_off)
//                //{
//                //    bt_off();
//                //    turnoff_all();
//                //}
//                current_button_state = GRACE;
//                reset_count();
//            }
//        }
//    }
//
//    else if (current_button_state == GRACE)
//    {
//        if (state_ == 0)
//        {
//            if (inc_count_0 == 0 && (inc_count_1 > 0))
//            {
//                notify_unpress();
//            }
//            inc_count_0++;
//            if (inc_count_0 > 1)
//            {
//                current_button_state = IDLE;
//                reset_count();
//            }
//        }
//        else if (state_ == 1)
//        {
//            inc_count_1++;
//        }
//    }
//    k_work_reschedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));
//}

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

int button_init()
{
    if (gpio_is_ready_dt(&d4_pin)) {
        LOG_INF("D4 Pin ready");
    } else {
        LOG_ERR("Error setting up D4 Pin");
        return -1;
    }
    if (gpio_pin_configure_dt(&d4_pin, GPIO_OUTPUT_ACTIVE) < 0) {
        LOG_ERR("Error setting up D4 Pin Voltage");
        return -1;
    } else {
        LOG_INF("D4 ready to transmit voltage");
    }
    if (gpio_is_ready_dt(&d5_pin_input)) {
        LOG_INF("D5 Pin ready");
    } else {
        LOG_ERR("D5 Pin not ready");
        return -1;
    }

    int err2 = gpio_pin_configure_dt(&d5_pin_input, GPIO_INPUT);

    if (err2 != 0) {
        LOG_ERR("Error setting up D5 Pin");
        return -1;
    } else {
        LOG_INF("D5 ready");
    }
    // GPIO_INT_LEVEL_INACTIVE
    err2 = gpio_pin_interrupt_configure_dt(&d5_pin_input, GPIO_INT_EDGE_BOTH);

    if (err2 != 0) {
        LOG_ERR("D5 unable to detect button presses");
        return -1;
    } else {
        LOG_INF("D5 ready to detect button presses");
    }

    gpio_init_callback(&button_cb_data, button_pressed_callback, BIT(d5_pin_input.pin));
    gpio_add_callback(d5_pin_input.port, &button_cb_data);

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

    mic_off();
    sd_off();
    speaker_off();
    accel_off();
    play_haptic_milli(50);
    k_msleep(100);
    set_led_blue(false);
    set_led_red(false);
    set_led_green(false);
    gpio_remove_callback(d5_pin_input.port, &button_cb_data);
    gpio_pin_interrupt_configure_dt(&d5_pin_input, GPIO_INT_LEVEL_INACTIVE);

    // Disable watchdog before entering system off
    int rc = watchdog_deinit();
    if (rc < 0) {
        LOG_ERR("Failed to deinitialize watchdog (%d)", rc);
    }

    // maybe save something here to indicate success. next time the button is pressed we should know about it
    NRF_USBD->INTENCLR = 0xFFFFFFFF;
    NRF_POWER->SYSTEMOFF = 1;
}

void force_button_state(FSM_STATE_T state)
{
    current_button_state = state;
}
