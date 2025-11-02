/*
 * Copyright 2024 Marcus Alexander Tjomsaas
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "battery.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(battery, LOG_LEVEL_INF);

static const struct device *gpio_battery_dev = DEVICE_DT_GET(DT_NODELABEL(gpio0));
static const struct device *adc_battery_dev = DEVICE_DT_GET(DT_NODELABEL(adc));

static K_MUTEX_DEFINE(battery_mut);

#define GPIO_BATTERY_CHARGE_SPEED 13
#define GPIO_BATTERY_CHARGING_ENABLE 17
#define GPIO_BATTERY_READ_ENABLE 14

// Increased sample count for better accuracy and noise reduction
// Higher sample count provides more stable and accurate readings
#define ADC_TOTAL_SAMPLES 50
int16_t sample_buffer[ADC_TOTAL_SAMPLES];

#define ADC_RESOLUTION 12
#define ADC_CHANNEL 7
#define ADC_PORT SAADC_CH_PSELP_PSELP_AnalogInput7 // AIN7
#define ADC_REFERENCE ADC_REF_INTERNAL             // 0.6V
#define ADC_GAIN ADC_GAIN_1_6                      // ADC REFERENCE * 6 = 3.6V
// Explicit acquisition time for stable ADC readings (40μs)
#define ADC_ACQUISITION_TIME ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 40)

struct adc_channel_cfg channel_7_cfg = {.gain = ADC_GAIN,
                                        .reference = ADC_REFERENCE,
                                        .acquisition_time = ADC_ACQUISITION_TIME,
                                        .channel_id = ADC_CHANNEL,
#ifdef CONFIG_ADC_NRFX_SAADC
                                        .input_positive = ADC_PORT
#endif
};

static struct adc_sequence_options options = {
    .extra_samplings = ADC_TOTAL_SAMPLES - 1,
    .interval_us = 100, // Reduced interval for faster sampling while maintaining stability
};

struct adc_sequence sequence = {
    .options = &options,
    .channels = BIT(ADC_CHANNEL),
    .buffer = sample_buffer,
    .buffer_size = sizeof(sample_buffer),
    .resolution = ADC_RESOLUTION,
};

typedef struct {
    uint16_t voltage;
    uint8_t percentage;
} BatteryState;

#define BATTERY_STATES_COUNT 20
// Enhanced 1S 250mAh LiPo battery discharge profile with improved granularity
// Additional data points at critical ranges for more accurate percentage calculation
BatteryState battery_states[BATTERY_STATES_COUNT] = {
    {4200, 100}, // Maximum voltage for fully charged LiPo
    {4074, 99},
    {4029, 95},
    {3983, 90},
    {3938, 85},
    {3893, 80},
    {3870, 75},
    {3847, 70},
    {3825, 65},
    {3802, 60},
    {3780, 55},
    {3756, 50},
    {3710, 45},
    {3665, 40},
    {3619, 30},
    {3528, 20},
    {3437, 10},
    {3346, 5},
    {3255, 2},
    {3000, 0} // Below safe level
};

static uint8_t is_initialized = false;

// Moving average filter for voltage smoothing
static uint16_t voltage_history[5];
static uint8_t history_index = 0;
static bool history_initialized = false;

static int battery_enable_read()
{
    return gpio_pin_set(gpio_battery_dev, GPIO_BATTERY_READ_ENABLE, 1);
}

int battery_set_fast_charge()
{
    if (!is_initialized) {
        return -ECANCELED;
    }

    return gpio_pin_set(gpio_battery_dev, GPIO_BATTERY_CHARGE_SPEED, 1); // FAST charge 100mA
}

int battery_set_slow_charge()
{
    if (!is_initialized) {
        return -ECANCELED;
    }

    return gpio_pin_set(gpio_battery_dev, GPIO_BATTERY_CHARGE_SPEED, 0); // SLOW charge 50mA
}

int battery_charge_start()
{
    int ret = 0;

    if (!is_initialized) {
        return -ECANCELED;
    }
    ret |= battery_enable_read();
    ret |= gpio_pin_set(gpio_battery_dev, GPIO_BATTERY_CHARGING_ENABLE, 1);
    return ret;
}

int battery_charge_stop()
{
    if (!is_initialized) {
        return -ECANCELED;
    }

    return gpio_pin_set(gpio_battery_dev, GPIO_BATTERY_CHARGING_ENABLE, 0);
}

int battery_get_millivolt(uint16_t *battery_millivolt)
{

    int ret = 0;

    // Voltage divider circuit (Should tune R1 in software if possible)
    const uint16_t R1 = 1037; // Originally 1M ohm, calibrated after measuring actual voltage values. Can happen due to
                              // resistor tolerances, temperature ect..
    const uint16_t R2 = 510;  // 510K ohm

    // ADC measure
    uint16_t adc_vref = adc_ref_internal(adc_battery_dev);

    k_mutex_lock(&battery_mut, K_FOREVER);
    ret |= adc_read(adc_battery_dev, &sequence);

    if (ret) {
        LOG_WRN("ADC read failed (error %d)", ret);
        k_mutex_unlock(&battery_mut);
        return ret;
    }

    // Use median filtering instead of simple average for better noise rejection
    // Copy samples to a temporary array for sorting
    int16_t sorted_samples[ADC_TOTAL_SAMPLES];
    for (int i = 0; i < ADC_TOTAL_SAMPLES; i++) {
        sorted_samples[i] = sample_buffer[i];
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

    // Calculate median value
    int32_t adc_raw_val;
    if (ADC_TOTAL_SAMPLES % 2 == 0) {
        adc_raw_val = (sorted_samples[ADC_TOTAL_SAMPLES / 2 - 1] + sorted_samples[ADC_TOTAL_SAMPLES / 2]) / 2;
    } else {
        adc_raw_val = sorted_samples[ADC_TOTAL_SAMPLES / 2];
    }

    LOG_DBG("Median ADC raw value: %d", adc_raw_val);

    // Convert ADC value to millivolts
    ret |= adc_raw_to_millivolts(adc_vref, ADC_GAIN, ADC_RESOLUTION, &adc_raw_val);

    if (ret) {
        LOG_WRN("ADC raw to millivolts conversion failed (error %d)", ret);
        k_mutex_unlock(&battery_mut);
        return ret;
    }

    // Calculate raw battery voltage using voltage divider formula
    uint16_t raw_battery_millivolt = (uint16_t)(adc_raw_val * ((float)(R1 + R2) / R2));

    // Apply moving average filter for smoother readings across multiple calls
    voltage_history[history_index] = raw_battery_millivolt;
    history_index = (history_index + 1) % 5;

    // Fill all history slots with the first reading on initialization
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
    *battery_millivolt = (uint16_t)(sum / 5);

    LOG_DBG("Raw battery millivolt: %u mV, Filtered: %u mV", raw_battery_millivolt, *battery_millivolt);

    k_mutex_unlock(&battery_mut);

    return ret;
}

int battery_get_percentage(uint8_t *battery_percentage, uint16_t battery_millivolt)
{
    // Ensure voltage is within bounds
    if (battery_millivolt >= battery_states[0].voltage) {
        *battery_percentage = battery_states[0].percentage;
        LOG_DBG("%d %%", *battery_percentage);
        return 0;
    }
    if (battery_millivolt <= battery_states[BATTERY_STATES_COUNT - 1].voltage) {
        *battery_percentage = battery_states[BATTERY_STATES_COUNT - 1].percentage;
        LOG_DBG("%d %%", *battery_percentage);
        return 0;
    }

    for (uint16_t i = 0; i < BATTERY_STATES_COUNT - 1; i++) {
        // Find the two points battery_millivolt is between
        if (battery_millivolt <= battery_states[i].voltage && battery_millivolt > battery_states[i + 1].voltage) {
            // Linear interpolation
            float voltage_range = (float) (battery_states[i].voltage - battery_states[i + 1].voltage);
            float percentage_range = (float) (battery_states[i].percentage - battery_states[i + 1].percentage);
            float position = (float) (battery_states[i].voltage - battery_millivolt) / voltage_range;

            *battery_percentage = battery_states[i].percentage - (uint8_t) (position * percentage_range);

            LOG_DBG("%d %%", *battery_percentage);
            return 0;
        }
    }
    return -ESPIPE;
}

int battery_init()
{
    int ret = 0;

    // ADC
    if (!device_is_ready(adc_battery_dev)) {
        LOG_ERR("ADC device not found!");
        return -EIO;
    }

    ret |= adc_channel_setup(adc_battery_dev, &channel_7_cfg);

    if (ret) {
        LOG_ERR("ADC setup failed (error %d)", ret);
    }

    // GPIO
    if (!device_is_ready(gpio_battery_dev)) {
        LOG_ERR("GPIO device not found!");
        return -EIO;
    }

    ret |= gpio_pin_configure(gpio_battery_dev, GPIO_BATTERY_CHARGING_ENABLE, GPIO_OUTPUT | GPIO_ACTIVE_LOW);
    ret |= gpio_pin_configure(gpio_battery_dev, GPIO_BATTERY_READ_ENABLE, GPIO_OUTPUT | GPIO_ACTIVE_LOW);
    ret |= gpio_pin_configure(gpio_battery_dev, GPIO_BATTERY_CHARGE_SPEED, GPIO_OUTPUT | GPIO_ACTIVE_LOW);

    if (ret) {
        LOG_ERR("GPIO configure failed!");
        return ret;
    }

    if (ret) {
        LOG_ERR("Initialization failed (error %d)", ret);
        return ret;
    }

    is_initialized = true;
    LOG_INF("Initialized");

    ret |= battery_enable_read();
    ret |= battery_set_fast_charge();

    return ret;
}
