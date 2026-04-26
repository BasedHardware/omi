use crate::rdev::{EventType, Key, KeyboardState};
use crate::windows::common::{get_code, get_scan_code, FALSE, TRUE};
use crate::windows::keycodes::code_from_key;
use std::ptr::null_mut;
use winapi::shared::minwindef::{BYTE, HKL, LPARAM, UINT};
use winapi::um::processthreadsapi::GetCurrentThreadId;
use winapi::um::winuser;
use winapi::um::winuser::{
    GetForegroundWindow, GetKeyState, GetKeyboardLayout, GetKeyboardState,
    GetWindowThreadProcessId, ToUnicodeEx, VK_CAPITAL, VK_LSHIFT, VK_RSHIFT, VK_SHIFT,
};

const VK_SHIFT_: usize = VK_SHIFT as usize;
const VK_CAPITAL_: usize = VK_CAPITAL as usize;
const VK_LSHIFT_: usize = VK_LSHIFT as usize;
const VK_RSHIFT_: usize = VK_RSHIFT as usize;
const HIGHBIT: u8 = 0x80;

pub struct Keyboard {
    last_code: UINT,
    last_scan_code: UINT,
    last_state: [BYTE; 256],
    last_is_dead: bool,
}

impl Keyboard {
    pub fn new() -> Option<Keyboard> {
        Some(Keyboard {
            last_code: 0,
            last_scan_code: 0,
            last_state: [0; 256],
            last_is_dead: false,
        })
    }

    pub(crate) unsafe fn get_name(&mut self, lpdata: LPARAM) -> Option<String> {
        // https://gist.github.com/akimsko/2011327
        // https://www.experts-exchange.com/questions/23453780/LowLevel-Keystroke-Hook-removes-Accents-on-French-Keyboard.html
        let code = get_code(lpdata);
        let scan_code = get_scan_code(lpdata);

        self.set_global_state()?;
        self.get_code_name(code, scan_code)
    }

    pub(crate) unsafe fn set_global_state(&mut self) -> Option<()> {
        let mut state = [0_u8; 256];
        let state_ptr = state.as_mut_ptr();

        let _shift = GetKeyState(VK_SHIFT);
        let current_window_thread_id = GetWindowThreadProcessId(GetForegroundWindow(), null_mut());
        let thread_id = GetCurrentThreadId();
        // Attach to active thread so we can get that keyboard state
        let status = if winuser::AttachThreadInput(thread_id, current_window_thread_id, TRUE) == 1 {
            // Current state of the modifiers in keyboard
            let status = GetKeyboardState(state_ptr);

            // Detach
            winuser::AttachThreadInput(thread_id, current_window_thread_id, FALSE);
            status
        } else {
            // Could not attach, perhaps it is this process?
            GetKeyboardState(state_ptr)
        };

        if status != 1 {
            return None;
        }
        self.last_state = state;
        Some(())
    }

    pub(crate) unsafe fn get_code_name(&mut self, code: UINT, scan_code: UINT) -> Option<String> {
        let current_window_thread_id = GetWindowThreadProcessId(GetForegroundWindow(), null_mut());
        let state_ptr = self.last_state.as_mut_ptr();
        const BUF_LEN: i32 = 32;
        let mut buff = [0_u16; BUF_LEN as usize];
        let buff_ptr = buff.as_mut_ptr();
        let layout = GetKeyboardLayout(current_window_thread_id);
        let len = ToUnicodeEx(code, scan_code, state_ptr, buff_ptr, 8 - 1, 0, layout);

        let mut is_dead = false;
        let result = match len {
            0 => None,
            -1 => {
                is_dead = true;
                self.clear_keyboard_buffer(code, scan_code, layout);
                None
            }
            len if len > 0 => String::from_utf16(&buff[..len as usize]).ok(),
            _ => None,
        };

        if self.last_code != 0 && self.last_is_dead {
            buff = [0; 32];
            let buff_ptr = buff.as_mut_ptr();
            let last_state_ptr = self.last_state.as_mut_ptr();
            ToUnicodeEx(
                self.last_code,
                self.last_scan_code,
                last_state_ptr,
                buff_ptr,
                BUF_LEN,
                0,
                layout,
            );
            self.last_code = 0;
        } else {
            self.last_code = code;
            self.last_scan_code = scan_code;
            self.last_is_dead = is_dead;
        }
        result
    }

    unsafe fn clear_keyboard_buffer(&self, code: UINT, scan_code: UINT, layout: HKL) {
        const BUF_LEN: i32 = 32;
        let mut buff = [0_u16; BUF_LEN as usize];
        let buff_ptr = buff.as_mut_ptr();
        let mut state = [0_u8; 256];
        let state_ptr = state.as_mut_ptr();

        let mut len = -1;
        while len < 0 {
            len = ToUnicodeEx(code, scan_code, state_ptr, buff_ptr, BUF_LEN, 0, layout);
        }
    }
}

impl KeyboardState for Keyboard {
    fn add(&mut self, event_type: &EventType) -> Option<String> {
        match event_type {
            EventType::KeyPress(key) => match key {
                Key::ShiftLeft => {
                    self.last_state[VK_SHIFT_] |= HIGHBIT;
                    self.last_state[VK_LSHIFT_] |= HIGHBIT;
                    None
                }
                Key::ShiftRight => {
                    self.last_state[VK_SHIFT_] |= HIGHBIT;
                    self.last_state[VK_RSHIFT_] |= HIGHBIT;
                    None
                }
                Key::CapsLock => {
                    self.last_state[VK_CAPITAL_] ^= HIGHBIT;
                    None
                }
                key => {
                    let code = code_from_key(*key)?;
                    unsafe { self.get_code_name(code.into(), 0) }
                }
            },
            EventType::KeyRelease(key) => match key {
                Key::ShiftLeft => {
                    self.last_state[VK_SHIFT_] &= !HIGHBIT;
                    self.last_state[VK_LSHIFT_] &= !HIGHBIT;
                    None
                }
                Key::ShiftRight => {
                    self.last_state[VK_SHIFT_] &= !HIGHBIT;
                    self.last_state[VK_RSHIFT_] &= HIGHBIT;
                    None
                }
                _ => None,
            },

            _ => None,
        }
    }

    fn reset(&mut self) {
        self.last_state[16] = 0;
        self.last_state[20] = 0;
    }
}
