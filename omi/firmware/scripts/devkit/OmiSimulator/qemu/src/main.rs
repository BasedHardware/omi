#![no_main]
#![no_std]

use cortex_m_rt::entry;
use cortex_m_semihosting::{debug, hprintln};
use omi_firmware_core::{ButtonEvent, ButtonState};
use panic_semihosting as _;

#[entry]
fn main() -> ! {
    assert_eq!(ButtonEvent::Single.packet(), [1, 0, 0, 0, 0, 0, 0, 0]);
    assert_eq!(ButtonEvent::Double.packet(), [2, 0, 0, 0, 0, 0, 0, 0]);
    assert_eq!(ButtonEvent::Long.packet(), [3, 0, 0, 0, 0, 0, 0, 0]);
    assert_eq!(ButtonEvent::Press.packet(), [4, 0, 0, 0, 0, 0, 0, 0]);
    assert_eq!(ButtonEvent::Release.packet(), [5, 0, 0, 0, 0, 0, 0, 0]);

    let mut state = ButtonState::default();
    state.apply(ButtonEvent::Press);
    assert!(state.pressed);
    state.apply(ButtonEvent::Release);
    assert!(!state.pressed);
    state.apply(ButtonEvent::Long);
    assert!(!state.powered);

    hprintln!("Omi portable firmware checks passed");
    debug::exit(debug::EXIT_SUCCESS);
    loop {
        cortex_m::asm::bkpt();
    }
}
