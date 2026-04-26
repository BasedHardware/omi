extern crate x11;
use crate::linux::keycodes::code_from_key;
use crate::rdev::{EventType, Key, KeyboardState};
use std::ffi::CString;
use std::os::raw::{c_char, c_int, c_uint, c_ulong, c_void};
use std::ptr::{null, null_mut, NonNull};
use x11::xlib;

#[derive(Debug)]
struct State {
    alt: bool,
    ctrl: bool,
    caps_lock: bool,
    shift: bool,
    meta: bool,
}

// Inspired from https://github.com/wavexx/screenkey
// But without remitting events to custom windows, instead we recreate  XKeyEvent
// from xEvent data received via xrecord.
// Other source of inspiration https://gist.github.com/baines/5a49f1334281b2685af5dcae81a6fa8a
// Needed xproto crate as x11 does not implement _xevent.
impl State {
    fn new() -> State {
        State {
            alt: false,
            ctrl: false,
            caps_lock: false,
            meta: false,
            shift: false,
        }
    }

    fn value(&self) -> c_uint {
        let mut res: c_uint = 0;
        if self.alt {
            res += xlib::Mod1Mask;
        }
        if self.ctrl {
            res += xlib::ControlMask;
        }
        if self.caps_lock {
            res += xlib::LockMask;
        }
        if self.meta {
            res += xlib::Mod4Mask;
        }
        if self.shift {
            res += xlib::ShiftMask;
        }
        res
    }
}

#[derive(Debug)]
pub struct Keyboard {
    pub xim: Box<xlib::XIM>,
    pub xic: Box<xlib::XIC>,
    pub display: Box<*mut xlib::Display>,
    window: Box<xlib::Window>,
    keysym: Box<c_ulong>,
    status: Box<i32>,
    state: State,
    serial: c_ulong,
}
impl Drop for Keyboard {
    fn drop(&mut self) {
        unsafe {
            xlib::XCloseDisplay(*self.display);
        }
    }
}

impl Keyboard {
    pub fn new() -> Option<Keyboard> {
        unsafe {
            // https://stackoverflow.com/questions/18246848/get-utf-8-input-with-x11-display#
            let string = CString::new("@im=none").expect("Can't creat CString");
            let ret = xlib::XSetLocaleModifiers(string.as_ptr());
            NonNull::new(ret)?;

            let dpy = xlib::XOpenDisplay(null());
            if dpy.is_null() {
                return None;
            }
            let xim = xlib::XOpenIM(dpy, null_mut(), null_mut(), null_mut());
            NonNull::new(xim)?;

            let mut win_attr = xlib::XSetWindowAttributes {
                background_pixel: 0,
                background_pixmap: 0,
                border_pixel: 0,
                border_pixmap: 0,
                bit_gravity: 0,
                win_gravity: 0,
                backing_store: 0,
                backing_planes: 0,
                backing_pixel: 0,
                event_mask: 0,
                save_under: 0,
                do_not_propagate_mask: 0,
                override_redirect: 0,
                colormap: 0,
                cursor: 0,
            };

            let window = xlib::XCreateWindow(
                dpy,
                xlib::XDefaultRootWindow(dpy),
                0,
                0,
                1,
                1,
                0,
                xlib::CopyFromParent,
                xlib::InputOnly as c_uint,
                null_mut(),
                xlib::CWOverrideRedirect,
                &mut win_attr,
            );

            let input_style = CString::new(xlib::XNInputStyle).expect("CString::new failed");
            let window_client = CString::new(xlib::XNClientWindow).expect("CString::new failed");
            let style = xlib::XIMPreeditNothing | xlib::XIMStatusNothing;

            let xic = xlib::XCreateIC(
                xim,
                window_client.as_ptr(),
                window,
                input_style.as_ptr(),
                style,
                null::<c_void>(),
            );
            NonNull::new(xic)?;
            xlib::XSetICFocus(xic);
            Some(Keyboard {
                xim: Box::new(xim),
                xic: Box::new(xic),
                display: Box::new(dpy),
                window: Box::new(window),
                keysym: Box::new(0),
                status: Box::new(0),
                state: State::new(),
                serial: 0,
            })
        }
    }

    pub(crate) unsafe fn name_from_code(
        &mut self,
        keycode: c_uint,
        state: c_uint,
    ) -> Option<String> {
        if self.display.is_null() || self.xic.is_null() {
            println!("We don't seem to have a display or a xic");
            return None;
        }
        const BUF_LEN: usize = 4;
        let mut buf = [0_u8; BUF_LEN];
        let key = xlib::XKeyEvent {
            display: *self.display,
            root: 0,
            window: *self.window,
            subwindow: 0,
            x: 0,
            y: 0,
            x_root: 0,
            y_root: 0,
            state,
            keycode,
            same_screen: 0,
            send_event: 0,
            serial: self.serial,
            type_: xlib::KeyPress,
            time: xlib::CurrentTime,
        };
        self.serial += 1;

        let mut event = xlib::XEvent { key };

        // -----------------------------------------------------------------
        // XXX: This is **OMEGA IMPORTANT** This is what enables us to receive
        // the correct keyvalue from the utf8LookupString !!
        // https://stackoverflow.com/questions/18246848/get-utf-8-input-with-x11-display#
        // -----------------------------------------------------------------
        xlib::XFilterEvent(&mut event, 0);

        let ret = xlib::Xutf8LookupString(
            *self.xic,
            &mut event.key,
            buf.as_mut_ptr() as *mut c_char,
            BUF_LEN as c_int,
            &mut *self.keysym,
            &mut *self.status,
        );
        if ret == xlib::NoSymbol {
            return None;
        }

        let len = buf.iter().position(|ch| ch == &0).unwrap_or(BUF_LEN);
        String::from_utf8(buf[..len].to_vec()).ok()
    }
}

impl KeyboardState for Keyboard {
    fn add(&mut self, event_type: &EventType) -> Option<String> {
        match event_type {
            EventType::KeyPress(key) => match key {
                Key::ShiftLeft | Key::ShiftRight => {
                    self.state.shift = true;
                    None
                }
                Key::CapsLock => {
                    self.state.caps_lock = !self.state.caps_lock;
                    None
                }
                key => {
                    let keycode = code_from_key(*key)?;
                    let state = self.state.value();
                    unsafe { self.name_from_code(keycode, state) }
                }
            },
            EventType::KeyRelease(key) => match key {
                Key::ShiftLeft | Key::ShiftRight => {
                    self.state.shift = false;
                    None
                }
                _ => None,
            },
            _ => None,
        }
    }
    fn reset(&mut self) {
        self.state = State::new();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore]
    /// If the following tests run, they *will* cause a crash because xlib
    /// is *not* thread safe. Ignoring the tests for now.
    /// XCB *could* be an option but not even sure we can get dead keys again.
    /// XCB doc is sparse on the web let's say.
    fn test_thread_safety() {
        let mut keyboard = Keyboard::new().unwrap();
        let char_s = keyboard.add(&EventType::KeyPress(Key::KeyS)).unwrap();
        assert_eq!(
            char_s,
            "s".to_string(),
            "This test should pass only on Qwerty layout !"
        );
    }

    #[test]
    #[ignore]
    fn test_thread_safety_2() {
        let mut keyboard = Keyboard::new().unwrap();
        let char_s = keyboard.add(&EventType::KeyPress(Key::KeyS)).unwrap();
        assert_eq!(
            char_s,
            "s".to_string(),
            "This test should pass only on Qwerty layout !"
        );
    }
}
