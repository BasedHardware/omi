#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <zephyr/sys/printk.h>

bool is_connected;
bool is_charging;
bool is_capturing;

uint16_t speak(uint16_t len, const void *buf)
{
    return len;
}

void mic_set_gain(uint8_t gain_level) {}

int rtc_set_utc_time(uint64_t utc_epoch_s)
{
    return 0;
}

uint32_t get_utc_time(void)
{
    return 0;
}

void sd_notify_time_synced(uint32_t utc_time) {}

void register_button_service(void) {}

int button_init(void)
{
    return 0;
}

void activate_button_work(void) {}

void turnoff_all(void)
{
    printk("OMI_BSIM_SLEEP\n");
}
