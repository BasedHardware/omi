#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::ffi::{c_char, c_int, c_uint, c_void};

pub const OMI_DEVICE_SPI_FLASH: c_int = 0;
pub const OMI_DEVICE_ADC: c_int = 1;
pub const OMI_DEVICE_SDHC0: c_int = 2;
pub const OMI_DEVICE_DMIC0: c_int = 3;

pub const OMI_PIN_MOTOR: c_int = 0;
pub const OMI_PIN_BAT_POWER: c_int = 1;
pub const OMI_PIN_BAT_READ: c_int = 2;
pub const OMI_PIN_BAT_CHG: c_int = 3;
pub const OMI_PIN_SD_EN: c_int = 4;

pub const PM_DEVICE_ACTION_RESUME: c_int = 0;
pub const PM_DEVICE_ACTION_SUSPEND: c_int = 1;
pub const PM_DEVICE_ACTION_TURN_ON: c_int = 2;
pub const PM_DEVICE_ACTION_TURN_OFF: c_int = 3;
pub const PM_DEVICE_ACTION_LOW_POWER: c_int = 4;

pub const ADC_GAIN_1_3: c_int = 3;

pub const DMIC_TRIGGER_START: c_int = 0;
pub const DMIC_TRIGGER_STOP: c_int = 1;

pub const DISK_IOCTL_CTRL_INIT: u8 = 0x10;
pub const DISK_IOCTL_GET_SECTOR_COUNT: u8 = 0x01;
pub const DISK_IOCTL_GET_SECTOR_SIZE: u8 = 0x02;
pub const DISK_IOCTL_CTRL_DEINIT: u8 = 0x11;
pub const FS_EXT2: c_int = 3;

pub type omi_gpio_edge_cb_t = Option<unsafe extern "C" fn(*mut c_void)>;
pub type omi_haptic_write_cb_t = Option<unsafe extern "C" fn(u8)>;

pub type settings_read_cb =
    unsafe extern "C" fn(cb_arg: *mut c_void, data: *mut c_void, len: usize) -> c_int;
pub type omi_settings_set_cb = unsafe extern "C" fn(
    name: *const c_char,
    len: usize,
    read_cb: settings_read_cb,
    cb_arg: *mut c_void,
    user_data: *mut c_void,
) -> c_int;

pub type omi_work_callback_t = Option<unsafe extern "C" fn(user_data: *mut c_void)>;

extern "C" {
    // LED helpers
    pub fn omi_led_ready_red() -> bool;
    pub fn omi_led_ready_green() -> bool;
    pub fn omi_led_ready_blue() -> bool;

    pub fn omi_led_period_red() -> c_uint;
    pub fn omi_led_period_green() -> c_uint;
    pub fn omi_led_period_blue() -> c_uint;

    pub fn omi_led_set_red(pulse_width_ns: c_uint) -> c_int;
    pub fn omi_led_set_green(pulse_width_ns: c_uint) -> c_int;
    pub fn omi_led_set_blue(pulse_width_ns: c_uint) -> c_int;

    // Device helpers
    pub fn omi_device_get(id: c_int) -> *const c_void;
    pub fn omi_device_is_ready(dev: *const c_void) -> bool;
    pub fn omi_pm_device_action(dev: *const c_void, action: c_int) -> c_int;
    pub fn omi_device_name(dev: *const c_void) -> *const c_char;

    // GPIO helpers
    pub fn omi_gpio_pin(id: c_int) -> *const c_void;
    pub fn omi_gpio_is_ready(pin: *const c_void) -> bool;
    pub fn omi_gpio_configure(pin: *const c_void, flags: u32) -> c_int;
    pub fn omi_gpio_set(pin: *const c_void, value: c_int) -> c_int;
    pub fn omi_gpio_get(pin: *const c_void) -> c_int;
    pub fn omi_gpio_flag_output() -> u32;
    pub fn omi_gpio_flag_input() -> u32;

    // ADC helpers
    pub fn omi_adc_sequence_init(
        sequence: *mut c_void,
        channel_mask: u32,
        buffer: *mut c_void,
        buffer_size: usize,
        resolution: u8,
    );
    pub fn omi_adc_channel_setup(adc_dev: *const c_void, cfg: *const c_void) -> c_int;
    pub fn omi_adc_read(adc_dev: *const c_void, sequence: *const c_void) -> c_int;
    pub fn omi_adc_ref_internal_mv(adc_dev: *const c_void) -> u16;
    pub fn omi_adc_raw_to_millivolts(
        vref_mv: u16,
        gain: c_int,
        resolution: u8,
        value: *mut i32,
    ) -> c_int;

    // Delayable work helpers
    pub fn omi_delayable_work_create(
        cb: omi_work_callback_t,
        user_data: *mut c_void,
    ) -> *mut c_void;
    pub fn omi_delayable_work_destroy(wrapper: *mut c_void);
    pub fn omi_delayable_work_set_user_data(wrapper: *mut c_void, user_data: *mut c_void);
    pub fn omi_delayable_work_schedule(wrapper: *mut c_void, delay_ms: u32) -> c_int;
    pub fn omi_delayable_work_cancel(wrapper: *mut c_void) -> c_int;

    // File system helpers
    pub fn omi_disk_access_ioctl(disk: *const c_char, cmd: u8, buffer: *mut c_void) -> c_int;
    pub fn omi_fs_mount(mount: *mut c_void) -> c_int;
    pub fn omi_fs_unmount(mount: *mut c_void) -> c_int;
    pub fn omi_fs_mkfs(
        fs_type: c_int,
        storage_dev: usize,
        scratch: *mut c_void,
        scratch_size: u32,
    ) -> c_int;

    // DMIC helpers
    pub fn omi_dmic_configure(dev: *const c_void, cfg: *const c_void) -> c_int;
    pub fn omi_dmic_trigger(dev: *const c_void, trigger: c_int) -> c_int;
    pub fn omi_dmic_read(
        dev: *const c_void,
        stream: u8,
        buffer: *mut *mut c_void,
        size: *mut u32,
        timeout_ms: i32,
    ) -> c_int;
    pub fn omi_mic_configure(sample_rate: u32, channels: u8) -> c_int;

    // Logging helpers
    pub fn omi_log_inf(msg: *const c_char);
    pub fn omi_log_err(msg: *const c_char);

    // Settings helpers
    pub fn omi_settings_subsys_init() -> c_int;
    pub fn omi_settings_load() -> c_int;
    pub fn omi_settings_save_one(name: *const c_char, value: *const c_void, len: usize) -> c_int;
    pub fn omi_settings_name_steq(
        name: *const c_char,
        key: *const c_char,
        next: *mut *const c_char,
    ) -> bool;
    pub fn omi_settings_register_handler(
        subtree: *const c_char,
        set_cb: omi_settings_set_cb,
        user_data: *mut c_void,
    ) -> c_int;

    // SAADC helpers
    pub fn omi_saadc_trigger_offset_calibration();

    // Battery helpers
    pub fn omi_battery_prepare_measurement_pin() -> c_int;
    pub fn omi_battery_restore_measurement_pin() -> c_int;
    pub fn omi_battery_channel_setup() -> c_int;
    pub fn omi_battery_perform_read(
        buffer: *mut i16,
        sample_count: usize,
        extra_samplings: u32,
    ) -> c_int;
    pub fn omi_battery_configure_pins() -> c_int;
    pub fn omi_battery_set_chg_handler(cb: omi_gpio_edge_cb_t, user_data: *mut c_void) -> c_int;
    pub fn omi_battery_enable_chg_interrupt() -> c_int;
    pub fn omi_battery_disable_chg_interrupt() -> c_int;
    pub fn omi_battery_read_chg_pin() -> c_int;

    pub fn omi_sleep_ms(ms: u32);
    pub fn omi_busy_wait_us(us: u32);

    // Thread & memory helpers
    pub fn omi_mic_mem_slab() -> *mut c_void;
    pub fn omi_mem_slab_alloc(slab: *mut c_void, mem: *mut *mut c_void, timeout_ms: u32) -> c_int;
    pub fn omi_mem_slab_free(slab: *mut c_void, mem: *mut c_void) -> c_int;
    pub fn omi_thread_create(
        entry: unsafe extern "C" fn(*mut c_void, *mut c_void, *mut c_void),
        p1: *mut c_void,
        p2: *mut c_void,
        p3: *mut c_void,
        priority: c_int,
    ) -> *mut c_void;
    pub fn omi_thread_start(thread: *mut c_void);
    pub fn omi_thread_abort(thread: *mut c_void);

    // Haptic helpers
    pub fn omi_haptic_register_service(cb: omi_haptic_write_cb_t) -> c_int;

    // SD helpers
    pub fn omi_sd_drive_name() -> *const c_char;
    pub fn omi_sd_mount_point() -> *const c_char;
    pub fn omi_sd_mount_struct() -> *mut c_void;
    pub fn omi_sd_device() -> *const c_void;
    pub fn omi_sd_enable_pin() -> *const c_void;

    // Misc
    pub fn printk(fmt: *const u8, ...) -> c_int;
}
