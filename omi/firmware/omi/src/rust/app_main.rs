use core::sync::atomic::{AtomicU32, Ordering};

use crate::ffi;
use crate::hal;
use crate::util;

const MIC_BUFFER_SAMPLES: usize = 1600;
const ENABLE_BATTERY: bool = option_env!("CONFIG_OMI_ENABLE_BATTERY").is_some();
const ENABLE_BUTTON: bool = option_env!("CONFIG_OMI_ENABLE_BUTTON").is_some();
const ENABLE_HAPTIC: bool = option_env!("CONFIG_OMI_ENABLE_HAPTIC").is_some();
const ENABLE_OFFLINE_STORAGE: bool = option_env!("CONFIG_OMI_ENABLE_OFFLINE_STORAGE").is_some();

#[no_mangle]
pub static mut is_connected: bool = false;
#[no_mangle]
pub static mut is_charging: bool = false;
#[no_mangle]
pub static mut is_off: bool = false;

#[no_mangle]
pub static mut gatt_notify_count: u32 = 0;
#[no_mangle]
pub static mut total_mic_buffer_bytes: u32 = 0;
#[no_mangle]
pub static mut broadcast_audio_count: u32 = 0;
#[no_mangle]
pub static mut write_to_tx_queue_count: u32 = 0;

static MIC_BUFFER_TOTAL: AtomicU32 = AtomicU32::new(0);

extern "C" {
    fn flash_off() -> i32;
    fn app_sd_off() -> i32;
    fn app_settings_init() -> i32;
    fn app_settings_save_dim_ratio(ratio: u8) -> i32;
    fn led_start() -> i32;
    fn set_led_red(on: bool);
    fn set_led_green(on: bool);
    fn set_led_blue(on: bool);
    fn battery_init() -> i32;
    fn battery_charge_start() -> i32;
    fn button_init() -> i32;
    fn activate_button_work();
    fn haptic_init() -> i32;
    fn play_haptic_milli(duration: u32);
    fn register_haptic_service();
    fn transport_start() -> i32;
    fn set_codec_callback(cb: extern "C" fn(*mut u8, usize));
    fn codec_start() -> i32;
    fn broadcast_audio_packets(data: *mut u8, len: usize) -> i32;
    fn codec_receive_pcm(buffer: *mut i16, samples: usize) -> i32;
    fn mic_start() -> i32;
    fn set_mic_callback(cb: unsafe extern "C" fn(*mut i16));
    fn mic_on();
    fn mic_off();
}

fn log_model_info() {
    if let Some(model) = option_env!("CONFIG_BT_DIS_MODEL") {
        util::log_info_fmt(format_args!("Model: {model}"));
    }
    if let Some(fw) = option_env!("CONFIG_BT_DIS_FW_REV_STR") {
        util::log_info_fmt(format_args!("Firmware revision: {fw}"));
    }
    if let Some(hw) = option_env!("CONFIG_BT_DIS_HW_REV_STR") {
        util::log_info_fmt(format_args!("Hardware revision: {hw}"));
    }
}

fn boot_led_sequence() {
    unsafe {
        set_led_red(true);
    }
    hal::sleep_ms(600);
    unsafe { set_led_red(false) };
    hal::sleep_ms(200);

    unsafe { set_led_green(true) };
    hal::sleep_ms(600);
    unsafe { set_led_green(false) };
    hal::sleep_ms(200);

    unsafe { set_led_blue(true) };
    hal::sleep_ms(600);
    unsafe { set_led_blue(false) };
    hal::sleep_ms(200);

    unsafe {
        set_led_red(true);
        set_led_green(true);
        set_led_blue(true);
    }
    hal::sleep_ms(600);
    unsafe {
        set_led_red(false);
        set_led_green(false);
        set_led_blue(false);
    }
}

fn set_led_state() {
    unsafe {
        set_led_green(is_charging);
        set_led_red(!(is_off || is_connected));
        set_led_blue(is_connected);
    }
}

fn suspend_unused_modules() {
    let err = unsafe { flash_off() };
    if err < 0 {
        util::log_error_fmt(format_args!("Cannot suspend SPI flash: {err}"));
    }

    let err = unsafe { app_sd_off() };
    if err < 0 {
        util::log_error_fmt(format_args!("Cannot suspend SD card: {err}"));
    }
}

extern "C" fn codec_handler(data: *mut u8, len: usize) {
    unsafe {
        broadcast_audio_count = broadcast_audio_count.wrapping_add(1);
        let err = broadcast_audio_packets(data, len);
        if err < 0 {
            util::log_error_fmt(format_args!("Failed to broadcast audio packets: {err}"));
        }
    }
}

unsafe extern "C" fn mic_handler(buffer: *mut i16) {
    MIC_BUFFER_TOTAL.fetch_add(1, Ordering::Relaxed);
    let err = codec_receive_pcm(buffer, MIC_BUFFER_SAMPLES);
    if err < 0 {
        util::log_error_fmt(format_args!("Failed to process PCM data: {err}"));
    }
}

fn loop_body() {
    let total_bytes = MIC_BUFFER_TOTAL.load(Ordering::Relaxed);
    unsafe {
        total_mic_buffer_bytes = total_bytes;
    }

    unsafe {
        util::log_info_fmt(format_args!(
            "Total mic buffer bytes: {total_bytes}, GATT notify count: {gatt_notify_count}, \
Broadcast count: {broadcast_audio_count}, TX queue writes: {write_to_tx_queue_count}"
        ));
    }

    set_led_state();
    hal::sleep_ms(1000);
}

#[no_mangle]
pub extern "C" fn main() -> i32 {
    unsafe {
        ffi::printk(b"Starting omi ...\n\0".as_ptr());
    }

    util::log_info("Suspending unused modules...\n");
    suspend_unused_modules();

    util::log_info("Initializing settings...\n");
    let mut ret = unsafe { app_settings_init() };
    if ret < 0 {
        util::log_error_fmt(format_args!("Failed to initialize settings ({ret})"));
        unsafe {
            app_settings_save_dim_ratio(5);
            set_led_red(true);
            hal::sleep_ms(500);
            set_led_red(false);
            hal::sleep_ms(200);
            app_settings_save_dim_ratio(100);
            set_led_red(true);
            hal::sleep_ms(500);
            set_led_red(false);
            hal::sleep_ms(200);
            app_settings_save_dim_ratio(30);
            set_led_red(true);
            hal::sleep_ms(500);
            set_led_red(false);
        }
    }

    util::log_info("Initializing LEDs...\n");
    ret = unsafe { led_start() };
    if ret < 0 {
        util::log_error_fmt(format_args!("Failed to initialize LEDs ({ret})"));
        return ret;
    }

    boot_led_sequence();

    if ENABLE_BATTERY {
        let err = unsafe { battery_init() };
        if err < 0 {
            util::log_error_fmt(format_args!("Battery init failed ({err})"));
            return err;
        }

        let err = unsafe { battery_charge_start() };
        if err < 0 {
            util::log_error_fmt(format_args!("Battery failed to start ({err})"));
            return err;
        }
        util::log_info("Battery initialized\n");
    }

    if ENABLE_BUTTON {
        let err = unsafe { button_init() };
        if err < 0 {
            util::log_error_fmt(format_args!("Failed to initialize Button ({err})"));
            return err;
        }
        unsafe { activate_button_work() };
        util::log_info("Button initialized\n");
    }

    if ENABLE_HAPTIC {
        let err = unsafe { haptic_init() };
        if err < 0 {
            util::log_error_fmt(format_args!("Failed to initialize Haptic ({err})"));
        } else {
            util::log_info("Haptic driver initialized\n");
            unsafe { play_haptic_milli(100) };
        }
    }

    log_model_info();

    if ENABLE_OFFLINE_STORAGE {
        util::log_info("Initializing transport...\n");
    }

    let transport_err = unsafe { transport_start() };
    if transport_err < 0 {
        util::log_error_fmt(format_args!("Failed to start transport ({transport_err})"));
        return transport_err;
    }

    util::log_info("Initializing codec...\n");
    unsafe { set_codec_callback(codec_handler) };
    ret = unsafe { codec_start() };
    if ret < 0 {
        util::log_error_fmt(format_args!("Failed to start codec ({ret})"));
        return ret;
    }

    util::log_info("Initializing microphone...\n");
    unsafe { set_mic_callback(mic_handler) };
    ret = unsafe { mic_start() };
    if ret < 0 {
        util::log_error_fmt(format_args!("Failed to start microphone ({ret})"));
        return ret;
    }

    if ENABLE_HAPTIC {
        unsafe { register_haptic_service() };
    }

    util::log_info("Device initialized successfully\n");

    loop {
        loop_body();
    }
}
