// src/deep_sleep.c
#include <zephyr/kernel.h>
#include <hal/nrf_power.h>
#include "deep_sleep.h"

#include <nrf.h>
#include <hal/nrf_gpio.h>  
#include "led.h"

#define BUTTON_PIN  4  
void configure_button_for_wake_up(void) {
    // Configure the button pin for wake-up from System OFF mode
    nrf_gpio_cfg_sense_input(BUTTON_PIN, NRF_GPIO_PIN_PULLUP, NRF_GPIO_PIN_SENSE_LOW);
}

void enter_deep_sleep(void)
{
        set_led_white(true);
    // Actions to take before entering deep sleep mode here

    // Wait one second before turning off
    k_sleep(K_SECONDS(1));
    
    // Set the system to deep sleep mode. 
    NRF_POWER->SYSTEMOFF = 1;
}
