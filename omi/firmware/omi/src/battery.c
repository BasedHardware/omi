#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/logging/log.h>
#include <hal/nrf_saadc.h>
#include "lib/dk2/lib/battery/battery.h"

LOG_MODULE_REGISTER(battery, CONFIG_LOG_DEFAULT_LEVEL);

#define BATTERY_STATES_COUNT 16

#define ADC_TOTAL_SAMPLES 20
int16_t sample_buffer[ADC_TOTAL_SAMPLES];

#define ADC_RESOLUTION 10
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
    {4074, 100},
    {4029, 95},
    {3983, 90},
    {3938, 85},
    {3893, 80},
    {3847, 70},
    {3802, 60},
    {3756, 50},
    {3665, 40},
    {3619, 30},
    {3528, 20},
    {3437, 10},
    {3346, 5},
    {3255, 2},
    {3164, 1},
    {3000, 0}  // Below safe level
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

const struct adc_sequence_options sequence_opts = {
    .extra_samplings = ADC_TOTAL_SAMPLES - 1,
    .interval_us = 500, // Interval between each sample
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
    if(gpio_pin_get(bat_chg_pin.port, bat_chg_pin.pin) == 0) {
        is_charging = true;
    } else {
        is_charging = false;
    }
}

static int adc_sample(uint16_t *m_buffer)
{
    int ret;
    const struct adc_sequence sequence = {
        .options = &sequence_opts,
        .channels = BIT(ADC_1ST_CHANNEL_ID),
        .buffer = m_buffer,
        .buffer_size = sizeof(m_buffer),
        .resolution = ADC_RESOLUTION,
    };

    ret = adc_read(adc_dev, &sequence);
    return ret;
}

int battery_get_millivolt(uint16_t *battery_millivolt)
{
    int err;

    // Voltage divider circuit (Should tune R1 in software if possible)
    const uint16_t R1 = 1037; // Originally 1M ohm, calibrated after measuring actual voltage values. Can happen due to resistor tolerances, temperature ect..
    const uint16_t R2 = 510;  // 510K ohm
    
    k_mutex_lock(&battery_mut, K_FOREVER);
    
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1);
    if (err < 0)
    {
        return err;
    }
    gpio_pin_set(bat_read_pin.port, bat_read_pin.pin, 0);

    if (!adc_dev)
    {
        return -1;
    }

    err = adc_channel_setup(adc_dev, &m_1st_channel_cfg);
    if (err)
    {
        return err;
    }

    err |= adc_read(adc_dev, &sequence);
    if (err)
    {
        LOG_WRN("ADC read failed (error %d)", err);
    }

    // ADC measure
    uint16_t adc_vref = adc_ref_internal(adc_dev);
    int adc_mv = 0;

    // Get average sample value.
    for (uint8_t sample = 0; sample < ADC_TOTAL_SAMPLES; sample++)
    {
        adc_mv += sample_buffer[sample]; // ADC value, not millivolt yet.
    }
    adc_mv /= ADC_TOTAL_SAMPLES;

    // Convert ADC value to millivolts
    err |= adc_raw_to_millivolts(adc_vref, ADC_GAIN, ADC_RESOLUTION, &adc_mv);

    // ISSUE FIXED: In firmware 2.0.2 to 2.0.8 update, battery showed 0% due to integer division
    // in voltage calculation formula. Integer division of (R1 + R2) / R2 truncated the result
    // causing the battery voltage to be underestimated.
    //
    // FIX: Use floating point calculation to get accurate voltage divider ratio
    // and convert back to integer for final result
    float voltage_divider_ratio = (float)(R1 + R2) / (float)R2;
    *battery_millivolt = (uint16_t)(adc_mv * voltage_divider_ratio);

    LOG_DBG("ADC raw value: %d ", adc_mv);
    LOG_DBG("Voltage divider ratio: %f", voltage_divider_ratio);
    LOG_DBG("Measured voltage: %d mV", *battery_millivolt);
    gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);

    LOG_DBG("Charging status: %d", is_charging);
    
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
    
    if (battery_millivolt <= battery_states[BATTERY_STATES_COUNT-1].millivolts) {
        *battery_percentage = battery_states[BATTERY_STATES_COUNT-1].percentage;
        return 0;
    }
    
    // Find the appropriate range in the battery profile
    for (int i = 0; i < BATTERY_STATES_COUNT - 1; i++) {
        if (battery_millivolt <= battery_states[i].millivolts && 
            battery_millivolt > battery_states[i+1].millivolts) {
            
            // Linear interpolation between the two closest points
            uint16_t voltage_range = battery_states[i].millivolts - battery_states[i+1].millivolts;
            uint8_t percentage_range = battery_states[i].percentage - battery_states[i+1].percentage;
            uint16_t voltage_diff = battery_states[i].millivolts - battery_millivolt;
            
            *battery_percentage = battery_states[i].percentage - 
                                 (voltage_diff * percentage_range) / voltage_range;
            break;
        }
    }
    
    return 0;
}

int battery_charge_start()
{
    return 0; // No specific action needed with the new pin layout
}

int battery_charge_stop()
{
    return 0; // No specific action needed with the new pin layout
}

int battery_set_fast_charge()
{
    return 0; // No specific action needed with the new pin layout
}

int battery_set_slow_charge()
{
    return 0; // No specific action needed with the new pin layout
}

int battery_init()
{
    int err;
    
    k_mutex_lock(&battery_mut, K_FOREVER);
    
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (err < 0)
    {
        LOG_ERR("Failed to configure enable pin (%d)", err);
        return err;
    }
    
    err = gpio_pin_configure_dt(&bat_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
    if (err < 0)
    {
        LOG_ERR("Failed to configure enable pin (%d)", err);
        return err;
    }
    battery_charging_callback(NULL, NULL, 0);
    err = gpio_pin_interrupt_configure_dt(&bat_chg_pin, GPIO_INT_EDGE_BOTH);
    if (err < 0) {
        LOG_ERR("Failed to configure interrupt for bat_chg_pin (%d)", err);
        return err;
    }
    gpio_init_callback(&bat_chg_cb, battery_charging_callback, BIT(bat_chg_pin.pin));
    gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

    k_mutex_unlock(&battery_mut);
    return 0;
}
