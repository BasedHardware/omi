#include "shims.h"
#include "ble_manifest.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/flash.h>
#include <zephyr/fs/fs.h>
#include <zephyr/storage/disk_access.h>
#include <zephyr/sys/util.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/audio/dmic.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <hal/nrf_saadc.h>
#include <errno.h>

#define LOG_MODULE_NAME omi_shims
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(LOG_MODULE_NAME);

#include <errno.h>

// LED PWM specs
static const struct pwm_dt_spec led_red = PWM_DT_SPEC_GET(DT_NODELABEL(led_red));
static const struct pwm_dt_spec led_green = PWM_DT_SPEC_GET(DT_NODELABEL(led_green));
static const struct pwm_dt_spec led_blue = PWM_DT_SPEC_GET(DT_NODELABEL(led_blue));

static const struct device *const battery_adc = DEVICE_DT_GET(DT_NODELABEL(adc));
static const struct gpio_dt_spec battery_read_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_read_pin), gpios, {0});
static const struct gpio_dt_spec battery_chg_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});

static const struct device *const dmic_dev = DEVICE_DT_GET(DT_ALIAS(dmic0));

static const struct device *const sd_dev = DEVICE_DT_GET(DT_NODELABEL(sdhc0));
static const struct gpio_dt_spec sd_en_pin = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

#define DISK_DRIVE_NAME "SDMMC"
#define DISK_MOUNT_PT "/ext"

static struct fs_mount_t sd_mount = {
    .type = FS_EXT2,
    .flags = FS_MOUNT_FLAG_NO_FORMAT,
    .storage_dev = (void *)DISK_DRIVE_NAME,
    .mnt_point = DISK_MOUNT_PT,
};

#define MAX_SAMPLE_RATE 16000
#define SAMPLE_BIT_WIDTH 16
#define BYTES_PER_SAMPLE sizeof(int16_t)
#define MIC_BLOCK_SIZE(sample_rate, channels) (BYTES_PER_SAMPLE * ((sample_rate) / 10) * (channels))
#define MIC_MAX_BLOCK_SIZE MIC_BLOCK_SIZE(MAX_SAMPLE_RATE, 2)
#define MIC_BLOCK_COUNT 4

K_MEM_SLAB_DEFINE_STATIC(mic_mem_slab, MIC_MAX_BLOCK_SIZE, MIC_BLOCK_COUNT, sizeof(void *));

static struct gpio_callback battery_chg_cb;
static omi_gpio_edge_cb_t battery_chg_handler;
static void *battery_chg_user_data;

#define BATTERY_ADC_CHANNEL_ID 0
#define BATTERY_ADC_RESOLUTION 12
#define BATTERY_ADC_ACQ_TIME ADC_ACQ_TIME(ADC_ACQ_TIME_MICROSECONDS, 10)

static const struct adc_channel_cfg battery_channel_cfg = {
    .gain = ADC_GAIN_1_3,
    .reference = ADC_REF_INTERNAL,
    .acquisition_time = BATTERY_ADC_ACQ_TIME,
    .channel_id = BATTERY_ADC_CHANNEL_ID,
#if defined(CONFIG_ADC_CONFIGURABLE_INPUTS)
    .input_positive = NRF_SAADC_INPUT_AIN0,
#endif
};

static struct adc_sequence_options battery_sequence_opts = {
    .extra_samplings = 0,
    .interval_us = 0,
    .callback = NULL,
    .user_data = NULL,
};

bool omi_led_ready_red(void)
{
    return pwm_is_ready_dt(&led_red);
}

bool omi_led_ready_green(void)
{
    return pwm_is_ready_dt(&led_green);
}

bool omi_led_ready_blue(void)
{
    return pwm_is_ready_dt(&led_blue);
}

uint32_t omi_led_period_red(void)
{
    return led_red.period;
}

uint32_t omi_led_period_green(void)
{
    return led_green.period;
}

uint32_t omi_led_period_blue(void)
{
    return led_blue.period;
}

int omi_led_set_red(uint32_t pulse_width_ns)
{
    return pwm_set_pulse_dt(&led_red, pulse_width_ns);
}

int omi_led_set_green(uint32_t pulse_width_ns)
{
    return pwm_set_pulse_dt(&led_green, pulse_width_ns);
}

int omi_led_set_blue(uint32_t pulse_width_ns)
{
    return pwm_set_pulse_dt(&led_blue, pulse_width_ns);
}

// -----------------------------------------------------------------------------
// Device helpers

const struct device *omi_device_get(enum omi_device_id id)
{
    switch (id) {
    case OMI_DEVICE_SPI_FLASH:
        return DEVICE_DT_GET(DT_NODELABEL(spi_flash));
    case OMI_DEVICE_ADC:
        return DEVICE_DT_GET(DT_NODELABEL(adc));
    case OMI_DEVICE_SDHC0:
        return DEVICE_DT_GET(DT_NODELABEL(sdhc0));
    case OMI_DEVICE_DMIC0:
        return DEVICE_DT_GET(DT_ALIAS(dmic0));
    default:
        return NULL;
    }
}

bool omi_device_is_ready(const struct device *dev)
{
    return device_is_ready(dev);
}

int omi_pm_device_action(const struct device *dev, enum pm_device_action action)
{
    return pm_device_action_run(dev, action);
}

const char *omi_device_name(const struct device *dev)
{
    if (!dev) {
        return "<null>";
    }
    return dev->name;
}

// -----------------------------------------------------------------------------
// GPIO helpers

static const struct gpio_dt_spec gpio_motor = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(motor_pin), gpios, {0});
static const struct gpio_dt_spec gpio_bat_power = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(power_pin), gpios, {0});
static const struct gpio_dt_spec gpio_bat_read = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_read_pin), gpios, {0});
static const struct gpio_dt_spec gpio_bat_chg = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(bat_chg_pin), gpios, {0});
static const struct gpio_dt_spec gpio_sd_en = GPIO_DT_SPEC_GET_OR(DT_NODELABEL(sdcard_en_pin), gpios, {0});

const struct gpio_dt_spec *omi_gpio_pin(enum omi_gpio_pin_id id)
{
    switch (id) {
    case OMI_PIN_MOTOR:
        return &gpio_motor;
    case OMI_PIN_BAT_POWER:
        return &gpio_bat_power;
    case OMI_PIN_BAT_READ:
        return &gpio_bat_read;
    case OMI_PIN_BAT_CHG:
        return &gpio_bat_chg;
    case OMI_PIN_SD_EN:
        return &gpio_sd_en;
    default:
        return NULL;
    }
}

bool omi_gpio_is_ready(const struct gpio_dt_spec *pin)
{
    return gpio_is_ready_dt(pin);
}

int omi_gpio_configure(const struct gpio_dt_spec *pin, gpio_flags_t flags)
{
    return gpio_pin_configure_dt(pin, flags);
}

int omi_gpio_set(const struct gpio_dt_spec *pin, int value)
{
    return gpio_pin_set_dt(pin, value);
}

int omi_gpio_get(const struct gpio_dt_spec *pin)
{
    return gpio_pin_get_dt(pin);
}

uint32_t omi_gpio_flag_output(void)
{
    return GPIO_OUTPUT;
}

uint32_t omi_gpio_flag_input(void)
{
    return GPIO_INPUT;
}

// -----------------------------------------------------------------------------
// ADC helpers

static struct adc_sequence_options adc_seq_opts = {
    .interval_us = 0,
    .callback = NULL,
    .user_data = NULL,
};

void omi_adc_sequence_init(struct adc_sequence *sequence, uint32_t channel_mask, void *buffer, size_t buffer_size, uint8_t resolution)
{
    sequence->options = &adc_seq_opts;
    sequence->channels = channel_mask;
    sequence->buffer = buffer;
    sequence->buffer_size = buffer_size;
    sequence->resolution = resolution;
}

int omi_adc_channel_setup(const struct device *adc_dev, const struct adc_channel_cfg *cfg)
{
    return adc_channel_setup(adc_dev, cfg);
}

int omi_adc_read(const struct device *adc_dev, const struct adc_sequence *sequence)
{
    return adc_read(adc_dev, sequence);
}

uint16_t omi_adc_ref_internal_mv(const struct device *adc_dev)
{
    return adc_ref_internal(adc_dev);
}

int omi_adc_raw_to_millivolts(uint16_t vref, enum adc_gain gain, uint8_t resolution, int32_t *val)
{
    return adc_raw_to_millivolts(vref, gain, resolution, val);
}

// -----------------------------------------------------------------------------
// Delayable work helper

struct omi_delayable_work {
    struct k_work_delayable work;
    omi_work_callback_t callback;
    void *user_data;
};

static void omi_work_trampoline(struct k_work *work)
{
    struct k_work_delayable *dwork = CONTAINER_OF(work, struct k_work_delayable, work);
    struct omi_delayable_work *wrapper = CONTAINER_OF(dwork, struct omi_delayable_work, work);
    if (wrapper->callback) {
        wrapper->callback(wrapper->user_data);
    }
}

struct omi_delayable_work *omi_delayable_work_create(omi_work_callback_t cb, void *user_data)
{
    struct omi_delayable_work *wrapper = k_calloc(1, sizeof(*wrapper));
    if (!wrapper) {
        return NULL;
    }
    wrapper->callback = cb;
    wrapper->user_data = user_data;
    k_work_init_delayable(&wrapper->work, omi_work_trampoline);
    return wrapper;
}

void omi_delayable_work_destroy(struct omi_delayable_work *wrapper)
{
    if (!wrapper) {
        return;
    }
    k_work_cancel_delayable(&wrapper->work);
    k_free(wrapper);
}

void omi_delayable_work_set_user_data(struct omi_delayable_work *wrapper, void *user_data)
{
    if (wrapper) {
        wrapper->user_data = user_data;
    }
}

int omi_delayable_work_schedule(struct omi_delayable_work *wrapper, uint32_t delay_ms)
{
    return k_work_schedule(&wrapper->work, K_MSEC(delay_ms));
}

int omi_delayable_work_cancel(struct omi_delayable_work *wrapper)
{
    return k_work_cancel_delayable(&wrapper->work);
}

// -----------------------------------------------------------------------------
// PM counter helpers for SD card

int omi_disk_access_ioctl(const char *disk_pdrv, uint8_t cmd, void *buffer)
{
    return disk_access_ioctl(disk_pdrv, cmd, buffer);
}

int omi_fs_mount(struct fs_mount_t *mount)
{
    return fs_mount(mount);
}

int omi_fs_unmount(struct fs_mount_t *mount)
{
    return fs_unmount(mount);
}

int omi_fs_mkfs(fs_system_t type, uintptr_t storage_dev, void *scratch, uint32_t scratch_size)
{
    return fs_mkfs(type, storage_dev, scratch, scratch_size);
}

// -----------------------------------------------------------------------------
// DMIC helpers

int omi_dmic_configure(const struct device *dev, const struct dmic_cfg *cfg)
{
    return dmic_configure(dev, cfg);
}

int omi_dmic_trigger(const struct device *dev, enum dmic_trigger trigger)
{
    return dmic_trigger(dev, trigger);
}

int omi_dmic_read(const struct device *dev, uint8_t stream, void **buffer, uint32_t *size, int32_t timeout)
{
    return dmic_read(dev, stream, buffer, size, K_MSEC(timeout));
}

int omi_mic_configure(uint32_t sample_rate, uint8_t channels)
{
    if (!device_is_ready(dmic_dev)) {
        return -ENODEV;
    }

    struct pcm_stream_cfg stream = {
        .pcm_width = SAMPLE_BIT_WIDTH,
        .mem_slab = &mic_mem_slab,
        .pcm_rate = sample_rate,
        .block_size = MIC_BLOCK_SIZE(sample_rate, channels),
    };

    struct dmic_cfg cfg = {
        .io = {
            .min_pdm_clk_freq = 1000000,
            .max_pdm_clk_freq = 3500000,
            .min_pdm_clk_dc = 40,
            .max_pdm_clk_dc = 60,
        },
        .streams = &stream,
        .channel = {
            .req_num_streams = 1,
            .req_num_chan = channels,
            .req_chan_map_lo = dmic_build_channel_map(0, 0, PDM_CHAN_LEFT),
        },
    };

    int ret = dmic_configure(dmic_dev, &cfg);
    if (ret < 0) {
        return ret;
    }

    return 0;
}

// -----------------------------------------------------------------------------
// Logging helpers

void omi_log_inf(const char *msg)
{
    LOG_INF("%s", msg);
}

void omi_log_err(const char *msg)
{
    LOG_ERR("%s", msg);
}

// -----------------------------------------------------------------------------
// Battery helpers

static void battery_chg_trampoline(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(cb);
    ARG_UNUSED(pins);
    if (battery_chg_handler) {
        battery_chg_handler(battery_chg_user_data);
    }
}

int omi_battery_prepare_measurement_pin(void)
{
    int ret = gpio_pin_configure_dt(&battery_read_pin, GPIO_OUTPUT | NRF_GPIO_DRIVE_S0H1);
    if (ret < 0) {
        return ret;
    }
    ret = gpio_pin_set_dt(&battery_read_pin, 0);
    return ret;
}

int omi_battery_restore_measurement_pin(void)
{
    return gpio_pin_configure_dt(&battery_read_pin, GPIO_INPUT);
}

int omi_battery_channel_setup(void)
{
    return adc_channel_setup(battery_adc, &battery_channel_cfg);
}

int omi_battery_perform_read(int16_t *buffer, size_t sample_count, uint32_t extra_samplings)
{
    if (!buffer || sample_count == 0) {
        return -EINVAL;
    }

    struct adc_sequence sequence = {
        .options = &battery_sequence_opts,
        .channels = BIT(BATTERY_ADC_CHANNEL_ID),
        .buffer = buffer,
        .buffer_size = sample_count * sizeof(int16_t),
        .resolution = BATTERY_ADC_RESOLUTION,
    };

    battery_sequence_opts.extra_samplings = extra_samplings;

    return adc_read(battery_adc, &sequence);
}

int omi_battery_configure_pins(void)
{
    int err = gpio_pin_configure_dt(&battery_read_pin, GPIO_INPUT);
    if (err < 0) {
        return err;
    }

    err = gpio_pin_configure_dt(&battery_chg_pin, GPIO_INPUT | GPIO_PULL_UP);
    if (err < 0) {
        return err;
    }

    gpio_init_callback(&battery_chg_cb, battery_chg_trampoline, BIT(battery_chg_pin.pin));
    err = gpio_add_callback(battery_chg_pin.port, &battery_chg_cb);
    if (err < 0) {
        return err;
    }

    return 0;
}

int omi_battery_set_chg_handler(omi_gpio_edge_cb_t handler, void *user_data)
{
    battery_chg_handler = handler;
    battery_chg_user_data = user_data;
    return 0;
}

int omi_battery_enable_chg_interrupt(void)
{
    return gpio_pin_interrupt_configure_dt(&battery_chg_pin, GPIO_INT_EDGE_BOTH);
}

int omi_battery_disable_chg_interrupt(void)
{
    return gpio_pin_interrupt_configure_dt(&battery_chg_pin, GPIO_INT_DISABLE);
}

int omi_battery_read_chg_pin(void)
{
    return gpio_pin_get_dt(&battery_chg_pin);
}

void omi_sleep_ms(uint32_t ms)
{
    k_msleep(ms);
}

void omi_busy_wait_us(uint32_t us)
{
    k_busy_wait(us);
}

// -----------------------------------------------------------------------------
// Threads and memory slabs

struct k_mem_slab *omi_mic_mem_slab(void)
{
    return &mic_mem_slab;
}

int omi_mem_slab_alloc(struct k_mem_slab *slab, void **mem, uint32_t timeout_ms)
{
    return k_mem_slab_alloc(slab, mem, K_MSEC(timeout_ms));
}

int omi_mem_slab_free(struct k_mem_slab *slab, void *mem)
{
    return k_mem_slab_free(slab, mem);
}

#define MIC_THREAD_STACK_SIZE 2048
K_THREAD_STACK_DEFINE(mic_thread_stack, MIC_THREAD_STACK_SIZE);
static struct k_thread mic_thread;

struct k_thread *omi_thread_create(void (*entry)(void *, void *, void *), void *p1, void *p2, void *p3, int priority)
{
    k_tid_t tid = k_thread_create(&mic_thread,
                                  mic_thread_stack,
                                  K_THREAD_STACK_SIZEOF(mic_thread_stack),
                                  entry,
                                  p1,
                                  p2,
                                  p3,
                                  priority,
                                  0,
                                  K_NO_WAIT);
    ARG_UNUSED(tid);
    return &mic_thread;
}

void omi_thread_start(struct k_thread *thread)
{
    if (thread) {
        k_thread_start(thread);
    }
}

void omi_thread_abort(struct k_thread *thread)
{
    if (thread) {
        k_thread_abort(thread);
    }
}

// -----------------------------------------------------------------------------
// Haptic helpers

static omi_haptic_write_cb_t haptic_write_cb;

static ssize_t haptic_write_handler(struct bt_conn *conn,
                                    const struct bt_gatt_attr *attr,
                                    const void *buf,
                                    uint16_t len,
                                    uint16_t offset,
                                    uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    ARG_UNUSED(offset);
    ARG_UNUSED(flags);

    if (len < 1) {
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    }

    if (haptic_write_cb) {
        haptic_write_cb(((const uint8_t *)buf)[0]);
    }

    return len;
}

static struct bt_uuid_128 haptic_service_uuid;
static struct bt_uuid_128 haptic_char_uuid;
static bool haptic_uuid_initialized;

static int ensure_haptic_uuids(void)
{
    if (haptic_uuid_initialized) {
        return 0;
    }

    int err = bt_uuid_from_str(omi_ble_haptic_service_uuid(), &haptic_service_uuid.uuid);
    if (err) {
        return err;
    }

    err = bt_uuid_from_str(omi_ble_haptic_command_uuid(), &haptic_char_uuid.uuid);
    if (err) {
        return err;
    }

    haptic_uuid_initialized = true;
    return 0;
}

static struct bt_gatt_attr haptic_attrs[] = {
    BT_GATT_PRIMARY_SERVICE(&haptic_service_uuid),
    BT_GATT_CHARACTERISTIC(&haptic_char_uuid.uuid,
                           BT_GATT_CHRC_WRITE,
                           BT_GATT_PERM_WRITE,
                           NULL,
                           haptic_write_handler,
                           NULL),
};

static struct bt_gatt_service haptic_service = BT_GATT_SERVICE(haptic_attrs);

int omi_haptic_register_service(omi_haptic_write_cb_t cb)
{
    int err = ensure_haptic_uuids();
    if (err) {
        return err;
    }

    haptic_write_cb = cb;
    return bt_gatt_service_register(&haptic_service);
}

// -----------------------------------------------------------------------------
// SD card helpers

const char *omi_sd_drive_name(void)
{
    return DISK_DRIVE_NAME;
}

const char *omi_sd_mount_point(void)
{
    return DISK_MOUNT_PT;
}

struct fs_mount_t *omi_sd_mount_struct(void)
{
    return &sd_mount;
}

const struct device *omi_sd_device(void)
{
    return sd_dev;
}

const struct gpio_dt_spec *omi_sd_enable_pin(void)
{
    return &sd_en_pin;
}

// -----------------------------------------------------------------------------
// Settings helpers

int omi_settings_subsys_init(void)
{
    return settings_subsys_init();
}

int omi_settings_load(void)
{
    return settings_load();
}

int omi_settings_save_one(const char *name, const void *value, size_t len)
{
    return settings_save_one(name, value, len);
}

bool omi_settings_name_steq(const char *name, const char *key, const char **next)
{
    return settings_name_steq(name, key, next);
}

static omi_settings_set_cb g_settings_cb;
static void *g_settings_user_data;

static int omi_settings_set_trampoline(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
    if (!g_settings_cb) {
        return -ENOENT;
    }
    return g_settings_cb(name, len, read_cb, cb_arg, g_settings_user_data);
}

int omi_settings_register_handler(const char *subtree, omi_settings_set_cb set_cb, void *user_data)
{
    static struct settings_handler handler = {
        .name = NULL,
        .h_set = omi_settings_set_trampoline,
        .h_get = NULL,
        .h_commit = NULL,
        .h_export = NULL,
    };

    handler.name = subtree;
    g_settings_cb = set_cb;
    g_settings_user_data = user_data;
    return settings_register(&handler);
}

// -----------------------------------------------------------------------------
// SAADC helpers

void omi_saadc_trigger_offset_calibration(void)
{
    NRF_SAADC_S->TASKS_CALIBRATEOFFSET = 1;
}
