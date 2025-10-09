use crate::util;

mod ffi {
    extern "C" {
        pub fn set_codec_callback(cb: extern "C" fn(*mut u8, usize));
        pub fn codec_start() -> i32;
        pub fn broadcast_audio_packets(data: *mut u8, len: usize) -> i32;
        pub fn codec_receive_pcm(buffer: *mut i16, samples: usize) -> i32;
    }
}

pub fn set_callback(cb: extern "C" fn(*mut u8, usize)) {
    unsafe { ffi::set_codec_callback(cb) };
}

pub fn start() -> Result<(), i32> {
    let rc = unsafe { ffi::codec_start() };
    if rc < 0 {
        util::log_error_fmt(format_args!("Failed to start codec ({rc})"));
        Err(rc)
    } else {
        Ok(())
    }
}

pub fn broadcast_packets(data: *mut u8, len: usize) -> Result<(), i32> {
    let rc = unsafe { ffi::broadcast_audio_packets(data, len) };
    if rc < 0 {
        util::log_error_fmt(format_args!("Failed to broadcast audio packets ({rc})"));
        Err(rc)
    } else {
        Ok(())
    }
}

pub fn receive_pcm(buffer: *mut i16, samples: usize) -> Result<(), i32> {
    let rc = unsafe { ffi::codec_receive_pcm(buffer, samples) };
    if rc < 0 {
        util::log_error_fmt(format_args!("Failed to process PCM data ({rc})"));
        Err(rc)
    } else {
        Ok(())
    }
}
