#![no_std]
#![allow(macro_expanded_macro_exports_accessed_by_absolute_paths)]

pub mod ble;
pub mod ffi;
pub mod led;
pub mod settings;
pub mod spi_flash;
pub mod util;
pub mod battery;
pub mod mic;
pub mod macros;
pub mod haptic;
pub mod sd_card;
pub mod app_main;
pub mod hal;

use core::panic::PanicInfo;

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}
