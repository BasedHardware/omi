/* Startup-only doubles, compiled against the production seam declarations.
 * Every synthetic milestone is labelled SIM. No device IO or BLE stack.
 */
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include "imu.h"
#include "lib/core/codec.h"
#include "lib/core/led.h"
#include "lib/core/lib/battery/battery.h"
#include "lib/core/mic.h"
#include "lib/core/sd_card.h"
#include "lib/core/storage.h"
#include "lib/core/transport.h"
#include "safe_mode.h"
#include "safe_mode_sim_mgmt.h"
#include "spi_flash.h"
#include "wdog_facade.h"

LOG_MODULE_REGISTER(sim_stubs, CONFIG_LOG_DEFAULT_LEVEL);

uint8_t battery_percentage = 75;
static bool watchdog_ready;
static unsigned int feeds;
static mix_handler mic_callback;
static codec_callback encoded_callback;

int watchdog_init(void)
{
    watchdog_ready = true;
    LOG_INF("SIM: Watchdog initialized (stub, no reset enforcement)");
    return 0;
}

void watchdog_feed(void)
{
    __ASSERT(watchdog_ready, "main fed an uninitialized watchdog stub");
    if (++feeds == 2) {
        /* Witness that main reached its loop and slept/yielded at least once. */
        LOG_INF("SIM: main loop alive (2 watchdog feeds)");
    }
}

int flash_off(void)
{
    return 0;
}
int led_start(void)
{
    return 0;
}
void set_led_red(bool on)
{
    ARG_UNUSED(on);
}
void set_led_green(bool on)
{
    ARG_UNUSED(on);
}
void set_led_blue(bool on)
{
    ARG_UNUSED(on);
}
void set_led_pwm(led_color_t color, uint8_t level)
{
    ARG_UNUSED(color);
    ARG_UNUSED(level);
}
void led_off(void) {}
int lsm6dsl_time_boot_adjust_rtc(void)
{
    return 0;
}
int battery_init(void)
{
    LOG_INF("SIM: battery stub reports 75%%");
    return 0;
}
int battery_charge_start(void)
{
    return 0;
}
void capture_mute_apply_runtime(void) {}

int app_sd_init(void)
{
    LOG_INF("SIM: SD init stub (no card or filesystem)");
    return 0;
}
void sd_notify_time_synced(uint32_t utc_time)
{
    ARG_UNUSED(utc_time);
}
int storage_init(void)
{
    LOG_INF("SIM: storage init stub (no storage worker)");
    return 0;
}
int transport_start(void)
{
    LOG_INF("SIM: Transport bluetooth initialized (stub; BLE disabled)");
    LOG_INF("SIM: Advertising successfully started (stub; no radio)");
    return 0;
}
int broadcast_audio_packets(uint8_t *buffer, size_t size)
{
    ARG_UNUSED(buffer);
    ARG_UNUSED(size);
    return -ENOTSUP;
}
void set_codec_callback(codec_callback callback)
{
    encoded_callback = callback;
}
int codec_start(void)
{
    __ASSERT(encoded_callback != NULL, "main must register codec callback first");
    LOG_INF("SIM: codec init stub (ARM Opus not linked)");
    return 0;
}
int codec_receive_pcm(int16_t *data, size_t len)
{
    ARG_UNUSED(data);
    ARG_UNUSED(len);
    return -ENOTSUP;
}
void set_mic_callback(mix_handler callback)
{
    mic_callback = callback;
}
int mic_start(void)
{
    __ASSERT(mic_callback != NULL, "main must register microphone callback first");
    LOG_INF("SIM: Microphone started (stub; no PCM generated)");
    return 0;
}

static struct mgmt_callback *sim_dfu_callback;
void mgmt_callback_register(struct mgmt_callback *callback)
{
    sim_dfu_callback = callback;
}

bool transport_advertising_started(void)
{
    return true;
}
int transport_start_safe(void)
{
    return 0;
}

void safe_mode_run(void)
{
    printk("Safe mode initialized: BLE DFU only\n");
    printk("Safe mode feed loop started\n");
    safe_mode_persist();
    for (;;) {
        watchdog_feed();
        k_msleep(1000);
#ifdef CONFIG_OMI_SIM_FINISH_DFU
        if (sim_dfu_callback) {
            struct img_mgmt_upload_req req = {.image = 0};
            struct img_mgmt_upload_action action = {.area_id = FIXED_PARTITION_ID(slot1_partition)};
            struct img_mgmt_upload_check check = {.req = &req, .action = &action};
            int32_t rc = 0;
            bool abort_more = false;
            sim_dfu_callback->callback(
                MGMT_EVT_OP_IMG_MGMT_DFU_CHUNK, MGMT_CB_OK, &rc, NULL, &abort_more, &check, sizeof(check));
            sim_dfu_callback->callback(MGMT_EVT_OP_IMG_MGMT_DFU_PENDING, MGMT_CB_OK, NULL, NULL, NULL, NULL, 0);
            sim_dfu_callback = NULL;
        }
#endif
    }
}
