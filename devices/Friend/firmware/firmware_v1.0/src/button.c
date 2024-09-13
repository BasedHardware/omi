#include <zephyr/logging/log.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/bluetooth/services/bas.h>
#include "transport.h"
#include "button.h"
LOG_MODULE_REGISTER(button, CONFIG_LOG_DEFAULT_LEVEL);

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value);
static ssize_t button_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset);
static struct gpio_callback button_cb_data;

static struct bt_uuid_128 button_uuid = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7924,0x0000,0x1000,0x7450,0x346EAC492E92));
static struct bt_uuid_128 button_uuid_x = BT_UUID_INIT_128(BT_UUID_128_ENCODE(0x23BA7925 ,0x0000,0x1000,0x7450,0x346EAC492E92));

static struct bt_gatt_attr button_service_attr[] = {
    BT_GATT_PRIMARY_SERVICE(&button_uuid),
    BT_GATT_CHARACTERISTIC(&button_uuid_x.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY, BT_GATT_PERM_READ, button_data_read_characteristic, NULL, NULL),
    BT_GATT_CCC(button_ccc_config_changed_handler, BT_GATT_PERM_READ | BT_GATT_PERM_WRITE),
};

static struct bt_gatt_service button_service = BT_GATT_SERVICE(button_service_attr);

static void button_ccc_config_changed_handler(const struct bt_gatt_attr *attr, uint16_t value) {
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
struct gpio_dt_spec d4_pin = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=4, .dt_flags = GPIO_OUTPUT_ACTIVE}; //3.3
struct gpio_dt_spec d5_pin_input = {.port = DEVICE_DT_GET(DT_NODELABEL(gpio0)), .pin=5, .dt_flags = GPIO_INT_EDGE_RISING};

static uint32_t current_button_time = 0;
static uint32_t previous_button_time = 0;

const int max_debounce_interval = 700;
static bool was_pressed = false;

//
// button
//
void button_pressed(const struct device *dev, struct gpio_callback *cb,
		    uint32_t pins)
{
    current_button_time = k_cycle_get_32();
	if (current_button_time - previous_button_time < max_debounce_interval) { //too low!
	}
	else { //right...    
        int temp = gpio_pin_get_raw(dev,d5_pin_input.pin);
        if (temp) {
            was_pressed = true;
        }
        else {
            was_pressed = false;
        }
	}
	previous_button_time = current_button_time;
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


static int final_button_state[2] = {0,0};
const static int threshold = 10;


static void reset_count() {
    inc_count_0 = 0;
    inc_count_1 = 0;
}
static void notify_press() {
    final_button_state[0] = BUTTON_PRESS;
    LOG_INF("pressed");
    bt_gatt_notify(get_current_connection(), &button_service.attrs[1], &final_button_state, sizeof(final_button_state));
}

static void notify_unpress() {
    final_button_state[0] = BUTTON_RELEASE; 
    LOG_INF("unpressed");
    bt_gatt_notify(get_current_connection(), &button_service.attrs[1], &final_button_state, sizeof(final_button_state));  
}

static void notify_tap() {
      final_button_state[0] = SINGLE_TAP;
    LOG_INF("tap");
    bt_gatt_notify(get_current_connection(), &button_service.attrs[1], &final_button_state, sizeof(final_button_state));  
}

static void notify_double_tap() {
      final_button_state[0] = DOUBLE_TAP; //button press
    LOG_INF("double tap");
    bt_gatt_notify(get_current_connection(), &button_service.attrs[1], &final_button_state, sizeof(final_button_state));  
}

static void notify_long_tap() {
    final_button_state[0] = LONG_TAP; //button press
    LOG_INF("long tap");
    bt_gatt_notify(get_current_connection(), &button_service.attrs[1], &final_button_state, sizeof(final_button_state));  
}

#define LONG_PRESS_INTERVAL 50
#define SINGLE_PRESS_INTERVAL 2
void check_button_level(struct k_work *work_item) {
    if (get_current_connection() == NULL)  {
        return;
    }

     //insert the current button state here
    int state_ = was_pressed ? 1 : 0;
    if (current_button_state == IDLE) {

        if (state_ == 0) {
            //Do nothing!
        }

        else if (state_ == 1) {
            //Also do nothing, but transition to the next state
            notify_press();
            current_button_state = ONE_PRESS;
        }

    }

    else if (current_button_state == ONE_PRESS) {

        if (state_ == 0) {
            
            if(inc_count_0 == 0) {
            notify_unpress();
            }
            inc_count_0++; //button is unpressed
            if (inc_count_0 > SINGLE_PRESS_INTERVAL) {
                //If button is not pressed for a little while....... 
                //transition to Two_press. button could be a single or double tap
                current_button_state = TWO_PRESS;
                reset_count();          
            }
        }
        if (state_ == 1) {
            inc_count_1++; //button is pressed

            if (inc_count_1 > LONG_PRESS_INTERVAL) {
                //If button is pressed for a long time.......
                notify_long_tap();
                //Fire the long mode notify and enter a grace period
                current_button_state = GRACE;
                reset_count();
            }

        }

    }

    else if (current_button_state == TWO_PRESS) {

        if (state_ == 0) {
             
                if (inc_count_1 > 0) { // if button has been pressed......
                notify_unpress();
                notify_double_tap();
                
                //Fire the notify and enter a grace period
                current_button_state = GRACE;
                reset_count();
             }
             //single button press
            else if (inc_count_0 > 10){
                notify_tap(); //Fire the notify and enter a grace period
                current_button_state = GRACE;
                reset_count();

             }
             else {
                inc_count_0++; //not pressed
             }
        }
        else if (state_ == 1 ) {
            if (inc_count_1 == 0) {
                notify_press();
                inc_count_1++;
            }
            if (inc_count_1 > threshold) {
                notify_long_tap();
                //Fire the notify and enter a grace period
                current_button_state = GRACE;
                reset_count();
            }
        }
    }

    else if (current_button_state == GRACE) {
        if (state_ == 0) {
            if (inc_count_0 == 0 && (inc_count_1 > 0)) {
            notify_unpress();
            }
            inc_count_0++;
            if (inc_count_0 > 10) {
            current_button_state = IDLE;
            reset_count();
            }
        }
        else if (state_ == 1) {
              inc_count_1++;
        }
    }

    k_work_reschedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));

}


static ssize_t button_data_read_characteristic(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf, uint16_t len, uint16_t offset) {
     LOG_INF("button_data_read_characteristic");
     int lint = 1;
     LOG_INF("was_pressed: %d", was_pressed);
    return bt_gatt_attr_read(conn, attr, buf, len, offset, &lint, sizeof(lint));

}
int button_init() {
    	if (gpio_is_ready_dt(&d4_pin)) {
		LOG_INF("D4 Pin ready");
	}
    	else {
		LOG_ERR("Error setting up D4 Pin");
        return 0;
	}

	if (gpio_pin_configure_dt(&d4_pin, GPIO_OUTPUT_ACTIVE) < 0) {
		LOG_ERR("Error setting up D4 Pin Voltage");
        return 0;
	}
	else {
		LOG_INF("D4 ready to transmit voltage");
	}
	if (gpio_is_ready_dt(&d5_pin_input)) {
		LOG_INF("D5 Pin ready");
	}
	else {
		LOG_ERR("D5 Pin not ready");
        return 0;
	}

	int err2 = gpio_pin_configure_dt(&d5_pin_input,GPIO_INPUT);

	if (err2 != 0) {
		LOG_ERR("Error setting up D5 Pin");
		return 0;
	}
	else {
		LOG_INF("D5 ready");
	}
	err2 =  gpio_pin_interrupt_configure_dt(&d5_pin_input,GPIO_INT_EDGE_BOTH);

	if (err2 != 0) {
		LOG_ERR("D5 unable to detect button presses");
		return 0;
	}
	else {
		LOG_INF("D5 ready to detect button presses");
	}

    gpio_init_callback(&button_cb_data, button_pressed, BIT(d5_pin_input.pin));
	gpio_add_callback(d5_pin_input.port, &button_cb_data);

    return 1;
}

void activate_button_work() {
     k_work_schedule(&button_work, K_MSEC(BUTTON_CHECK_INTERVAL));
}

void register_button_service() {
    bt_gatt_service_register(&button_service);
}

FSM_STATE_T get_current_button_state() {
    return current_button_state;
}