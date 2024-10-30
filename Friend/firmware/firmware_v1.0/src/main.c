#include <zephyr/logging/log.h>
#include <zephyr/kernel.h>
#include "transport.h"
#include "mic.h"
#include "utils.h"
#include "led.h"
#include "config.h"
#include "codec.h"
#include "button.h"
// #include "nfc.h"
#include "sdcard.h"
#include "storage.h"
#include "speaker.h"
#include "usb.h"
#define BOOT_BLINK_DURATION_MS 600
#define BOOT_PAUSE_DURATION_MS 200
#define VBUS_DETECT (1U << 20)
#define WAKEUP_DETECT (1U << 16)
LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

static void codec_handler(uint8_t *data, size_t len)
{
	int err = broadcast_audio_packets(data, len);
    if (err) 
    {
        LOG_ERR("Failed to broadcast audio packets: %d", err);
    }
}

static void mic_handler(int16_t *buffer)
{
    int err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if (err) 
    {
        LOG_ERR("Failed to process PCM data: %d", err);
    }
}

void bt_ctlr_assert_handle(char *name, int type)
{
	LOG_INF("Bluetooth assert: %s (type %d)", name ? name : "NULL", type);
}



bool is_connected = false;
bool is_charging = false;
extern bool is_off;
extern bool usb_charge;
static void boot_led_sequence(void)
{
    // Red blink
    set_led_red(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_red(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Green blink
    set_led_green(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_green(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // Blue blink
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    set_led_blue(false);
    k_msleep(BOOT_PAUSE_DURATION_MS);
    // All LEDs on
    set_led_red(true);
    set_led_green(true);
    set_led_blue(true);
    k_msleep(BOOT_BLINK_DURATION_MS);
    // All LEDs off
    set_led_red(false);
    set_led_green(false);
    set_led_blue(false);
}
void activate_everything_no_lights()
{
    int err;

    err = led_start();
    err = transport_start();
    err = mount_sd_card();
    err = storage_init();
    err = init_haptic_pin();
    set_codec_callback(codec_handler);
    err = codec_start();
    set_mic_callback(mic_handler);
    err = mic_start();
    err = init_usb();

}

void set_led_state()
{
	// Recording and connected state - BLUE

    if(usb_charge)
    {
        is_charging = !is_charging;
        if(is_charging)
        {
            set_led_green(true);
        }
        else
        {
            set_led_green(false);
        }
    }
    else
    {
        set_led_green(false);
    }
    if(is_off)
    {
		set_led_red(false);
		set_led_blue(false);
        return;
    }
	if (is_connected)
	{
		set_led_blue(true);
		set_led_red(false);
		return;
	}

	// Recording but lost connection - RED
	if (!is_connected)
	{
		set_led_red(true);
		set_led_blue(false);
		return;
	}

}
bool from_wakeup = false;
// Main loop
int main(void)
{
	int err;
    //for system power off, we have no choice but to handle usb detect wakeup events. if off, and this was the reason, initialize, skip lightshow, start not recording 
    uint32_t reset_reas = NRF_POWER->RESETREAS;
    NRF_POWER->DCDCEN=1;
    NRF_POWER->DCDCEN0=1;
    
    NRF_POWER->RESETREAS=1;
    bool from_usb_event = (reset_reas & VBUS_DETECT);
    bool from_wakeup =  (reset_reas & WAKEUP_DETECT);
    if (from_usb_event) 
    {
        k_msleep(100);
        printf("from reset \n");
        is_off = true;

        // usb_charge = true;
        activate_everything_no_lights();
        // bt_disable();
        bt_off();
    }
    else if (from_wakeup)
    {
 
        is_off = false;
        usb_charge = false;
        force_button_state(GRACE);
        k_msleep(1000);
        activate_everything_no_lights(); 
        bt_on();       
        play_haptic_milli(100);


    }
    else
    {
    
    LOG_INF("Friend device firmware starting...");
    err = led_start();
    if (err) 
    {
        LOG_ERR("Failed to initialize LEDs: %d", err);
        return err;
    }
    // Run the boot LED sequence
    boot_led_sequence();
    // Indicate transport initialization
    set_led_green(true);
    set_led_green(false);

    err = transport_start();
    if (err) 
    {
        LOG_ERR("Failed to start transport: %d", err);
        // Blink green LED to indicate error
        for (int i = 0; i < 5; i++) 
        {
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_green(false);
        // return err;
    }
    play_boot_sound();
    err = mount_sd_card();
    if (err)
    {
        LOG_ERR("Failed to mount SD card: %d", err);
    }
    LOG_INF("result of mount:%d",err);

    k_msleep(500);
    err = storage_init();
    if (err)
    {
        LOG_ERR("Failed to initialize storage: %d", err);
    }
    err = init_haptic_pin();
    if (err)
    {
        LOG_ERR("Failed to initialize haptic pin: %d", err);
    }

    set_led_blue(true);
    set_codec_callback(codec_handler);
    err = codec_start();
    if (err) 
    {
        LOG_ERR("Failed to start codec: %d", err);
        // Blink blue LED to indicate error
        for (int i = 0; i < 5; i++) 
        {
            set_led_blue(!gpio_pin_get_dt(&led_blue));
            k_msleep(200);
        }
        set_led_blue(false);
        return err;
    }
    play_haptic_milli(500);
    set_led_blue(false);

    // Indicate microphone initialization
    set_led_red(true);
    set_led_green(true);
    LOG_INF("Starting microphone initialization");
    set_mic_callback(mic_handler);
    err = mic_start();
    if (err) 
    {
        LOG_ERR("Failed to start microphone: %d", err);
        // Blink red and green LEDs to indicate error
        for (int i = 0; i < 5; i++) 
        {
            set_led_red(!gpio_pin_get_dt(&led_red));
            set_led_green(!gpio_pin_get_dt(&led_green));
            k_msleep(200);
        }
        set_led_red(false);
        set_led_green(false);
        return err;
    }
    set_led_red(false);
    set_led_green(false);

    // save_offset(200);
    // // Initialize NFC first
    // LOG_INF("Initializing NFC...");
    // err = nfc_init();
    // if (err != 0) {
    //     LOG_ERR("Failed to initialize NFC: %d", err);
    //     // Consider whether to continue or return based on the severity of the error
    // } else {
    //     LOG_INF("NFC initialized successfully");
    // }

    // Indicate successful initialization
    err = init_usb();
    if (err)
    {
        LOG_ERR("Failed to initialize power supply: %d", err);
    }

    // button_init();
    // register_button_service();
    // activate_button_work();


    LOG_INF("Omi firmware initialized successfully\n");
    set_led_blue(true);
    k_msleep(1000);
    set_led_blue(false);
    printf("reset reas:%d\n",reset_reas);

    }
    printf("reset reas:%d\n",reset_reas);
	while (1)
	{
		set_led_state();
		k_msleep(500);
	}
	// Unreachable
	return 0;
}


