#include "lib/core/lib/battery/battery.h"

#include <hal/nrf_saadc.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

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
#define BATTERY_FILTER_ALPHA_U16 (uint16_t) (65535 / (5 + 1))
#define FILTER_INIT_CYCLES 5
#define BATTERY_STATES(is_charging) ((is_charging) ? battery_charging_states : battery_discharge_states)

// Static variable to store previous EMA value for battery percentage
static uint8_t battery_percentage_ema = 0;
static bool ema_initialized = false;
static bool is_first_measurement = true;
static uint8_t ema_init_counter = 0;

// GPIO edges arrive in interrupt context; never take battery_mut there.
static struct k_spinlock battery_state_lock;
static bool charging_state_known;
static uint32_t charge_generation;
static uint16_t charge_edge_count;
static bool first_off_charger_pending;
static bool has_off_charger_sample;
static uint8_t last_off_charger_percentage;
static uint16_t last_off_charger_millivolts = UINT16_MAX;
static uint16_t measured_millivolts = UINT16_MAX;
static bool soc_frozen;
static bool sample_valid;
static bool sample_charging;
static uint32_t sample_generation;

struct battery_soc_decision {
    uint8_t percentage;
    bool frozen;
};

// Three cases: charging freezes the last off-charger SOC; booting on the charger
// falls back to the charging curve without freezing; the first off-charger sample
// uses the discharge curve directly (later samples keep the discharge clamp/EMA).
static struct battery_soc_decision battery_soc_policy(bool charging,
                                                      bool has_off_sample,
                                                      bool first_off_sample,
                                                      uint8_t curve_percentage,
                                                      uint8_t filtered_percentage,
                                                      uint8_t off_percentage)
{
    if (charging) {
        return (struct battery_soc_decision) {
            .percentage = has_off_sample ? off_percentage : curve_percentage,
            .frozen = has_off_sample,
        };
    }
    return (struct battery_soc_decision) {
        .percentage = first_off_sample ? curve_percentage : MIN(filtered_percentage, off_percentage),
        .frozen = false,
    };
}

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

BatteryState battery_discharge_states[BATTERY_STATES_COUNT] = {
    {4140, 100},
    {4135, 99},
    {4091, 91},
    {4020, 78},
    {3938, 63},
    {3884, 53},
    {3791, 36},
    {3785, 35},
    {3671, 14},
    {3655, 11},
    {3600, 1}, // Threshold for <1%
    {0000, 0}  // Below safe level
};

BatteryState battery_charging_states[BATTERY_STATES_COUNT] = {
    {4200, 100},
    {4195, 99},
    {4159, 91},
    {4100, 78},
    {4032, 63},
    {3986, 53},
    {3909, 36},
    {3905, 35},
    {3809, 14},
    {3795, 11},
    {3750, 1}, // Threshold for <1%
    {0000, 0}  // Below safe level
};

extern bool is_charging;

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

uint8_t update_ema_filter(uint32_t current_ema, uint8_t new_value)
{
    // handle edge case transitions directly
    if ((!is_charging && (current_ema <= 5)) || (is_charging && (current_ema >= 95))) {
        if (is_charging) {
            return (new_value > current_ema) ? current_ema + 1 : current_ema;
        } else {
            return (new_value < current_ema) ? current_ema - 1 : current_ema;
        }
    }

    // Constant coefficient Alpha for EMA calculation, scaled to 16 bit.
    // Alpha = 65535/(N+1) where N is the averaging window
    const uint32_t alpha = BATTERY_FILTER_ALPHA_U16;
    const uint32_t alpha_complement = UINT16_MAX - BATTERY_FILTER_ALPHA_U16;

    // Calculate new EMA: new_ema = (alpha * new_value + alpha_complement * current_ema) / 65535
    uint64_t new_ema = (alpha * new_value) + (alpha_complement * current_ema);

    // Scale result back to 8-bit, with rounding up
    return (uint8_t) ((new_ema + 32768) >> 16);
}

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
    k_spinlock_key_t key = k_spin_lock(&battery_state_lock);
    const bool charging = is_charging;
    const uint32_t generation = charge_generation;
    sample_valid = false;
    k_spin_unlock(&battery_state_lock, key);

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

    // Diagnostics retain honest battery ADC millivolts before charging correction.
    const uint16_t adc_battery_millivolts = (uint16_t) (adc_raw_val * ((float) (R1 + R2) / R2));

    // Sub 16mV when charging to correct voltage skew
    // based on practical measurements adjusted on the omi device
    if (charging) {
        adc_raw_val -= 16;
    }

    // Calculate battery voltage using the voltage divider formula
    *battery_millivolt = (uint16_t) (adc_raw_val * ((float) (R1 + R2) / R2));
    LOG_INF("Battery voltage (mV): %d", *battery_millivolt);

    // Restore bat_read_pin to INPUT state to save power/avoid affecting other circuits
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (err < 0) {
        LOG_ERR("Failed to configure bat_read_pin to input: %d", err);
        k_mutex_unlock(&battery_mut);
        return err;
    }

    key = k_spin_lock(&battery_state_lock);
    measured_millivolts = adc_battery_millivolts;
    sample_charging = charging;
    sample_generation = generation;
    // Discard an ADC sample spanning an edge, rather than applying the wrong curve.
    const bool stable_charge_pin = charging_state_known && generation == charge_generation;
    sample_valid = stable_charge_pin;
    k_spin_unlock(&battery_state_lock, key);

    if (!stable_charge_pin) {
        k_mutex_unlock(&battery_mut);
        return -EAGAIN;
    }

    if (is_first_measurement) {
        LOG_INF("First measurement, skipping to allow voltage to stabilize");
        is_first_measurement = false;
        key = k_spin_lock(&battery_state_lock);
        sample_valid = false;
        k_spin_unlock(&battery_state_lock, key);
        k_mutex_unlock(&battery_mut);
        return -EAGAIN; // Skip first measurement to allow voltage to stabilize
    }

    k_mutex_unlock(&battery_mut);

    return 0;
}

int battery_get_percentage(uint8_t *battery_percentage, uint16_t battery_millivolt)
{
    k_mutex_lock(&battery_mut, K_FOREVER);
    k_spinlock_key_t key = k_spin_lock(&battery_state_lock);
    if (!sample_valid || sample_generation != charge_generation) {
        k_spin_unlock(&battery_state_lock, key);
        k_mutex_unlock(&battery_mut);
        return -EAGAIN;
    }
    sample_valid = false;
    const bool charging = sample_charging;
    const bool first_off_sample = !has_off_charger_sample || first_off_charger_pending;
    uint8_t raw_percentage = 0;
    BatteryState *battery_states = BATTERY_STATES(charging);

    // Use the battery discharge profile to determine percentage
    if (battery_millivolt >= battery_states[0].millivolts) {
        raw_percentage = battery_states[0].percentage;
    } else if (battery_millivolt <= battery_states[BATTERY_STATES_COUNT - 1].millivolts) {
        raw_percentage = battery_states[BATTERY_STATES_COUNT - 1].percentage;
    } else {
        // Find the appropriate range in the battery profile
        for (int i = 0; i < BATTERY_STATES_COUNT - 1; i++) {
            if (battery_millivolt <= battery_states[i].millivolts &&
                battery_millivolt > battery_states[i + 1].millivolts) {

                // Linear interpolation between the two closest points
                uint16_t voltage_range = battery_states[i].millivolts - battery_states[i + 1].millivolts;
                uint8_t percentage_range = battery_states[i].percentage - battery_states[i + 1].percentage;
                uint16_t voltage_diff = battery_states[i].millivolts - battery_millivolt;

                raw_percentage = battery_states[i].percentage - (voltage_diff * percentage_range) / voltage_range;
                break;
            }
        }
    }

    uint8_t filtered_percentage = raw_percentage;
    if (!charging && !first_off_sample) {
        raw_percentage = MIN(raw_percentage, battery_percentage_ema);
        if (!ema_initialized) {
            battery_percentage_ema = raw_percentage;
            if (++ema_init_counter >= FILTER_INIT_CYCLES) {
                ema_initialized = true;
            }
        } else {
            battery_percentage_ema = update_ema_filter(battery_percentage_ema, raw_percentage);
        }
        filtered_percentage = battery_percentage_ema;
    }

    const struct battery_soc_decision decision = battery_soc_policy(charging,
                                                                    has_off_charger_sample,
                                                                    first_off_sample,
                                                                    raw_percentage,
                                                                    filtered_percentage,
                                                                    last_off_charger_percentage);
    *battery_percentage = decision.percentage;
    soc_frozen = decision.frozen;
    if (!charging) {
        if (first_off_sample) {
            // Rebase the filter to the uncorrected discharge reading, not charger EMA.
            battery_percentage_ema = decision.percentage;
            ema_initialized = false;
            ema_init_counter = 1;
        }
        has_off_charger_sample = true;
        first_off_charger_pending = false;
        last_off_charger_percentage = decision.percentage;
        last_off_charger_millivolts = measured_millivolts;
    }
    k_spin_unlock(&battery_state_lock, key);
    k_mutex_unlock(&battery_mut);

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
    const int pin = gpio_pin_get(bat_chg_pin.port, bat_chg_pin.pin);
    if (pin < 0) {
        return pin;
    }
    const bool charging = pin == 0;
    k_spinlock_key_t key = k_spin_lock(&battery_state_lock);
    if (charging_state_known && charging != is_charging) {
        charge_generation++;
        if (charge_edge_count < UINT16_MAX - 1U) {
            charge_edge_count++;
        }
        if (!charging) {
            first_off_charger_pending = true;
        }
    }
    is_charging = charging;
    charging_state_known = true;
    k_spin_unlock(&battery_state_lock, key);
    return 0;
}

void battery_get_diagnostics(struct battery_diagnostics *diagnostics)
{
    k_spinlock_key_t key = k_spin_lock(&battery_state_lock);
    *diagnostics = (struct battery_diagnostics) {
        .millivolts = measured_millivolts,
        .last_off_charger_millivolts = last_off_charger_millivolts,
        .charge_edge_count = charge_edge_count,
        .charge_pin = charging_state_known ? (is_charging ? 1U : 0U) : UINT8_MAX,
        .soc_frozen = soc_frozen,
    };
    k_spin_unlock(&battery_state_lock, key);
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
