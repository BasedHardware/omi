use crate::hal::{Error as HalError, SpiFlash};
use crate::util;

#[no_mangle]
pub extern "C" fn flash_init() -> i32 {
    match init_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

#[no_mangle]
pub extern "C" fn flash_off() -> i32 {
    match suspend_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

fn init_impl() -> Result<(), i32> {
    match SpiFlash::new() {
        Ok(flash) => {
            if !flash.is_ready() {
                util::log_error("SPI Flash device not ready\n");
                return Err(HalError::DeviceNotReady.as_errno());
            }
            util::log_info("SPI Flash control module initialized\n");
            Ok(())
        }
        Err(err) => {
            util::log_error_fmt(format_args!("SPI Flash device handle error ({:?})\n", err));
            Err(err.as_errno())
        }
    }
}

fn suspend_impl() -> Result<(), i32> {
    match SpiFlash::new() {
        Ok(flash) => match flash.suspend() {
            Ok(()) => {
                util::log_info("SPI Flash device suspended successfully\n");
                Ok(())
            }
            Err(err) => {
                if err.as_errno() == -114 {
                    util::log_info("SPI Flash device already suspended\n");
                    Ok(())
                } else {
                    util::log_error_fmt(format_args!(
                        "Failed to suspend SPI Flash device ({:?})\n",
                        err
                    ));
                    Err(err.as_errno())
                }
            }
        },
        Err(err) => {
            util::log_error_fmt(format_args!(
                "SPI Flash device handle is null ({:?})\n",
                err
            ));
            Err(err.as_errno())
        }
    }
}

pub fn init() -> Result<(), i32> {
    init_impl()
}

pub fn suspend() -> Result<(), i32> {
    suspend_impl()
}
