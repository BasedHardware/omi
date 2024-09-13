#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <haly/nrfy_gpio.h>
#include "nrfx_clock.h"
#include "nrfx_pdm.h"
#include "config.h"
#include "mic.h"
#include "utils.h"
#include "led.h"

//
// Port of this code: https://github.com/Seeed-Studio/Seeed_Arduino_Mic/blob/master/src/hardware/nrf52840_adc.cpp
//

static int16_t _buffer_0[MIC_BUFFER_SAMPLES];
static int16_t _buffer_1[MIC_BUFFER_SAMPLES];
static volatile uint8_t _next_buffer_index = 0;
static volatile mix_handler _callback = NULL;

static void pdm_irq_handler(nrfx_pdm_evt_t const *event)
{
    // Ignore error (how to handle?)
    if (event->error)
    {
        printk("PDM error\n");
        return;
    }

    // Assign buffer
    if (event->buffer_requested)
    {
        // printk("Buffer requested\n");
        if (_next_buffer_index == 0)
        {
            nrfx_pdm_buffer_set(_buffer_0, MIC_BUFFER_SAMPLES);
            _next_buffer_index = 1;
        }
        else
        {
            nrfx_pdm_buffer_set(_buffer_1, MIC_BUFFER_SAMPLES);
            _next_buffer_index = 0;
        }
    }

    // Release buffer
    if (event->buffer_released)
    {
        // printk("Buffer released\n");
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

    // Configure PDM
    nrfx_pdm_config_t pdm_config = NRFX_PDM_DEFAULT_CONFIG(PDM_CLK_PIN, PDM_DIN_PIN);
    pdm_config.gain_l = MIC_GAIN;
    pdm_config.gain_r = MIC_GAIN;
    pdm_config.interrupt_priority = MIC_IRC_PRIORITY;
    pdm_config.clock_freq = NRF_PDM_FREQ_1280K;
    pdm_config.mode = NRF_PDM_MODE_MONO;
    pdm_config.edge = NRF_PDM_EDGE_LEFTFALLING;
    pdm_config.ratio = NRF_PDM_RATIO_80X;
    IRQ_DIRECT_CONNECT(PDM_IRQn, 5, nrfx_pdm_irq_handler, 0); // IMPORTANT!
    if (nrfx_pdm_init(&pdm_config, pdm_irq_handler) != NRFX_SUCCESS)
    {
        printk("Unable to initialize PDM\n");
        return -1;
    }

    // Power on Mic
    nrfy_gpio_cfg_output(PDM_PWR_PIN);
    nrfy_gpio_pin_set(PDM_PWR_PIN);
    
    printk("Microphone started\n");
    return 0;
}

int mic_resume()
{
    if (nrfx_pdm_start() != NRFX_SUCCESS)
    {
        printk("Unable to resume PDM\n");
        return -1;
    }

    printk("Microphone resumed\n");
    return 0;
}

int mic_pause()
{
    if (nrfx_pdm_stop() != NRFX_SUCCESS)
    {
        printk("Unable to pause PDM\n");
        return -1;
    }

    printk("Microphone paused\n");
    return 0;
}

void set_mic_callback(mix_handler callback)
{
    _callback = callback;
}