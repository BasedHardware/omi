use core::ffi::c_void;
use core::ptr;
use core::sync::atomic::{AtomicBool, Ordering};

use spin::Mutex;

use crate::ble::{self, HapticCharacteristic};
use crate::hal::{self, DelayableWork, Error as HalError};
use crate::macros::omi_macro_support::{BleAccess, CodecSpec};
use crate::util;

const MAX_HAPTIC_DURATION_MS: u32 = 5_000;

static WORK_HANDLE: Mutex<Option<DelayableWork>> = Mutex::new(None);
static SERVICE_REGISTERED: AtomicBool = AtomicBool::new(false);

fn haptic_pin() -> Result<hal::GpioPin, HalError> {
    hal::motor_pin()
}

fn log_service_metadata() {
    let spec = ble::haptic_service_spec();
    util::log_info_fmt(format_args!(
        "Haptic BLE service '{}' (uuid: {}) advertise={}\n",
        spec.name, spec.uuid, spec.advertise
    ));

    for characteristic in spec.characteristics() {
        util::log_info_fmt(format_args!(
            "  characteristic '{}' uuid={} access={:?} codec={:?}\n",
            characteristic.name(),
            characteristic.uuid(),
            characteristic.access(),
            characteristic.codec()
        ));
    }
}

fn ensure_work_locked(slot: &mut Option<DelayableWork>) -> Result<(), i32> {
    if slot.is_some() {
        return Ok(());
    }

    unsafe extern "C" fn off_trampoline(_user_data: *mut c_void) {
        haptic_off();
        util::log_info("Haptic turned off by work handler\n");
    }

    let work = DelayableWork::new(Some(off_trampoline), ptr::null_mut()).map_err(|err| err.as_errno())?;
    *slot = Some(work);
    Ok(())
}

fn with_work<F>(f: F) -> Result<(), i32>
where
    F: FnOnce(&DelayableWork) -> Result<(), i32>,
{
    let mut guard = WORK_HANDLE.lock();
    ensure_work_locked(&mut *guard)?;
    let work = guard.as_ref().expect("work initialized");
    f(work)
}

#[no_mangle]
pub extern "C" fn haptic_init() -> i32 {
    let pin = match haptic_pin() {
        Ok(pin) => pin,
        Err(err) => {
            util::log_error("Haptic GPIO pin not found\n");
            return err.as_errno();
        }
    };

    if !pin.is_ready() {
        util::log_error("Haptic GPIO device not ready\n");
        return HalError::DeviceNotReady.as_errno();
    }

    if let Err(code) = with_work(|_| Ok(())) {
        return code;
    }

    util::log_info("Haptic system initialized\n");
    0
}

fn configure_output(pin: &hal::GpioPin) -> Result<(), i32> {
    pin.configure_output().map_err(|err| {
        util::log_error("Failed to configure haptic pin\n");
        err.as_errno()
    })
}

#[no_mangle]
pub extern "C" fn play_haptic_milli(duration_ms: u32) {
    let pin = match haptic_pin() {
        Ok(pin) => pin,
        Err(err) => {
            util::log_error_fmt(format_args!("Haptic GPIO pin not found ({:?})\n", err));
            return;
        }
    };

    if !pin.is_ready() {
        util::log_error("Haptic GPIO not ready\n");
        return;
    }

    if let Err(code) = with_work(|work| {
        let _ = work.cancel();

        if duration_ms == 0 {
            pin.set(false).map_err(|err| err.as_errno())?;
            util::log_info("Haptic explicitly stopped\n");
            return Ok(());
        }

        let bounded = duration_ms.min(MAX_HAPTIC_DURATION_MS);
        if bounded != duration_ms {
            util::log_error("Requested haptic duration exceeded max; capping\n");
        }

        configure_output(&pin)?;
        pin.set(true).map_err(|err| err.as_errno())?;
        work.schedule(bounded).map_err(|err| err.as_errno())?;
        util::log_info("Playing haptic\n");
        Ok(())
    }) {
        util::log_error_fmt(format_args!("Failed to control haptic ({code})\n"));
    }
}

#[no_mangle]
pub extern "C" fn haptic_off() {
    if let Ok(pin) = haptic_pin() {
        if let Err(err) = pin.set(false) {
            util::log_error_fmt(format_args!("Failed to disable haptic pin ({:?})\n", err));
        }
    }
}

unsafe extern "C" fn haptic_ble_callback(value: u8) {
    debug_assert!(matches!(ble::haptic_command_codec(), CodecSpec::Binary));
    match value {
        1 => play_haptic_milli(100),
        2 => play_haptic_milli(300),
        3 => play_haptic_milli(500),
        _ => util::log_error_fmt(format_args!(
            "Haptic write: invalid value {} on {}\n",
            value,
            HapticCharacteristic::command.uuid()
        )),
    }
}

#[no_mangle]
pub extern "C" fn register_haptic_service() {
    if SERVICE_REGISTERED.load(Ordering::Relaxed) {
        return;
    }

    debug_assert!(
        ble::haptic_command_access().contains(&BleAccess::Write),
        "Haptic command characteristic must allow writes"
    );

    log_service_metadata();

    if let Err(err) = hal::register_haptic_service(Some(haptic_ble_callback)) {
        util::log_error_fmt(format_args!("Failed to register Haptic GATT service ({:?})\n", err));
    } else {
        SERVICE_REGISTERED.store(true, Ordering::Relaxed);
        util::log_info("Haptic GATT service registered\n");
    }
}
