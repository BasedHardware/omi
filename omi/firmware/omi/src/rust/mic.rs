use core::ffi::c_void;
use core::sync::atomic::{AtomicBool, Ordering};

use spin::Mutex;

use crate::hal::{self, Dmic, MemSlab, ThreadHandle};
use crate::util;

const MAX_SAMPLE_RATE: u32 = 16_000;
const READ_TIMEOUT_MS: i32 = 1_000;
const MIC_THREAD_PRIORITY: i32 = 5;

static MIC_RUNNING: AtomicBool = AtomicBool::new(false);
static THREAD_HANDLE: Mutex<Option<ThreadHandle>> = Mutex::new(None);
static CALLBACK: Mutex<Option<unsafe extern "C" fn(*mut i16)>> = Mutex::new(None);

fn get_dmic() -> Result<Dmic, i32> {
    Dmic::new().map_err(|err| err.as_errno())
}

fn spawn_thread() -> Result<(), i32> {
    let handle = ThreadHandle::create(mic_thread, MIC_THREAD_PRIORITY).map_err(|err| err.as_errno())?;
    handle.start();
    *THREAD_HANDLE.lock() = Some(handle);
    Ok(())
}

unsafe extern "C" fn mic_thread(_p1: *mut c_void, _p2: *mut c_void, _p3: *mut c_void) {
    let dmic = match get_dmic() {
        Ok(d) => d,
        Err(err) => {
            util::log_error_fmt(format_args!("DMIC not ready ({err})\n"));
            MIC_RUNNING.store(false, Ordering::Relaxed);
            return;
        }
    };

    let slab = match MemSlab::global() {
        Ok(s) => s,
        Err(err) => {
            util::log_error_fmt(format_args!("Failed to access mem slab ({:?})\n", err));
            MIC_RUNNING.store(false, Ordering::Relaxed);
            return;
        }
    };

    while MIC_RUNNING.load(Ordering::Relaxed) {
        let mut buffer: *mut c_void = core::ptr::null_mut();
        let mut size: u32 = 0;
        if let Err(err) = dmic.read(&mut buffer, &mut size, READ_TIMEOUT_MS) {
            util::log_error_fmt(format_args!("DMIC read failed ({:?})\n", err));
            continue;
        }

        if buffer.is_null() {
            continue;
        }

        if let Some(cb) = *CALLBACK.lock() {
            cb(buffer as *mut i16);
        }

        if let Err(err) = slab.free(buffer) {
            util::log_error_fmt(format_args!("Failed to free DMIC buffer ({:?})\n", err));
        }
    }
}

#[no_mangle]
pub extern "C" fn mic_start() -> i32 {
    let dmic = match get_dmic() {
        Ok(d) => d,
        Err(err) => return err,
    };

    if let Err(err) = dmic.configure(MAX_SAMPLE_RATE, 1) {
        util::log_error_fmt(format_args!("Failed to configure DMIC ({:?})\n", err));
        return err.as_errno();
    }

    if let Err(err) = dmic.trigger(hal::DMIC_TRIGGER_START) {
        util::log_error_fmt(format_args!("START trigger failed ({:?})\n", err));
        return err.as_errno();
    }

    MIC_RUNNING.store(true, Ordering::Relaxed);
    if let Err(err) = spawn_thread() {
        MIC_RUNNING.store(false, Ordering::Relaxed);
        let _ = dmic.trigger(hal::DMIC_TRIGGER_STOP);
        return err;
    }

    util::log_info("Microphone started\n");
    0
}

#[no_mangle]
pub extern "C" fn set_mic_callback(callback: unsafe extern "C" fn(*mut i16)) {
    if (callback as usize) == 0 {
        *CALLBACK.lock() = None;
    } else {
        *CALLBACK.lock() = Some(callback);
    }
}

#[no_mangle]
pub extern "C" fn mic_off() {
    if MIC_RUNNING.swap(false, Ordering::Relaxed) {
        if let Ok(dmic) = get_dmic() {
            let _ = dmic.trigger(hal::DMIC_TRIGGER_STOP);
        }

        if let Some(handle) = THREAD_HANDLE.lock().take() {
            drop(handle);
        }

        util::log_info("Microphone stopped\n");
    }
}

#[no_mangle]
pub extern "C" fn mic_on() {
    if MIC_RUNNING.load(Ordering::Relaxed) {
        return;
    }

    let dmic = match get_dmic() {
        Ok(d) => d,
        Err(err) => {
            util::log_error_fmt(format_args!("DMIC not ready ({err})\n"));
            return;
        }
    };

    if let Err(err) = dmic.trigger(hal::DMIC_TRIGGER_START) {
        util::log_error_fmt(format_args!("START trigger failed ({:?})\n", err));
        return;
    }

    MIC_RUNNING.store(true, Ordering::Relaxed);
    if let Err(err) = spawn_thread() {
        MIC_RUNNING.store(false, Ordering::Relaxed);
        let _ = dmic.trigger(hal::DMIC_TRIGGER_STOP);
        util::log_error_fmt(format_args!("Failed to restart microphone ({err})\n"));
    } else {
        util::log_info("Microphone restarted\n");
    }
}
