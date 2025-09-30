#pragma once

#include <stdint.h>
#include <stdbool.h>

#include <zephyr/device.h>
#include <zephyr/drivers/adc.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/fs/fs.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/pm/device.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>

// -----------------------------------------------------------------------------
// LED helpers
// -----------------------------------------------------------------------------

bool omi_led_ready_red(void);
bool omi_led_ready_green(void);
bool omi_led_ready_blue(void);

uint32_t omi_led_period_red(void);
uint32_t omi_led_period_green(void);
uint32_t omi_led_period_blue(void);

int omi_led_set_red(uint32_t pulse_width_ns);
int omi_led_set_green(uint32_t pulse_width_ns);
int omi_led_set_blue(uint32_t pulse_width_ns);

// -----------------------------------------------------------------------------
// Device helpers
// -----------------------------------------------------------------------------

enum omi_device_id {
    OMI_DEVICE_SPI_FLASH,
    OMI_DEVICE_ADC,
    OMI_DEVICE_SDHC0,
    OMI_DEVICE_DMIC0,
};

const struct device *omi_device_get(enum omi_device_id id);
bool omi_device_is_ready(const struct device *dev);
int omi_pm_device_action(const struct device *dev, enum pm_device_action action);
const char *omi_device_name(const struct device *dev);

// -----------------------------------------------------------------------------
// GPIO helpers
// -----------------------------------------------------------------------------

enum omi_gpio_pin_id {
    OMI_PIN_MOTOR,
    OMI_PIN_BAT_POWER,
    OMI_PIN_BAT_READ,
    OMI_PIN_BAT_CHG,
    OMI_PIN_SD_EN,
};

const struct gpio_dt_spec *omi_gpio_pin(enum omi_gpio_pin_id id);
bool omi_gpio_is_ready(const struct gpio_dt_spec *pin);
int omi_gpio_configure(const struct gpio_dt_spec *pin, gpio_flags_t flags);
int omi_gpio_set(const struct gpio_dt_spec *pin, int value);
int omi_gpio_get(const struct gpio_dt_spec *pin);

// Commonly used GPIO flags re-exported for FFI consumers
enum {
    OMI_GPIO_OUTPUT = GPIO_OUTPUT,
    OMI_GPIO_INPUT = GPIO_INPUT,
    OMI_GPIO_PULL_UP = GPIO_PULL_UP,
    OMI_GPIO_PULL_DOWN = GPIO_PULL_DOWN,
};

uint32_t omi_gpio_flag_output(void);
uint32_t omi_gpio_flag_input(void);

// nRF drive strengths often needed by battery code
#ifdef NRF_GPIO_DRIVE_S0H1
enum {
    OMI_GPIO_DRIVE_S0H1 = NRF_GPIO_DRIVE_S0H1,
};
#endif

// -----------------------------------------------------------------------------
// ADC helpers
// -----------------------------------------------------------------------------

void omi_adc_sequence_init(struct adc_sequence *sequence, uint32_t channel_mask, void *buffer, size_t buffer_size, uint8_t resolution);
int omi_adc_channel_setup(const struct device *adc_dev, const struct adc_channel_cfg *cfg);
int omi_adc_read(const struct device *adc_dev, const struct adc_sequence *sequence);
uint16_t omi_adc_ref_internal_mv(const struct device *adc_dev);
int omi_adc_raw_to_millivolts(uint16_t vref, enum adc_gain gain, uint8_t resolution, int32_t *val);

// -----------------------------------------------------------------------------
// Delayable work helpers
// -----------------------------------------------------------------------------

typedef void (*omi_work_callback_t)(void *user_data);

struct omi_delayable_work;

struct omi_delayable_work *omi_delayable_work_create(omi_work_callback_t cb, void *user_data);
void omi_delayable_work_destroy(struct omi_delayable_work *wrapper);
void omi_delayable_work_set_user_data(struct omi_delayable_work *wrapper, void *user_data);
int omi_delayable_work_schedule(struct omi_delayable_work *wrapper, uint32_t delay_ms);
int omi_delayable_work_cancel(struct omi_delayable_work *wrapper);

// -----------------------------------------------------------------------------
// File system helpers
// -----------------------------------------------------------------------------

int omi_disk_access_ioctl(const char *disk_pdrv, uint8_t cmd, void *buffer);
int omi_fs_mount(struct fs_mount_t *mount);
int omi_fs_unmount(struct fs_mount_t *mount);
int omi_fs_mkfs(fs_system_t type, uintptr_t storage_dev, void *scratch, uint32_t scratch_size);

// -----------------------------------------------------------------------------
// DMIC helpers
// -----------------------------------------------------------------------------

int omi_dmic_configure(const struct device *dev, const struct dmic_cfg *cfg);
int omi_dmic_trigger(const struct device *dev, enum dmic_trigger trigger);
int omi_dmic_read(const struct device *dev, uint8_t stream, void **buffer, uint32_t *size, int32_t timeout_ms);
int omi_mic_configure(uint32_t sample_rate, uint8_t channels);

// -----------------------------------------------------------------------------
// Logging helpers
// -----------------------------------------------------------------------------

void omi_log_inf(const char *msg);
void omi_log_err(const char *msg);

// -----------------------------------------------------------------------------
// Settings helpers
// -----------------------------------------------------------------------------

int omi_settings_subsys_init(void);
int omi_settings_load(void);
int omi_settings_save_one(const char *name, const void *value, size_t len);
bool omi_settings_name_steq(const char *name, const char *key, const char **next);

typedef int (*omi_settings_set_cb)(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg, void *user_data);

int omi_settings_register_handler(const char *subtree, omi_settings_set_cb set_cb, void *user_data);

// -----------------------------------------------------------------------------
// SAADC helpers
// -----------------------------------------------------------------------------

void omi_saadc_trigger_offset_calibration(void);

// -----------------------------------------------------------------------------
// Battery helpers
// -----------------------------------------------------------------------------

typedef void (*omi_gpio_edge_cb_t)(void *user_data);

int omi_battery_prepare_measurement_pin(void);
int omi_battery_restore_measurement_pin(void);
int omi_battery_channel_setup(void);
int omi_battery_perform_read(int16_t *buffer, size_t sample_count, uint32_t extra_samplings);
int omi_battery_configure_pins(void);
int omi_battery_set_chg_handler(omi_gpio_edge_cb_t handler, void *user_data);
int omi_battery_enable_chg_interrupt(void);
int omi_battery_disable_chg_interrupt(void);
int omi_battery_read_chg_pin(void);

void omi_sleep_ms(uint32_t ms);
void omi_busy_wait_us(uint32_t us);
// -----------------------------------------------------------------------------
// Thread/memory helpers
// -----------------------------------------------------------------------------

#include <zephyr/kernel.h>

struct k_thread;
struct k_mem_slab;

struct k_thread *omi_thread_create(void (*entry)(void *, void *, void *), void *p1, void *p2, void *p3, int priority);
void omi_thread_start(struct k_thread *thread);
void omi_thread_abort(struct k_thread *thread);

struct k_mem_slab *omi_mic_mem_slab(void);
int omi_mem_slab_alloc(struct k_mem_slab *slab, void **mem, uint32_t timeout_ms);
int omi_mem_slab_free(struct k_mem_slab *slab, void *mem);

// -----------------------------------------------------------------------------
// Haptic helpers
// -----------------------------------------------------------------------------

typedef void (*omi_haptic_write_cb_t)(uint8_t value);

int omi_haptic_register_service(omi_haptic_write_cb_t cb);

// -----------------------------------------------------------------------------
// SD card helpers
// -----------------------------------------------------------------------------

const char *omi_sd_drive_name(void);
const char *omi_sd_mount_point(void);
struct fs_mount_t *omi_sd_mount_struct(void);
const struct device *omi_sd_device(void);
const struct gpio_dt_spec *omi_sd_enable_pin(void);
