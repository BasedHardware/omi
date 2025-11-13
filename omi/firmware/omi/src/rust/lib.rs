#![no_std]
#![allow(macro_expanded_macro_exports_accessed_by_absolute_paths)]

pub mod app_main;
pub mod battery;
pub mod ble;
pub mod button;
pub mod codec;
pub mod ffi;
pub mod hal;
pub mod haptic;
pub mod led;
pub mod macros;
pub mod mic;
pub mod sd_card;
pub mod settings;
pub mod spi_flash;
pub mod transport;
pub mod util;

use core::panic::PanicInfo;

#[panic_handler]
fn panic(_info: &PanicInfo) -> ! {
    loop {}
}
