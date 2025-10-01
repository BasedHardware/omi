use crate::util;

mod ffi {
    extern "C" {
        pub fn transport_start() -> i32;
    }
}

pub fn start() -> Result<(), i32> {
    let rc = unsafe { ffi::transport_start() };
    if rc < 0 {
        util::log_error_fmt(format_args!("Failed to start transport ({rc})"));
        Err(rc)
    } else {
        Ok(())
    }
}
