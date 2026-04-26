use crate::rdev::Key;
use std::os::raw::c_uint;

macro_rules! decl_keycodes {
    ($($key:ident, $code:literal),*) => {
        //TODO: make const when rust lang issue #49146 is fixed
        pub fn code_from_key(key: Key) -> Option<c_uint> {
            match key {
                $(
                    Key::$key => Some($code),
                )*
                Key::Unknown(code) => Some(code),
                _ => None,
            }
        }

        //TODO: make const when rust lang issue #49146 is fixed
        pub fn key_from_code(code: c_uint) -> Key {
            match code {
                $(
                    $code => Key::$key,
                )*
                _ => Key::Unknown(code)
            }
        }
    };
}

#[rustfmt::skip]
decl_keycodes!(
    Alt, 64,
    AltGr, 108,
    Backspace, 22,
    CapsLock, 66,
    ControlLeft, 37,
    ControlRight, 105,
    Delete, 119,
    DownArrow, 116,
    End, 115,
    Escape, 9,
    F1, 67,
    F10, 76,
    F11, 95,
    F12, 96,
    F2, 68,
    F3, 69,
    F4, 70,
    F5, 71,
    F6, 72,
    F7, 73,
    F8, 74,
    F9, 75,
    Home, 110,
    LeftArrow, 113,
    MetaLeft, 133,
    PageDown, 117,
    PageUp, 112,
    Return, 36,
    RightArrow, 114,
    ShiftLeft, 50,
    ShiftRight, 62,
    Space, 65,
    Tab, 23,
    UpArrow, 111,
    PrintScreen, 107,
    ScrollLock, 78,
    Pause, 127,
    NumLock, 77,
    BackQuote, 49,
    Num1, 10,
    Num2, 11,
    Num3, 12,
    Num4, 13,
    Num5, 14,
    Num6, 15,
    Num7, 16,
    Num8, 17,
    Num9, 18,
    Num0, 19,
    Minus, 20,
    Equal, 21,
    KeyQ, 24,
    KeyW, 25,
    KeyE, 26,
    KeyR, 27,
    KeyT, 28,
    KeyY, 29,
    KeyU, 30,
    KeyI, 31,
    KeyO, 32,
    KeyP, 33,
    LeftBracket, 34,
    RightBracket, 35,
    KeyA, 38,
    KeyS, 39,
    KeyD, 40,
    KeyF, 41,
    KeyG, 42,
    KeyH, 43,
    KeyJ, 44,
    KeyK, 45,
    KeyL, 46,
    SemiColon, 47,
    Quote, 48,
    BackSlash, 51,
    IntlBackslash, 94,
    KeyZ, 52,
    KeyX, 53,
    KeyC, 54,
    KeyV, 55,
    KeyB, 56,
    KeyN, 57,
    KeyM, 58,
    Comma, 59,
    Dot, 60,
    Slash, 61,
    Insert, 118,
    KpReturn, 104,
    KpMinus, 82,
    KpPlus, 86,
    KpMultiply, 63,
    KpDivide, 106,
    Kp0, 90,
    Kp1, 87,
    Kp2, 88,
    Kp3, 89,
    Kp4, 83,
    Kp5, 84,
    Kp6, 85,
    Kp7, 79,
    Kp8, 80,
    Kp9, 81,
    KpDelete, 91
);

#[cfg(test)]
mod test {
    use super::{code_from_key, key_from_code};
    #[test]
    fn test_reversible() {
        for code in 0..65636 {
            let key = key_from_code(code);
            match code_from_key(key) {
                Some(code2) => assert_eq!(code, code2),
                None => panic!("Could not convert back code: {:?}", code),
            }
        }
    }
}
