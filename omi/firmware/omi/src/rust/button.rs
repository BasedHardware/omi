use crate::util;

mod ffi {
    extern "C" {
        pub fn button_init() -> i32;
        pub fn activate_button_work();
    }
}

pub fn init() -> Result<(), i32> {
    let rc = unsafe { ffi::button_init() };
    if rc < 0 {
        util::log_error_fmt(format_args!("Failed to initialize Button ({rc})"));
        Err(rc)
    } else {
        util::log_info("Button initialized\n");
        Ok(())
    }
}

pub fn activate_work() {
    unsafe { ffi::activate_button_work() };
}
