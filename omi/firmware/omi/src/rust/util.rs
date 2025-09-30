use core::ffi::c_char;
use core::fmt::{self, Write};

use crate::ffi;

pub fn log_info(message: &str) {
    log(message, true);
}

pub fn log_error(message: &str) {
    log(message, false);
}

fn log(message: &str, info: bool) {
    let mut buffer = [0u8; 128];
    let bytes = message.as_bytes();
    let len = bytes.len().min(buffer.len() - 1);
    buffer[..len].copy_from_slice(&bytes[..len]);
    buffer[len] = 0;
    unsafe {
        let ptr = buffer.as_ptr() as *const c_char;
        if info {
            ffi::omi_log_inf(ptr);
        } else {
            ffi::omi_log_err(ptr);
        }
    }
}

struct LogBuffer {
    buf: [u8; 160],
    len: usize,
}

impl LogBuffer {
    fn new() -> Self {
        Self { buf: [0; 160], len: 0 }
    }

    fn as_c_str(&mut self) -> *const c_char {
        self.buf[self.len.min(self.buf.len() - 1)] = 0;
        self.buf.as_ptr() as *const c_char
    }
}

impl Write for LogBuffer {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        let bytes = s.as_bytes();
        let space = self.buf.len().saturating_sub(self.len + 1);
        let to_copy = bytes.len().min(space);
        self.buf[self.len..self.len + to_copy].copy_from_slice(&bytes[..to_copy]);
        self.len += to_copy;
        Ok(())
    }
}

fn log_fmt(args: fmt::Arguments, info: bool) {
    let mut buf = LogBuffer::new();
    let _ = buf.write_fmt(args);
    unsafe {
        let ptr = buf.as_c_str();
        if info {
            ffi::omi_log_inf(ptr);
        } else {
            ffi::omi_log_err(ptr);
        }
    }
}

pub fn log_info_fmt(args: fmt::Arguments) {
    log_fmt(args, true);
}

pub fn log_error_fmt(args: fmt::Arguments) {
    log_fmt(args, false);
}
