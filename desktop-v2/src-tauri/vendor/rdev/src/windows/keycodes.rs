use crate::rdev::Key;
use std::convert::TryInto;
use winapi::shared::minwindef::WORD;

macro_rules! decl_keycodes {
    ($($key:ident, $code:literal),*) => {
        //TODO: make const when rust lang issue #49146 is fixed
        pub fn code_from_key(key: Key) -> Option<WORD> {
            match key {
                $(
                    Key::$key => Some($code),
                )*
                Key::Unknown(code) => Some(code.try_into().ok()?),
                _ => None,
            }
        }

        //TODO: make const when rust lang issue #49146 is fixed
        pub fn key_from_code(code: WORD) -> Key {
            match code {
                $(
                    $code => Key::$key,
                )*
                _ => Key::Unknown(code.into())
            }
        }
    };
}

// https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes
// We redefined here for Letter and number keys which are not in winapi crate (and don't have a name either in win32)
decl_keycodes! {
    Alt, 164,
    AltGr, 165,
    Backspace, 0x08,
    CapsLock, 20,
    ControlLeft, 162,
    ControlRight, 163,
    Delete, 46,
    DownArrow, 40,
    End, 35,
    Escape, 27,
    F1, 112,
    F10, 121,
    F11, 122,
    F12, 123,
    F2, 113,
    F3, 114,
    F4, 115,
    F5, 116,
    F6, 117,
    F7, 118,
    F8, 119,
    F9, 120,
    Home, 36,
    LeftArrow, 37,
    MetaLeft, 91,
    PageDown, 34,
    PageUp, 33,
    Return, 0x0D,
    RightArrow, 39,
    ShiftLeft, 160,
    ShiftRight, 161,
    Space, 32,
    Tab, 0x09,
    UpArrow, 38,
    PrintScreen, 44,
    ScrollLock, 145,
    Pause, 19,
    NumLock, 144,
    BackQuote, 192,
    Num1, 49,
    Num2, 50,
    Num3, 51,
    Num4, 52,
    Num5, 53,
    Num6, 54,
    Num7, 55,
    Num8, 56,
    Num9, 57,
    Num0, 48,
    Minus, 189,
    Equal, 187,
    KeyQ, 81,
    KeyW, 87,
    KeyE, 69,
    KeyR, 82,
    KeyT, 84,
    KeyY, 89,
    KeyU, 85,
    KeyI, 73,
    KeyO, 79,
    KeyP, 80,
    LeftBracket, 219,
    RightBracket, 221,
    KeyA, 65,
    KeyS, 83,
    KeyD, 68,
    KeyF, 70,
    KeyG, 71,
    KeyH, 72,
    KeyJ, 74,
    KeyK, 75,
    KeyL, 76,
    SemiColon, 186,
    Quote, 222,
    BackSlash, 220,
    IntlBackslash, 226,
    KeyZ, 90,
    KeyX, 88,
    KeyC, 67,
    KeyV, 86,
    KeyB, 66,
    KeyN, 78,
    KeyM, 77,
    Comma, 188,
    Dot, 190,
    Slash, 191,
    Insert, 45,
    //KP_RETURN, 13,
    KpMinus, 109,
    KpPlus, 107,
    KpMultiply, 106,
    KpDivide, 111,
    Kp0, 96,
    Kp1, 97,
    Kp2, 98,
    Kp3, 99,
    Kp4, 100,
    Kp5, 101,
    Kp6, 102,
    Kp7, 103,
    Kp8, 104,
    Kp9, 105,
    KpDelete, 110
}

#[cfg(test)]
mod test {
    use super::{code_from_key, key_from_code};
    #[test]
    fn test_reversible() {
        for code in 0..65535 {
            let key = key_from_code(code);
            if let Some(code2) = code_from_key(key) {
                assert_eq!(code, code2)
            } else {
                assert!(false, "We could not convert back code: {:?}", code);
            }
        }
    }
}
