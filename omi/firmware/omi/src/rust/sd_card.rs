use core::sync::atomic::{AtomicBool, Ordering};

use crate::hal::{self, Error as HalError};
use crate::util;

static IS_MOUNTED: AtomicBool = AtomicBool::new(false);

fn sd_card() -> Result<hal::SdCard, i32> {
    hal::SdCard::new().map_err(|err| err.as_errno())
}

fn log_stats(sd: &hal::SdCard) {
    if let Ok((count, size)) = sd.stats() {
        util::log_info_fmt(format_args!("Block count {count}"));
        util::log_info_fmt(format_args!("Sector size {size}"));
        let memory_mb = ((count as u64) * (size as u64)) >> 20;
        util::log_info_fmt(format_args!("Memory Size(MB) {memory_mb}"));
    }
}

fn mount_sd_card(sd: &hal::SdCard) -> Result<(), HalError> {
    sd.power_on()?;
    sd.disk_init()?;
    log_stats(sd);
    let _ = sd.disk_deinit();

    match sd.mount() {
        Ok(()) => {
            IS_MOUNTED.store(true, Ordering::Relaxed);
            util::log_info("Disk mounted.\n");
            Ok(())
        }
        Err(_) => {
            util::log_info("File system not found, creating file system...\n");
            sd.format_ext2()?;
            sd.mount()?;
            IS_MOUNTED.store(true, Ordering::Relaxed);
            util::log_info("Disk mounted.\n");
            Ok(())
        }
    }
}

fn unmount_sd_card(sd: &hal::SdCard) -> Result<(), HalError> {
    if IS_MOUNTED.load(Ordering::Relaxed) {
        sd.unmount()?;
        IS_MOUNTED.store(false, Ordering::Relaxed);
        util::log_info("Disk unmounted.\n");
    }
    sd.power_off()
}

#[no_mangle]
pub extern "C" fn app_sd_init() -> i32 {
    match init_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

#[no_mangle]
pub extern "C" fn app_sd_off() -> i32 {
    match power_off_impl() {
        Ok(()) => 0,
        Err(err) => err,
    }
}

fn init_impl() -> Result<(), i32> {
    match sd_card() {
        Ok(sd) => {
            if let Some(name) = sd.device_name() {
                util::log_info_fmt(format_args!("SD card module initialized (Device: {name})"));
            } else {
                util::log_info("SD card module initialized\n");
            }
            Ok(())
        }
        Err(err) => Err(err),
    }
}

fn power_off_impl() -> Result<(), i32> {
    let sd = sd_card()?;
    let _ = mount_sd_card(&sd);
    unmount_sd_card(&sd).map_err(|err| err.as_errno())
}

pub fn init() -> Result<(), i32> {
    init_impl()
}

pub fn power_off() -> Result<(), i32> {
    power_off_impl()
}
