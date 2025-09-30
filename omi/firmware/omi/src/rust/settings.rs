use core::ffi::{c_char, c_int, c_void, CStr};
use core::ptr;
use core::sync::atomic::{AtomicBool, AtomicU8, Ordering};

use crate::ffi;
use crate::hal::Settings;
use crate::util;

const DEFAULT_DIM_RATIO: u8 = 50;
const EINVAL: i32 = -22;
const ENOENT: i32 = -2;

static DIM_RATIO: AtomicU8 = AtomicU8::new(DEFAULT_DIM_RATIO);
static HANDLER_REGISTERED: AtomicBool = AtomicBool::new(false);

const SUBTREE_BYTES: &[u8] = b"omi\0";
const DIM_KEY_BYTES: &[u8] = b"dim_ratio\0";
const DIM_PATH_BYTES: &[u8] = b"omi/dim_ratio\0";

fn subtree() -> &'static CStr {
    unsafe { CStr::from_bytes_with_nul_unchecked(SUBTREE_BYTES) }
}

fn dim_key() -> &'static CStr {
    unsafe { CStr::from_bytes_with_nul_unchecked(DIM_KEY_BYTES) }
}

fn dim_path() -> &'static CStr {
    unsafe { CStr::from_bytes_with_nul_unchecked(DIM_PATH_BYTES) }
}

fn settings() -> Settings {
    Settings::new()
}

fn ensure_handler_registered() -> i32 {
    if HANDLER_REGISTERED.load(Ordering::Relaxed) {
        return 0;
    }

    let err = settings()
        .register_handler(subtree(), settings_set_cb, ptr::null_mut())
        .map_err(|err| err.as_errno());

    match err {
        Ok(()) => {
            HANDLER_REGISTERED.store(true, Ordering::Relaxed);
            0
        }
        Err(code) => {
            util::log_error_fmt(format_args!("Failed to register settings handler ({code})\n"));
            code
        }
    }
}

unsafe extern "C" fn settings_set_cb(
    name: *const c_char,
    len: usize,
    read_cb: ffi::settings_read_cb,
    cb_arg: *mut c_void,
    _user_data: *mut c_void,
) -> c_int {
    if name.is_null() {
        return EINVAL;
    }

    let mut next: *const c_char = ptr::null();
    let matches = Settings::name_steq(name, dim_key(), &mut next);

    if matches && next.is_null() {
        if len != core::mem::size_of::<u8>() {
            return EINVAL;
        }

        let mut value: u8 = DIM_RATIO.load(Ordering::Relaxed);
        let rc = read_cb(cb_arg, &mut value as *mut _ as *mut c_void, len);
        if rc >= 0 {
            DIM_RATIO.store(value, Ordering::Relaxed);
            util::log_info("Loaded dim_ratio\n");
            return 0;
        }
        return rc;
    }

    ENOENT
}

#[no_mangle]
pub extern "C" fn app_settings_init() -> i32 {
    if let Err(err) = settings().init() {
        util::log_error_fmt(format_args!("Failed to initialize settings subsystem ({:?})\n", err));
        return err.as_errno();
    }

    let err = ensure_handler_registered();
    if err != 0 {
        return err;
    }

    match settings().load() {
        Ok(()) => {
            util::log_info("Settings initialized\n");
            0
        }
        Err(err) => {
            util::log_error_fmt(format_args!("Failed to load settings ({:?})\n", err));
            err.as_errno()
        }
    }
}

#[no_mangle]
pub extern "C" fn app_settings_save_dim_ratio(new_ratio: u8) -> i32 {
    DIM_RATIO.store(new_ratio, Ordering::Relaxed);
    let bytes = [new_ratio];
    match settings().save_one(dim_path(), &bytes) {
        Ok(()) => {
            util::log_info("Saved dim_ratio\n");
            0
        }
        Err(err) => {
            util::log_error_fmt(format_args!("Failed to save dim_ratio ({:?})\n", err));
            err.as_errno()
        }
    }
}

#[no_mangle]
pub extern "C" fn app_settings_get_dim_ratio() -> u8 {
    DIM_RATIO.load(Ordering::Relaxed)
}
