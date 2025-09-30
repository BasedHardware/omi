use crate::hal::{Error as HalError, SpiFlash};
use crate::util;

#[no_mangle]
pub extern "C" fn flash_init() -> i32 {
    match SpiFlash::new() {
        Ok(flash) => {
            if !flash.is_ready() {
                util::log_error("SPI Flash device not ready\n");
                return HalError::DeviceNotReady.as_errno();
            }
            util::log_info("SPI Flash control module initialized\n");
            0
        }
        Err(err) => {
            util::log_error_fmt(format_args!("SPI Flash device handle error ({:?})\n", err));
            err.as_errno()
        }
    }
}

#[no_mangle]
pub extern "C" fn flash_off() -> i32 {
    match SpiFlash::new() {
        Ok(flash) => match flash.suspend() {
            Ok(()) => {
                util::log_info("SPI Flash device suspended successfully\n");
                0
            }
            Err(err) => {
                if err.as_errno() == -114 {
                    util::log_info("SPI Flash device already suspended\n");
                    0
                } else {
                    util::log_error_fmt(format_args!(
                        "Failed to suspend SPI Flash device ({:?})\n",
                        err
                    ));
                    err.as_errno()
                }
            }
        },
        Err(err) => {
            util::log_error_fmt(format_args!(
                "SPI Flash device handle is null ({:?})\n",
                err
            ));
            err.as_errno()
        }
    }
}
