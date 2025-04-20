#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <haly/nrfy_gpio.h>
#include "nrfx_clock.h"
#include "nrfx_pdm.h"
#include "config.h"
#include "mic.h"
#include "utils.h"

LOG_MODULE_REGISTER(mic, CONFIG_LOG_DEFAULT_LEVEL);

static const struct gpio_dt_spec mic_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_en_pin), gpios, {0});
static const struct gpio_dt_spec mic_thsel = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_thsel_pin), gpios, {0});
static const struct gpio_dt_spec mic_wake = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(pdm_wake_pin), gpios, {0});

//
// Port of this code: https://github.com/Seeed-Studio/Seeed_Arduino_Mic/blob/master/src/hardware/nrf52840_adc.cpp
//

static int16_t _buffer_0[MIC_BUFFER_SAMPLES];
static int16_t _buffer_1[MIC_BUFFER_SAMPLES];
static volatile uint8_t _next_buffer_index = 0;
static volatile mix_handler _callback = NULL;

static nrfx_pdm_t pdm_instance = {
    .p_reg = NRF_PDM0,
    .drv_inst_idx = 0
};

static void pdm_irq_handler(nrfx_pdm_evt_t const *event)
{
    // Ignore error (how to handle?)
    if (event->error)
    {
        LOG_ERR("PDM error: %d", event->error);
        return;
    }

    // Assign buffer
    if (event->buffer_requested)
    {
        LOG_DBG("Audio buffer requested");
        int16_t *currentBuffer = _next_buffer_index == 0 ? _buffer_0 : _buffer_1;
        _next_buffer_index = _next_buffer_index == 0 ? 1 : 0;
        nrfx_pdm_buffer_set(&pdm_instance, currentBuffer, MIC_BUFFER_SAMPLES);
    }

    // Release buffer
    if (event->buffer_released)
    {
        LOG_DBG("Audio buffer requested");
        if (_callback)
        {
            _callback(event->buffer_released);
        }
    }
}

int mic_start()
{

    // Start the high frequency clock
    if (!nrf_clock_hf_is_running(NRF_CLOCK, NRF_CLOCK_HFCLK_HIGH_ACCURACY))
    {
        nrf_clock_task_trigger(NRF_CLOCK, NRF_CLOCK_TASK_HFCLKSTART);
    }

    // Use hardcoded PDM pins from pinctrl.dtsi
    // PDM CLK is on P1.1 and PDM DIN is on P1.0 as defined in omi2-pinctrl.dtsi
    uint32_t pdm_clk_pin = NRF_GPIO_PIN_MAP(1, 1);
    uint32_t pdm_din_pin = NRF_GPIO_PIN_MAP(1, 0);
    
    // Configure PDM
    nrfx_pdm_config_t pdm_config = NRFX_PDM_DEFAULT_CONFIG(pdm_clk_pin, pdm_din_pin);
    pdm_config.gain_l = MIC_GAIN;
    pdm_config.gain_r = MIC_GAIN;
    pdm_config.interrupt_priority = MIC_IRC_PRIORITY;
    pdm_config.clock_freq = NRF_PDM_FREQ_1000K; // TODO: try to lower the capturing rate, was NRF_PDM_FREQ_1280K; before
    pdm_config.mode = NRF_PDM_MODE_MONO;
    pdm_config.edge = NRF_PDM_EDGE_LEFTFALLING;
    pdm_config.ratio = NRF_PDM_RATIO_80X;
    IRQ_DIRECT_CONNECT(PDM0_IRQn, 5, nrfx_pdm_0_irq_handler, 0); // IMPORTANT!
    if (nrfx_pdm_init(&pdm_instance, &pdm_config, pdm_irq_handler) != NRFX_SUCCESS)
    {
        LOG_ERR("Audio unable to initialize PDM");
        return -1;
    }

    // Configure and enable microphone pins
    if (mic_en.port) {
        gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_en, 1);
    }
    
    if (mic_thsel.port) {
        gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_thsel, 1);
    }

    // Start PDM
    if (nrfx_pdm_start(&pdm_instance) != NRFX_SUCCESS)
    {
        LOG_ERR("Audio unable to start PDM");
        return -1;
    }

    LOG_INF("Audio microphone started");
    return 0;
}

void set_mic_callback(mix_handler callback) 
{
    _callback = callback;
}

void mic_off()
{
    if (mic_en.port) {
        gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_en, 0);
    }
    
    if (mic_thsel.port) {
        gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_thsel, 0);
    }
}


void mic_on()
{
    if (mic_en.port) {
        gpio_pin_configure_dt(&mic_en, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_en, 1);
    }

    if (mic_thsel.port) {
        gpio_pin_configure_dt(&mic_thsel, GPIO_OUTPUT);
        gpio_pin_set_dt(&mic_thsel, 1);
    }

    if (mic_wake.port) {
        gpio_pin_configure_dt(&mic_wake, GPIO_INPUT);
    }
}
