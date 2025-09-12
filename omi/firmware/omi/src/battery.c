#include "lib/dk2/lib/battery/battery.h"

#include <hal/nrf_saadc.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(battery, CONFIG_LOG_DEFAULT_LEVEL);

#define BATTERY_STATES_COUNT 16

#define ADC_TOTAL_SAMPLES 50
// +1 for the calibration sample
int16_t sample_buffer[ADC_TOTAL_SAMPLES + 1];

#define ADC_RESOLUTION 12
#define ADC_GAIN ADC_GAIN_1_3
#define ADC_REFERENCE ADC_REF_INTERNAL
#define ADC_ACQUISITION_TIME ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)
#define ADC_1ST_CHANNEL_ID 0
#define ADC_1ST_CHANNEL_INPUT NRF_SAADC_INPUT_AIN0

static const struct device *const adc_dev = DEVICE_DT_GET(DT_NODELABEL(adc));
static const struct gpio_dt_spec power_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(power_pin), gpios, {0});
static const struct gpio_dt_spec bat_read_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_read_pin), gpios, {0});
static const struct gpio_dt_spec bat_chg_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});

static struct gpio_callback bat_chg_cb;

static K_MUTEX_DEFINE(battery_mut);

// 150mAh LiPo battery discharge profile
typedef struct {
    uint16_t millivolts;
    uint8_t percentage;
} BatteryState;

BatteryState battery_states[BATTERY_STATES_COUNT] = {
    {4200, 100},
    {4160, 99},
    {4090, 91},
    {4030, 78},
    {3890, 63},
    {3830, 53},
    {3680, 36},
    {3660, 35},
    {3480, 14},
    {3420, 11},
    {3400, 1}, // Threshold for <1%
    {0000, 0}  // Below safe level
};

extern bool is_charging;

// Moving average filter for voltage smoothing
static uint16_t voltage_history[5];
static uint8_t history_index = 0;
static bool history_initialized = false;

static const struct adc_channel_cfg m_1st_channel_cfg = {
    .gain = ADC_GAIN,
    .reference = ADC_REFERENCE,
    .acquisition_time = ADC_ACQUISITION_TIME,
    .channel_id = ADC_1ST_CHANNEL_ID,
#if defined(CONFIG_ADC_CONFIGURABLE_INPUTS)
    .input_positive = ADC_1ST_CHANNEL_INPUT,
#endif
};

// Define ADC sequence for this read operation
const struct adc_sequence_options sequence_opts = {
    .extra_samplings = ADC_TOTAL_SAMPLES,
    .interval_us = 0,
    .callback = NULL,
    .user_data = NULL,
};

struct adc_sequence sequence = {
    .options = &sequence_opts,
    .channels = BIT(ADC_1ST_CHANNEL_ID),
    .buffer = sample_buffer,
    .buffer_size = sizeof(sample_buffer),
    .resolution = ADC_RESOLUTION,
};

static void battery_charging_callback(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    int err = battery_charging_state_read();
    if (err) {
        LOG_ERR("Failed to read charging state (%d)", err);
    }
}

int battery_get_millivolt(uint16_t *battery_millivolt)
{
    int err;

    // Voltage divider circuit
    // based on practical measurements adjusted on the omi device
    const uint16_t R1 = 1091;
    const uint16_t R2 = 499;

    k_mutex_lock(&battery_mut, K_FOREVER);

    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1);
    if (err < 0) {
        LOG_ERR("Failed to configure bat_read_pin to output: %d", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }

    // Set pin low to enable battery voltage measurement path
    gpio_pin_set(bat_read_pin.port, bat_read_pin.pin, 0);

    if (!device_is_ready(adc_dev)) {
        LOG_ERR("ADC device %s is not ready", adc_dev->name);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        k_mutex_unlock(&battery_mut);
        return -ENODEV;
    }

    err = adc_channel_setup(adc_dev, &m_1st_channel_cfg);
    if (err) {
        LOG_ERR("ADC channel setup failed (error %d)", err);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        k_mutex_unlock(&battery_mut);
        return err;
    }

    // Trigger offset calibration. The first sample after this will be affected.
    NRF_SAADC_S->TASKS_CALIBRATEOFFSET = 1;
    k_busy_wait(100); // Short delay for calibration, if needed.

    err = adc_read(adc_dev, &sequence);
    if (err) {
        LOG_WRN("ADC read failed (error %d)", err);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        k_mutex_unlock(&battery_mut);
        return err;
    }

    // Calculate median of valid samples, discarding the first one (post-calibration)
    // Copy samples to a temporary array for sorting
    int16_t sorted_samples[ADC_TOTAL_SAMPLES];
    for (int i = 0; i < ADC_TOTAL_SAMPLES; i++) {
        sorted_samples[i] = sample_buffer[i + 1];
    }

    // Simple bubble sort for median calculation
    for (int i = 0; i < ADC_TOTAL_SAMPLES - 1; i++) {
        for (int j = 0; j < ADC_TOTAL_SAMPLES - i - 1; j++) {
            if (sorted_samples[j] > sorted_samples[j + 1]) {
                int16_t temp = sorted_samples[j];
                sorted_samples[j] = sorted_samples[j + 1];
                sorted_samples[j + 1] = temp;
            }
        }
    }

    // Calculate median
    int32_t adc_raw_val;
    if (ADC_TOTAL_SAMPLES % 2 == 0) {
        adc_raw_val = (sorted_samples[ADC_TOTAL_SAMPLES / 2 - 1] + sorted_samples[ADC_TOTAL_SAMPLES / 2]) / 2;
    } else {
        adc_raw_val = sorted_samples[ADC_TOTAL_SAMPLES / 2];
    }

    LOG_INF("Median ADC raw (after discarding 1st of %d total): %d", ADC_TOTAL_SAMPLES + 1, adc_raw_val);

    // Convert median ADC value to millivolts at the ADC pin
    uint16_t adc_vref_mv = adc_ref_internal(adc_dev);
    err = adc_raw_to_millivolts(adc_vref_mv, ADC_GAIN, ADC_RESOLUTION, &adc_raw_val);
    if (err) {
        LOG_WRN("ADC raw to millivolts conversion failed (error %d)", err);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        k_mutex_unlock(&battery_mut);
        return err;
    }
    LOG_INF("ADC mV at pin (after conversion): %d, charging: %s", adc_raw_val, is_charging ? "true" : "false");

    // Sub 16mV when charging to correct voltage skew
    // based on practical measurements adjusted on the omi device
    if (is_charging) {
        adc_raw_val -= 16;
    }

    // Calculate battery voltage using the voltage divider formula
    uint16_t raw_battery_millivolt = (uint16_t) (adc_raw_val * ((float) (R1 + R2) / R2));

    // Apply moving average filter for smoother readings
    voltage_history[history_index] = raw_battery_millivolt;
    history_index = (history_index + 1) % 5;

    // Fill all history slots with the first reading
    if (!history_initialized) {
        for (int i = 0; i < 5; i++) {
            voltage_history[i] = raw_battery_millivolt;
        }
        history_initialized = true;
    }

    // Calculate moving average
    uint32_t sum = 0;
    for (int i = 0; i < 5; i++) {
        sum += voltage_history[i];
    }
    *battery_millivolt = (uint16_t) (sum / 5);

    LOG_INF("Raw battery millivolt: %u mV, Filtered: %u mV", raw_battery_millivolt, *battery_millivolt);

    // Restore bat_read_pin to INPUT state to save power/avoid affecting other circuits
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (err < 0) {
        LOG_ERR("Failed to configure bat_read_pin to input: %d", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }

    k_mutex_unlock(&battery_mut);

    return 0;
}

int battery_get_percentage(uint8_t *battery_percentage, uint16_t battery_millivolt)
{
    // Use the battery discharge profile to determine percentage
    if (battery_millivolt >= battery_states[0].millivolts) {
        *battery_percentage = battery_states[0].percentage;
        return 0;
    }

    if (battery_millivolt <= battery_states[BATTERY_STATES_COUNT - 1].millivolts) {
        *battery_percentage = battery_states[BATTERY_STATES_COUNT - 1].percentage;
        return 0;
    }

    // Find the appropriate range in the battery profile
    for (int i = 0; i < BATTERY_STATES_COUNT - 1; i++) {
        if (battery_millivolt <= battery_states[i].millivolts && battery_millivolt > battery_states[i + 1].millivolts) {

            // Linear interpolation between the two closest points
            uint16_t voltage_range = battery_states[i].millivolts - battery_states[i + 1].millivolts;
            uint8_t percentage_range = battery_states[i].percentage - battery_states[i + 1].percentage;
            uint16_t voltage_diff = battery_states[i].millivolts - battery_millivolt;

            *battery_percentage = battery_states[i].percentage - (voltage_diff * percentage_range) / voltage_range;
            break;
        }
    }

    return 0;
}

int battery_charge_start()
{
    return 0;
}

int battery_charge_stop()
{
    return 0;
}

int battery_set_fast_charge()
{
    return 0;
}

int battery_set_slow_charge()
{
    return 0;
}

int battery_charging_state_read()
{
    if (gpio_pin_get(bat_chg_pin.port, bat_chg_pin.pin) == 0) {
        is_charging = true;
    } else {
        is_charging = false;
    }
    return 0;
}

int battery_enable_read()
{
    int err;

    // Perform voltage divider configs
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1);
    if (err < 0) {
        LOG_ERR("Failed to configure bat_read_pin to output: %d", err);
        return err;
    }

    // Set pin low to enable battery voltage measurement path
    gpio_pin_set(bat_read_pin.port, bat_read_pin.pin, 0);
    k_msleep(10);

    if (!device_is_ready(adc_dev)) {
        LOG_ERR("ADC device %s is not ready", adc_dev->name);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        return -ENODEV;
    }

    err = adc_channel_setup(adc_dev, &m_1st_channel_cfg);
    if (err) {
        LOG_ERR("ADC channel setup failed (error %d)", err);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        return err;
    }

    // Trigger offset calibration with proper settling time
    NRF_SAADC_S->TASKS_CALIBRATEOFFSET = 1;
    k_msleep(5);

    // Read samples
    err = adc_read(adc_dev, &sequence);
    if (err) {
        LOG_WRN("ADC read failed (error %d)", err);
        gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT); // Restore pin state
        return err;
    }

    // Restore bat_read_pin
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (err < 0) {
        LOG_ERR("Failed to configure bat_read_pin to input: %d", err);
        return err;
    }

    return 0;
}

int battery_init()
{
    int err;

    k_mutex_lock(&battery_mut, K_FOREVER);

    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (err < 0) {
        LOG_ERR("Failed to configure enable pin (%d)", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }

    err = gpio_pin_configure_dt(&bat_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
    if (err < 0) {
        LOG_ERR("Failed to configure enable pin (%d)", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }
    battery_charging_callback(NULL, NULL, 0);
    err = gpio_pin_interrupt_configure_dt(&bat_chg_pin, GPIO_INT_EDGE_BOTH);
    if (err < 0) {
        LOG_ERR("Failed to configure interrupt for bat_chg_pin (%d)", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }
    gpio_init_callback(&bat_chg_cb, battery_charging_callback, BIT(bat_chg_pin.pin));
    gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

    err = battery_enable_read();
    if (err < 0) {
        LOG_ERR("Failed to enable battery read (%d)", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }

    k_mutex_unlock(&battery_mut);

    // Charging state read
    int chargingStateErr;
    chargingStateErr = battery_charging_state_read();
    if (chargingStateErr) {
        LOG_ERR("Failed to read charging state (%d)", chargingStateErr);
    }

    return 0;
}
