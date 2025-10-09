use crate::hal::{self, LedPwm};
use crate::util;

fn dim_ratio() -> u32 {
    extern "C" {
        fn app_settings_get_dim_ratio() -> u8;
    }
    unsafe { app_settings_get_dim_ratio() as u32 }
}

fn apply_channel(channel: LedPwm, on: bool) {
    if !channel.is_ready() {
        util::log_error("LED device not ready\n");
        return;
    }

    let duty = if on { dim_ratio().min(100) } else { 0 };
    if let Err(err) = channel.set_duty(duty) {
        util::log_error_fmt(format_args!("Failed to set LED pulse ({:?})\n", err));
    }
}

fn init_impl() -> Result<(), i32> {
    match hal::led_start() {
        Ok(()) => Ok(()),
        Err(err) => {
            util::log_error_fmt(format_args!("LED PWM device not ready ({:?})\n", err));
            Err(err.as_errno())
        }
    }
}

pub fn init() -> Result<(), i32> {
    init_impl()
}

pub fn red(on: bool) {
    apply_channel(LedPwm::red(), on);
}

pub fn green(on: bool) {
    apply_channel(LedPwm::green(), on);
}

pub fn blue(on: bool) {
    apply_channel(LedPwm::blue(), on);
}

#[no_mangle]
pub extern "C" fn led_start() -> i32 {
    match init_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

#[no_mangle]
pub extern "C" fn set_led_red(on: bool) {
    red(on);
}

#[no_mangle]
pub extern "C" fn set_led_green(on: bool) {
    green(on);
}

#[no_mangle]
pub extern "C" fn set_led_blue(on: bool) {
    blue(on);
}
