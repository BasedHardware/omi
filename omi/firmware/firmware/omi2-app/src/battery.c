// /*
//  * Copyright 2024 Marcus Alexander Tjomsaas
//  *
//  * Licensed under the Apache License, Version 2.0 (the "License");
//  * you may not use this file except in compliance with the License.
//  * You may obtain a copy of the License at
//  *
//  *     http://www.apache.org/licenses/LICENSE-2.0
//  *
//  * Unless required by applicable law or agreed to in writing, software
//  * distributed under the License is distributed on an "AS IS" BASIS,
//  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  * See the License for the specific language governing permissions and
//  * limitations under the License.
//  */

// #include "battery.h"

// #include <zephyr/kernel.h>
// #include <zephyr/device.h>
// #include <zephyr/devicetree.h>
// #include <zephyr/drivers/gpio.h>
// #include <zephyr/drivers/adc.h>
// #include <zephyr/logging/log.h>
// #include <hal/nrf_saadc.h>
// #include <hal/nrf_gpio.h>
// LOG_MODULE_REGISTER(battery, LOG_LEVEL_INF);

// // Updated to match test/src/battery.c approach
// #define ADC_RESOLUTION 10
// #define ADC_GAIN ADC_GAIN_1_3
// #define ADC_REFERENCE ADC_REF_INTERNAL
// #define ADC_ACQUISITION_TIME ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)
// #define ADC_1ST_CHANNEL_ID 0
// #define ADC_1ST_CHANNEL_INPUT NRF_SAADC_INPUT_AIN0

// // Using device tree specs as in test file
// static const struct device *const adc_dev = DEVICE_DT_GET(DT_NODELABEL(adc));
// static const struct gpio_dt_spec power_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(power_pin), gpios, {0});
// static const struct gpio_dt_spec bat_read_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_read_pin), gpios, {0});
// static const struct gpio_dt_spec bat_chg_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});

// static K_MUTEX_DEFINE(battery_mut);
// static struct gpio_callback bat_chg_cb;
// static uint8_t is_initialized = false;
// static bool is_charging = false;

// static const struct adc_channel_cfg m_1st_channel_cfg = {
//     .gain = ADC_GAIN,
//     .reference = ADC_REFERENCE,
//     .acquisition_time = ADC_ACQUISITION_TIME,
//     .channel_id = ADC_1ST_CHANNEL_ID,
// #if defined(CONFIG_ADC_CONFIGURABLE_INPUTS)
//     .input_positive = ADC_1ST_CHANNEL_INPUT,
// #endif
// };

// const struct adc_sequence_options sequence_opts = {
//     .interval_us = 0,
//     .callback = NULL,
//     .user_data = NULL,
//     .extra_samplings = 1,
// };

// static void battrey_input_cb(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
// {
//     if(gpio_pin_get_dt(&bat_chg_pin) == 1) {
//         is_charging = true;
//     } else {
//         is_charging = false;
//     }
//     return;
// }

// static int battery_enable_read()
// {
//     return gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT) ||
//            gpio_pin_set_dt(&bat_read_pin, 0);
// }

// static int adc_sample(uint16_t *m_buffer)
// {
//     int ret;
//     const struct adc_sequence sequence = {
//         .options = &sequence_opts,
//         .channels = BIT(ADC_1ST_CHANNEL_ID),
//         .buffer = m_buffer,
//         .buffer_size = sizeof(uint16_t) * 2, // Buffer size for 2 samples
//         .resolution = ADC_RESOLUTION,
//     };

//     k_mutex_lock(&battery_mut, K_FOREVER);
//     ret = adc_read(adc_dev, &sequence);
//     k_mutex_unlock(&battery_mut);
    
//     return ret;
// }

// int battery_set_fast_charge()
// {
//     if (!is_initialized)
//     {
//         return -ECANCELED;
//     }

//     return gpio_pin_set_dt(&power_pin, 1); // FAST charge
// }

// int battery_set_slow_charge()
// {
//     if (!is_initialized)
//     {
//         return -ECANCELED;
//     }

//     return gpio_pin_set_dt(&power_pin, 0); // SLOW charge
// }

// int battery_charge_start()
// {
//     int ret = 0;

//     if (!is_initialized)
//     {
//         return -ECANCELED;
//     }
//     ret |= battery_enable_read();
//     return ret;
// }

// int battery_charge_stop()
// {
//     if (!is_initialized)
//     {
//         return -ECANCELED;
//     }

//     return gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
// }

// int battery_get_millivolt(uint16_t *battery_millivolt)
// {
//     int ret = 0;
//     uint16_t m_buffer[2];

//     ret |= battery_enable_read();
//     if (ret)
//     {
//         LOG_WRN("Failed to enable battery read (%d)", ret);
//         return ret;
//     }

//     // ADC setup has already been done in init
    
//     /* Trigger offset calibration
//      * As this generates a _DONE and _RESULT event
//      * the first result will be incorrect.
//      */
//     nrf_saadc_task_trigger(NRF_SAADC, NRF_SAADC_TASK_CALIBRATEOFFSET);

//     ret |= adc_sample(m_buffer);
//     if (ret)
//     {
//         LOG_WRN("ADC read failed (error %d)", ret);
//         return ret;
//     }

//     // Using conversion formula from test file
//     *battery_millivolt = (m_buffer[1] * 1.8) / 1024 * 3000; // Converting to millivolts

//     LOG_DBG("%d mV", *battery_millivolt);
//     return ret;
// }

// int battery_get_percentage(uint8_t *battery_percentage, uint16_t battery_millivolt)
// {
//     // Simplified calculation based on voltage ranges
//     if (battery_millivolt >= 4200)
//         *battery_percentage = 100;
//     else if (battery_millivolt <= 3150)
//         *battery_percentage = 0;
//     else
//         *battery_percentage = (battery_millivolt - 3150) * 100 / (4200 - 3150);

//     LOG_DBG("%d %%", *battery_percentage);
//     return 0;
// }

// int battery_init()
// {
//     int ret = 0;

//     LOG_INF("Initializing battery...\n");

//     // Check if devices are ready
//     if (!device_is_ready(adc_dev))
//     {
//         LOG_ERR("ADC device not found!");
//         return -EIO;
//     }

//     // Configure power pin
//     ret |= gpio_pin_configure_dt(&power_pin, GPIO_OUTPUT);
//     if (ret)
//     {
//         LOG_ERR("Failed to configure power pin (%d)", ret);
//         return ret;
//     }
//     gpio_pin_set_dt(&power_pin, 0);
    
//     // Configure battery read pin
//     ret |= gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
//     if (ret)
//     {
//         LOG_ERR("Failed to configure battery read pin (%d)", ret);
//         return ret;
//     }
    
//     // Configure battery charging pin
//     ret |= gpio_pin_configure_dt(&bat_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
//     if (ret)
//     {
//         LOG_ERR("Failed to configure battery charging pin (%d)", ret);
//         return ret;
//     }
    
//     // Setup charging status callback
//     gpio_init_callback(&bat_chg_cb, battrey_input_cb, BIT(bat_chg_pin.pin));
//     gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

//     // ADC setup
//     ret |= adc_channel_setup(adc_dev, &m_1st_channel_cfg);
//     if (ret)
//     {
//         LOG_ERR("ADC setup failed (error %d)", ret);
//         return ret;
//     }

//     is_initialized = true;
//     LOG_INF("Battery module initialized");

//     return ret;
// }

#include "battery.h"

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/logging/log.h>
#include <hal/nrf_saadc.h>

LOG_MODULE_REGISTER(battery, LOG_LEVEL_INF);

#define ADC_RESOLUTION         10
#define ADC_GAIN               ADC_GAIN_1_3
#define ADC_REFERENCE          ADC_REF_INTERNAL
#define ADC_ACQUISITION_TIME   ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)
#define ADC_CHANNEL_ID         0
#define ADC_CHANNEL_INPUT      NRF_SAADC_INPUT_AIN2   // P0.04

#define BAT_READ_ACTIVE_LOW    1   // Set to output low to enable read

// Devices and specs
static const struct device *adc_dev = DEVICE_DT_GET(DT_NODELABEL(adc));
static const struct gpio_dt_spec bat_read_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_read_pin), gpios, {0}); // P0.06
static const struct gpio_dt_spec bat_chg_pin  = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});  // P0.17 or similar
static const struct gpio_dt_spec power_pin    = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(power_pin), gpios, {0});    // Optional

static struct gpio_callback bat_chg_cb;
static K_MUTEX_DEFINE(battery_mut);
static bool is_initialized = false;
bool is_charging = false;

static const struct adc_channel_cfg adc_cfg = {
    .gain = ADC_GAIN,
    .reference = ADC_REFERENCE,
    .acquisition_time = ADC_ACQUISITION_TIME,
    .channel_id = ADC_CHANNEL_ID,
#if defined(CONFIG_ADC_CONFIGURABLE_INPUTS)
    .input_positive = ADC_CHANNEL_INPUT,
#endif
};

static const struct adc_sequence_options sequence_opts = {
    .interval_us = 0,
    .callback = NULL,
    .user_data = NULL,
    .extra_samplings = 1,
};

static void batt_chg_cb_handler(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    is_charging = gpio_pin_get_dt(&bat_chg_pin) == 1;
}

/* Enable battery voltage read by pulling READ_BAT_n LOW */
static int battery_enable_read()
{
    return gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT | GPIO_ACTIVE_LOW) |
           gpio_pin_set_dt(&bat_read_pin, 0);
}

/* Disable battery read pin (optional) */
static int battery_disable_read()
{
    return gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
}

static int adc_sample(uint16_t *buffer)
{
    const struct adc_sequence sequence = {
        .options = &sequence_opts,
        .channels = BIT(ADC_CHANNEL_ID),
        .buffer = buffer,
        .buffer_size = sizeof(uint16_t) * 2,
        .resolution = ADC_RESOLUTION,
    };

    k_mutex_lock(&battery_mut, K_FOREVER);
    int ret = adc_read(adc_dev, &sequence);
    k_mutex_unlock(&battery_mut);
    return ret;
}

int battery_get_millivolt(uint16_t *battery_millivolt)
{
    int ret;
    uint16_t buffer[2];

    if (!is_initialized) return -ECANCELED;

    ret = battery_enable_read();
    if (ret) return ret;

    // Optional: Trigger calibration (first sample may be invalid)
    nrf_saadc_task_trigger(NRF_SAADC, NRF_SAADC_TASK_CALIBRATEOFFSET);

    ret = adc_sample(buffer);
    if (ret) return ret;

    // Simple conversion: ADC raw * Vref / resolution * scaling
    *battery_millivolt = (uint16_t)(((float)buffer[1] * 1.8f / 1024.0f) * 3000.0f);  // Adjust scaling as needed

    return 0;
}

int battery_get_percentage(uint8_t *battery_percentage, uint16_t millivolts)
{
    if (millivolts >= 4200) *battery_percentage = 100;
    else if (millivolts <= 3150) *battery_percentage = 0;
    else *battery_percentage = (millivolts - 3150) * 100 / (4200 - 3150);
    return 0;
}

int battery_set_fast_charge()
{
    if (!is_initialized) return -ECANCELED;
    return gpio_pin_set_dt(&power_pin, 1);
}

int battery_set_slow_charge()
{
    if (!is_initialized) return -ECANCELED;
    return gpio_pin_set_dt(&power_pin, 0);
}

int battery_charge_start()
{
    if (!is_initialized) return -ECANCELED;
    return battery_enable_read();
}

int battery_charge_stop()
{
    if (!is_initialized) return -ECANCELED;
    return battery_disable_read();
}

int battery_init()
{
    int ret = 0;

    LOG_INF("Initializing battery...");

    // Check if ADC device is ready
    if (!device_is_ready(adc_dev)) {
        LOG_ERR("ADC device not ready");
        return -ENODEV;
    }

    // Check if battery read pin is ready
    if (!device_is_ready(bat_read_pin.port)) {
        LOG_ERR("bat_read_pin not ready");
        return -ENODEV;
    }

    // Check if battery charging pin is ready
    if (!device_is_ready(bat_chg_pin.port)) {
        LOG_ERR("bat_chg_pin not ready");
        return -ENODEV;
    }

    // Check if power pin is ready
    if (!device_is_ready(power_pin.port)) {
        LOG_ERR("power_pin not ready");
        return -ENODEV;
    }

    // Configure power pin
    ret = gpio_pin_configure_dt(&power_pin, GPIO_OUTPUT);
    if (ret) {
        LOG_ERR("power_pin config failed: %d", ret);
        return ret;
    }

    // Configure battery read pin
    ret = gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);
    if (ret) {
        LOG_ERR("bat_read_pin config failed: %d", ret);
        return ret;
    }

    // Configure battery charging pin
    ret = gpio_pin_configure_dt(&bat_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
    if (ret) {
        LOG_ERR("bat_chg_pin config failed: %d", ret);
        return ret;
    }

    // Add GPIO callback
    gpio_init_callback(&bat_chg_cb, batt_chg_cb_handler, BIT(bat_chg_pin.pin));
    gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

    // Setup ADC channel    
    ret = adc_channel_setup(adc_dev, &adc_cfg);
    if (ret) {
        LOG_ERR("ADC setup failed: %d", ret);
        return ret;
    }

    // Set initialized flag
    is_initialized = true;
    LOG_INF("Battery module initialized");
    return 0;
}


// int battery_init()
// {
//     int ret = 0;

//     LOG_INF("Initializing battery module");

//     if (!device_is_ready(adc_dev)) {
//         LOG_ERR("ADC device not ready");
//         return -ENODEV;
//     }

//     if (!device_is_ready(bat_read_pin.port) ||
//         !device_is_ready(bat_chg_pin.port) ||
//         !device_is_ready(power_pin.port)) {
//         LOG_ERR("One or more battery GPIOs not ready");
//         return -ENODEV;
//     }

//     // Configure GPIOs
//     ret |= gpio_pin_configure_dt(&power_pin, GPIO_OUTPUT | GPIO_ACTIVE_LOW);
//     ret |= gpio_pin_set_dt(&power_pin, 0); // Default to slow charge
//     ret |= gpio_pin_configure_dt(&bat_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
//     if (ret) {
//         LOG_ERR("GPIO configuration failed: %d", ret);
//         return ret;
//     }

//     // Setup charging callback
//     gpio_init_callback(&bat_chg_cb, batt_chg_cb_handler, BIT(bat_chg_pin.pin));
//     gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

//     // ADC setup
//     ret = adc_channel_setup(adc_dev, &adc_cfg);
//     if (ret) {
//         LOG_ERR("ADC setup failed: %d", ret);
//         return ret;
//     }

//     is_initialized = true;
//     LOG_INF("Battery initialized");
//     return 0;
// }
