#include <stdio.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/dt-bindings/gpio/nordic-nrf-gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <hal/nrf_saadc.h>
#include "battery.h"

LOG_MODULE_REGISTER(battery);

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

bool is_charging = false;
static void battrey_input_cb(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    if(gpio_pin_get(bat_chg_pin.port, bat_chg_pin.pin) == 1) {
        shell_execute_cmd(NULL, "led on 1");
        is_charging = true;
    } else{
        shell_execute_cmd(NULL, "led off 1");
        is_charging = false;
    }
	return;
}


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
    .interval_us = 0,
    .callback = NULL,
    .user_data = NULL,
    .extra_samplings = 1,
};

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

static int cmd_bat_get(const struct shell *sh, size_t argc, char **argv)
{
    int err;
    uint16_t m_buffer[2];
    err = gpio_pin_configure_dt(&bat_read_pin, GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1);
    if (err < 0)
    {
        shell_error(sh, "Failed to configure enable pin (%d)", err);
        return err;
    }
    gpio_pin_set(bat_read_pin.port, bat_read_pin.pin, 0);

    if (!adc_dev)
    {
        shell_error(sh, "device_get_binding ADC_0 failed\n");
        return -1;
    }
    err = adc_channel_setup(adc_dev, &m_1st_channel_cfg);
    if (err)
    {
        shell_error(sh, "Error in adc setup: %d\n", err);
        return err;
    }

    /* Trigger offset calibration
     * As this generates a _DONE and _RESULT event
     * the first result will be incorrect.
     */
    NRF_SAADC_S->TASKS_CALIBRATEOFFSET = 1;

    err = adc_sample(m_buffer);
    if (err)
    {
        shell_error(sh, "Error in adc sampling: %d\n", err);
        return err;
    }

    shell_print(sh, "ADC raw value: %d ", m_buffer[1]);
    shell_print(sh, "Measured voltage: %f", (m_buffer[1] * 1.8) / 1024 * 3);
    gpio_pin_configure_dt(&bat_read_pin, GPIO_INPUT);

    shell_print(sh, "Charging status: %d", is_charging);
    return 0;
}

int bat_init(void)
{ 
    int err;
    err = gpio_pin_configure_dt(&power_pin, GPIO_OUTPUT );
    if (err < 0)
    {
        LOG_ERR("Failed to configure enable pin (%d)", err);
        return err;
    }
    gpio_pin_set_dt(&power_pin, 0);
    
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
    gpio_init_callback(&bat_chg_cb, battrey_input_cb, BIT(bat_chg_pin.pin));
    gpio_add_callback(bat_chg_pin.port, &bat_chg_cb);

    return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(sub_bat_cmds,
                               SHELL_CMD(get, NULL, "Get battery voltage", cmd_bat_get),
                               SHELL_SUBCMD_SET_END);

SHELL_CMD_REGISTER(bat, &sub_bat_cmds, "Get battery voltage", NULL);