use core::sync::atomic::{AtomicU32, Ordering};

use crate::battery;
use crate::button;
use crate::codec;
use crate::ffi;
use crate::hal;
use crate::haptic;
use crate::led;
use crate::mic;
use crate::sd_card;
use crate::settings;
use crate::spi_flash;
use crate::transport;
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
    led::red(true);
    hal::sleep_ms(600);
    led::red(false);
    hal::sleep_ms(200);

    led::green(true);
    hal::sleep_ms(600);
    led::green(false);
    hal::sleep_ms(200);

    led::blue(true);
    hal::sleep_ms(600);
    led::blue(false);
    hal::sleep_ms(200);

    led::red(true);
    led::green(true);
    led::blue(true);
    hal::sleep_ms(600);
    led::red(false);
    led::green(false);
    led::blue(false);
}

fn set_led_state() {
    let charging = unsafe { is_charging };
    let off = unsafe { is_off };
    let connected = unsafe { is_connected };

    led::green(charging);
    led::red(!(off || connected));
    led::blue(connected);
}

fn suspend_unused_modules() {
    if let Err(err) = spi_flash::suspend() {
        util::log_error_fmt(format_args!("Cannot suspend SPI flash: {err}"));
    }

    if let Err(err) = sd_card::power_off() {
        util::log_error_fmt(format_args!("Cannot suspend SD card: {err}"));
    }
}

extern "C" fn codec_handler(data: *mut u8, len: usize) {
    unsafe {
        broadcast_audio_count = broadcast_audio_count.wrapping_add(1);
    }

    let _ = codec::broadcast_packets(data, len);
}

unsafe extern "C" fn mic_handler(buffer: *mut i16) {
    MIC_BUFFER_TOTAL.fetch_add(1, Ordering::Relaxed);
    let _ = codec::receive_pcm(buffer, MIC_BUFFER_SAMPLES);
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
    if let Err(ret) = settings::init() {
        util::log_error_fmt(format_args!("Failed to initialize settings ({ret})"));
        let _ = settings::save_dim_ratio(5);
        led::red(true);
        hal::sleep_ms(500);
        led::red(false);
        hal::sleep_ms(200);
        let _ = settings::save_dim_ratio(100);
        led::red(true);
        hal::sleep_ms(500);
        led::red(false);
        hal::sleep_ms(200);
        let _ = settings::save_dim_ratio(30);
        led::red(true);
        hal::sleep_ms(500);
        led::red(false);
    }

    util::log_info("Initializing LEDs...\n");
    if let Err(ret) = led::init() {
        util::log_error_fmt(format_args!("Failed to initialize LEDs ({ret})"));
        return ret;
    }

    boot_led_sequence();

    if ENABLE_BATTERY {
        if let Err(err) = battery::init() {
            util::log_error_fmt(format_args!("Battery init failed ({err})"));
            return err;
        }

        if let Err(err) = battery::start_charging() {
            util::log_error_fmt(format_args!("Battery failed to start ({err})"));
            return err;
        }
        util::log_info("Battery initialized\n");
    }

    if ENABLE_BUTTON {
        if let Err(err) = button::init() {
            return err;
        }
        button::activate_work();
    }

    if ENABLE_HAPTIC {
        if let Err(err) = haptic::init() {
            util::log_error_fmt(format_args!("Failed to initialize Haptic ({err})"));
        } else {
            haptic::play_milliseconds(100);
        }
    }

    log_model_info();

    if ENABLE_OFFLINE_STORAGE {
        util::log_info("Initializing transport...\n");
    }

    if let Err(err) = transport::start() {
        return err;
    }

    util::log_info("Initializing codec...\n");
    codec::set_callback(codec_handler);
    if let Err(ret) = codec::start() {
        return ret;
    }

    util::log_info("Initializing microphone...\n");
    mic::set_callback(mic_handler);
    if let Err(ret) = mic::start() {
        return ret;
    }

    if ENABLE_HAPTIC {
        haptic::register_service();
    }

    util::log_info("Device initialized successfully\n");

    loop {
        loop_body();
    }
}
