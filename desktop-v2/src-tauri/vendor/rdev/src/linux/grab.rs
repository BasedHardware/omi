use crate::linux::common::Display;
use crate::linux::keyboard::Keyboard;
use crate::rdev::{Button, Event, EventType, GrabError, Key, KeyboardState};
use epoll::ControlOptions::{EPOLL_CTL_ADD, EPOLL_CTL_DEL};
use evdev_rs::{
    enums::{EventCode, EV_KEY, EV_REL},
    Device, InputEvent, UInputDevice,
};
use inotify::{Inotify, WatchMask};
use std::ffi::{OsStr, OsString};
use std::fs::{read_dir, File};
use std::io;
use std::os::unix::{
    ffi::OsStrExt,
    fs::FileTypeExt,
    io::{AsRawFd, IntoRawFd, RawFd},
};
use std::path::Path;
use std::time::SystemTime;

// TODO The x, y coordinates are currently wrong !! Is there mouse acceleration
// to take into account ??

macro_rules! convert_keys {
    ($($ev_key:ident, $rdev_key:ident),*) => {
        //TODO: make const when rust lang issue #49146 is fixed
        #[allow(unreachable_patterns)]
        fn evdev_key_to_rdev_key(key: &EV_KEY) -> Option<Key> {
            match key {
                $(
                    EV_KEY::$ev_key => Some(Key::$rdev_key),
                )*
                _ => None,
            }
        }

        // //TODO: make const when rust lang issue #49146 is fixed
        // fn rdev_key_to_evdev_key(key: &Key) -> Option<EV_KEY> {
        //     match key {
        //         $(
        //             Key::$rdev_key => Some(EV_KEY::$ev_key),
        //         )*
        //         _ => None
        //     }
        // }
    };
}

macro_rules! convert_buttons {
    ($($ev_key:ident, $rdev_key:ident),*) => {
        //TODO: make const when rust lang issue #49146 is fixed
        fn evdev_key_to_rdev_button(key: &EV_KEY) -> Option<Button> {
            match key {
                $(
                    EV_KEY::$ev_key => Some(Button::$rdev_key),
                )*
                _ => None,
            }
        }

        // //TODO: make const when rust lang issue #49146 is fixed
        // fn rdev_button_to_evdev_key(event: &Button) -> Option<EV_KEY> {
        //     match event {
        //         $(
        //             Button::$rdev_key => Some(EV_KEY::$ev_key),
        //         )*
        //         _ => None
        //     }
        // }
    };
}

#[rustfmt::skip]
convert_buttons!(
    BTN_LEFT, Left,
    BTN_RIGHT, Right,
    BTN_MIDDLE, Middle
);

//TODO: IntlBackslash, kpDelete
#[rustfmt::skip]
convert_keys!(
    KEY_ESC, Escape,
    KEY_1, Num1,
    KEY_2, Num2,
    KEY_3, Num3,
    KEY_4, Num4,
    KEY_5, Num5,
    KEY_6, Num6,
    KEY_7, Num7,
    KEY_8, Num8,
    KEY_9, Num9,
    KEY_0, Num0,
    KEY_MINUS, Minus,
    KEY_EQUAL, Equal,
    KEY_BACKSPACE, Backspace,
    KEY_TAB, Tab,
    KEY_Q, KeyQ,
    KEY_W, KeyW,
    KEY_E, KeyE,
    KEY_R, KeyR,
    KEY_T, KeyT,
    KEY_Y, KeyY,
    KEY_U, KeyU,
    KEY_I, KeyI,
    KEY_O, KeyO,
    KEY_P, KeyP,
    KEY_LEFTBRACE, LeftBracket,
    KEY_RIGHTBRACE, RightBracket,
    KEY_ENTER, Return,
    KEY_LEFTCTRL, ControlLeft,
    KEY_A, KeyA,
    KEY_S, KeyS,
    KEY_D, KeyD,
    KEY_F, KeyF,
    KEY_G, KeyG,
    KEY_H, KeyH,
    KEY_J, KeyJ,
    KEY_K, KeyK,
    KEY_L, KeyL,
    KEY_SEMICOLON, SemiColon,
    KEY_APOSTROPHE, Quote,
    KEY_GRAVE, BackQuote,
    KEY_LEFTSHIFT, ShiftLeft,
    KEY_BACKSLASH, BackSlash,
    KEY_Z, KeyZ,
    KEY_X, KeyX,
    KEY_C, KeyC,
    KEY_V, KeyV,
    KEY_B, KeyB,
    KEY_N, KeyN,
    KEY_M, KeyM,
    KEY_COMMA, Comma,
    KEY_DOT, Dot,
    KEY_SLASH, Slash,
    KEY_RIGHTSHIFT, ShiftRight,
    KEY_KPASTERISK , KpMultiply,
    KEY_LEFTALT, Alt,
    KEY_SPACE, Space,
    KEY_CAPSLOCK, CapsLock,
    KEY_F1, F1,
    KEY_F2, F2,
    KEY_F3, F3,
    KEY_F4, F4,
    KEY_F5, F5,
    KEY_F6, F6,
    KEY_F7, F7,
    KEY_F8, F8,
    KEY_F9, F9,
    KEY_F10, F10,
    KEY_NUMLOCK, NumLock,
    KEY_SCROLLLOCK, ScrollLock,
    KEY_KP7, Kp7,
    KEY_KP8, Kp8,
    KEY_KP9, Kp9,
    KEY_KPMINUS, KpMinus,
    KEY_KP4, Kp4,
    KEY_KP5, Kp5,
    KEY_KP6, Kp6,
    KEY_KPPLUS, KpPlus,
    KEY_KP1, Kp1,
    KEY_KP2, Kp2,
    KEY_KP3, Kp3,
    KEY_KP0, Kp0,
    KEY_F11, F11,
    KEY_F12, F12,
    KEY_KPENTER, KpReturn,
    KEY_RIGHTCTRL, ControlRight,
    KEY_KPSLASH, KpDivide,
    KEY_RIGHTALT, AltGr,
    KEY_HOME , Home,
    KEY_UP, UpArrow,
    KEY_PAGEUP, PageUp,
    KEY_LEFT, LeftArrow,
    KEY_RIGHT, RightArrow,
    KEY_END, End,
    KEY_DOWN, DownArrow,
    KEY_PAGEDOWN, PageDown,
    KEY_INSERT, Insert,
    KEY_DELETE, Delete,
    KEY_PAUSE, Pause,
    KEY_LEFTMETA, MetaLeft,
    KEY_RIGHTMETA, MetaRight,
    KEY_PRINT, PrintScreen,
    // KpDelete behaves like normal Delete most of the time
    KEY_DELETE, KpDelete,
    // Linux doesn't have an IntlBackslash key
    KEY_BACKSLASH, IntlBackslash
);

fn evdev_event_to_rdev_event(
    event: &InputEvent,
    x: &mut f64,
    y: &mut f64,
    w: f64,
    h: f64,
) -> Option<EventType> {
    match &event.event_code {
        EventCode::EV_KEY(key) => {
            if let Some(button) = evdev_key_to_rdev_button(key) {
                // first check if pressed key is a mouse button
                match event.value {
                    0 => Some(EventType::ButtonRelease(button)),
                    _ => Some(EventType::ButtonPress(button)),
                }
            } else if let Some(key) = evdev_key_to_rdev_key(key) {
                // check if pressed key is a keyboard key
                match event.value {
                    0 => Some(EventType::KeyRelease(key)),
                    _ => Some(EventType::KeyPress(key)),
                }
            } else {
                // if neither mouse button nor keyboard key, return none
                None
            }
        }
        EventCode::EV_REL(mouse) => match mouse {
            EV_REL::REL_X => {
                let dx = event.value as f64;
                *x += dx;
                if *x < 0.0 {
                    *x = 0.0;
                }
                if *x > w {
                    *x = w;
                }
                Some(EventType::MouseMove { x: *x, y: *y })
            }
            EV_REL::REL_Y => {
                let dy = event.value as f64;
                *y += dy;
                if *y < 0.0 {
                    *y = 0.0;
                }
                if *y > h {
                    *y = h;
                }
                Some(EventType::MouseMove { x: *x, y: *y })
            }
            EV_REL::REL_HWHEEL => Some(EventType::Wheel {
                delta_x: event.value.into(),
                delta_y: 0,
            }),
            EV_REL::REL_WHEEL => Some(EventType::Wheel {
                delta_x: 0,
                delta_y: event.value.into(),
            }),
            // Other EV_REL events cannot be represented by rdev
            _ => None,
        },
        // Other event_codes cannot be represented by rdev,
        // and some never will e.g. EV_SYN
        _ => None,
    }
}

// fn rdev_event_to_evdev_event(event: &EventType, time: &TimeVal) -> Option<InputEvent> {
//     match event {
//         EventType::KeyPress(key) => {
//             let key = rdev_key_to_evdev_key(&key)?;
//             Some(InputEvent::new(&time, &EventCode::EV_KEY(key), 1))
//         }
//         EventType::KeyRelease(key) => {
//             let key = rdev_key_to_evdev_key(&key)?;
//             Some(InputEvent::new(&time, &EventCode::EV_KEY(key), 0))
//         }
//         EventType::ButtonPress(button) => {
//             let button = rdev_button_to_evdev_key(&button)?;
//             Some(InputEvent::new(&time, &EventCode::EV_KEY(button), 1))
//         }
//         EventType::ButtonRelease(button) => {
//             let button = rdev_button_to_evdev_key(&button)?;
//             Some(InputEvent::new(&time, &EventCode::EV_KEY(button), 0))
//         }
//         EventType::MouseMove { x, y } => {
//             let (x, y) = (*x as i32, *y as i32);
//             //TODO allow both x and y movements simultaneously
//             if x != 0 {
//                 Some(InputEvent::new(&time, &EventCode::EV_REL(EV_REL::REL_X), x))
//             } else {
//                 Some(InputEvent::new(&time, &EventCode::EV_REL(EV_REL::REL_Y), y))
//             }
//         }
//         EventType::Wheel { delta_x, delta_y } => {
//             let (x, y) = (*delta_x as i32, *delta_y as i32);
//             //TODO allow both x and y movements simultaneously
//             if x != 0 {
//                 Some(InputEvent::new(
//                     &time,
//                     &EventCode::EV_REL(EV_REL::REL_HWHEEL),
//                     x,
//                 ))
//             } else {
//                 Some(InputEvent::new(
//                     &time,
//                     &EventCode::EV_REL(EV_REL::REL_WHEEL),
//                     y,
//                 ))
//             }
//         }
//     }
// }

pub fn grab<T>(callback: T) -> Result<(), GrabError>
where
    T: Fn(Event) -> Option<Event> + 'static,
{
    let mut kb = Keyboard::new().ok_or(GrabError::KeyboardError)?;
    let display = Display::new().ok_or(GrabError::MissingDisplayError)?;
    let (width, height) = display.get_size().ok_or(GrabError::MissingDisplayError)?;
    let (current_x, current_y) = display
        .get_mouse_pos()
        .ok_or(GrabError::MissingDisplayError)?;
    let mut x = current_x as f64;
    let mut y = current_y as f64;
    let w = width as f64;
    let h = height as f64;
    filter_map_events(|event| {
        let event_type = match evdev_event_to_rdev_event(&event, &mut x, &mut y, w, h) {
            Some(rdev_event) => rdev_event,
            // If we can't convert event, simulate it
            None => return (Some(event), GrabStatus::Continue),
        };
        let name = kb.add(&event_type);
        let rdev_event = Event {
            time: SystemTime::now(),
            name,
            event_type,
        };
        if callback(rdev_event).is_some() {
            (Some(event), GrabStatus::Continue)
        } else {
            // callback returns None, swallow the event
            (None, GrabStatus::Continue)
        }
    })?;
    Ok(())
}

pub fn filter_map_events<F>(mut func: F) -> io::Result<()>
where
    F: FnMut(InputEvent) -> (Option<InputEvent>, GrabStatus),
{
    let (epoll_fd, mut devices, output_devices) = setup_devices()?;
    let mut inotify = setup_inotify(epoll_fd, &devices)?;

    //grab devices
    devices
        .iter_mut()
        .try_for_each(|device| device.grab(evdev_rs::GrabMode::Grab))?;

    // create buffer for epoll to fill
    let mut epoll_buffer = [epoll::Event::new(epoll::Events::empty(), 0); 4];
    let mut inotify_buffer = vec![0_u8; 4096];
    'event_loop: loop {
        let num_events = epoll::wait(epoll_fd, -1, &mut epoll_buffer)?;

        //map and simulate events, dealing with
        'events: for event in &epoll_buffer[0..num_events] {
            // new device file created
            if event.data == INOTIFY_DATA {
                for event in inotify.read_events(&mut inotify_buffer)? {
                    assert!(
                        event.mask.contains(inotify::EventMask::CREATE),
                        "inotify is listening for events other than file creation"
                    );
                    add_device_to_epoll_from_inotify_event(epoll_fd, event, &mut devices)?;
                }
            } else {
                // Input device recieved event
                let device_idx = event.data as usize;
                let device = devices.get(device_idx).unwrap();
                while device.has_event_pending() {
                    //TODO: deal with EV_SYN::SYN_DROPPED
                    let (_, event) = match device.next_event(evdev_rs::ReadFlag::NORMAL) {
                        Ok(event) => event,
                        Err(_) => {
                            let device_fd = device.fd().unwrap().into_raw_fd();
                            let empty_event = epoll::Event::new(epoll::Events::empty(), 0);
                            epoll::ctl(epoll_fd, EPOLL_CTL_DEL, device_fd, empty_event)?;
                            continue 'events;
                        }
                    };
                    let (event, grab_status) = func(event);

                    if let (Some(event), Some(out_device)) = (event, output_devices.get(device_idx))
                    {
                        out_device.write_event(&event)?;
                    }
                    if grab_status == GrabStatus::Stop {
                        break 'event_loop;
                    }
                }
            }
        }
    }

    for device in devices.iter_mut() {
        //ungrab devices, ignore errors
        device.grab(evdev_rs::GrabMode::Ungrab).ok();
    }

    epoll::close(epoll_fd)?;
    Ok(())
}

static DEV_PATH: &str = "/dev/input";
const INOTIFY_DATA: u64 = u64::max_value();
const EPOLLIN: epoll::Events = epoll::Events::EPOLLIN;

/// Whether to continue grabbing events or to stop
/// Used in `filter_map_events` (and others)
#[derive(Debug, Eq, PartialEq, Hash)]
pub enum GrabStatus {
    /// Stop grabbing
    Continue,
    /// ungrab events
    Stop,
}

fn get_device_files<T>(path: T) -> io::Result<Vec<File>>
where
    T: AsRef<Path>,
{
    let mut res = Vec::new();
    for entry in read_dir(path)? {
        let entry = entry?;
        // /dev/input files are character devices
        if !entry.file_type()?.is_char_device() {
            continue;
        }

        let path = entry.path();
        let file_name_bytes = match path.file_name() {
            Some(file_name) => file_name.as_bytes(),
            None => continue, // file_name was "..", should be impossible
        };
        // skip filenames matching "mouse.* or mice".
        // these files don't play nice with libevdev, not sure why
        // see: https://askubuntu.com/questions/1043832/difference-between-dev-input-mouse0-and-dev-input-mice
        if file_name_bytes == OsStr::new("mice").as_bytes()
            || file_name_bytes
                .get(0..=1)
                .map(|s| s == OsStr::new("js").as_bytes())
                .unwrap_or(false)
            || file_name_bytes
                .get(0..=4)
                .map(|s| s == OsStr::new("mouse").as_bytes())
                .unwrap_or(false)
        {
            continue;
        }
        res.push(File::open(path)?);
    }
    Ok(res)
}

fn epoll_watch_all<'a, T>(device_files: T) -> io::Result<RawFd>
where
    T: Iterator<Item = &'a File>,
{
    let epoll_fd = epoll::create(true)?;
    // add file descriptors to epoll
    for (file_idx, file) in device_files.enumerate() {
        let epoll_event = epoll::Event::new(EPOLLIN, file_idx as u64);
        epoll::ctl(epoll_fd, EPOLL_CTL_ADD, file.as_raw_fd(), epoll_event)?;
    }
    Ok(epoll_fd)
}

fn inotify_devices() -> io::Result<Inotify> {
    let mut inotify = Inotify::init()?;
    inotify.add_watch(DEV_PATH, WatchMask::CREATE)?;
    Ok(inotify)
}

fn add_device_to_epoll_from_inotify_event(
    epoll_fd: RawFd,
    event: inotify::Event<&OsStr>,
    devices: &mut Vec<Device>,
) -> io::Result<()> {
    let mut device_path = OsString::from(DEV_PATH);
    device_path.push(OsString::from("/"));
    device_path.push(event.name.unwrap());
    // new plug events
    let file = File::open(device_path)?;
    let fd = file.as_raw_fd();
    let device = Device::new_from_fd(file)?;
    let event = epoll::Event::new(EPOLLIN, devices.len() as u64);
    devices.push(device);
    epoll::ctl(epoll_fd, EPOLL_CTL_ADD, fd, event)?;
    Ok(())
}

/// Returns tuple of epoll_fd, all devices, and uinput devices, where
/// uinputdevices is the same length as devices, and each uinput device is
/// a libevdev copy of its corresponding device.The epoll_fd is level-triggered
/// on any available data in the original devices.
fn setup_devices() -> io::Result<(RawFd, Vec<Device>, Vec<UInputDevice>)> {
    let device_files = get_device_files(DEV_PATH)?;
    let epoll_fd = epoll_watch_all(device_files.iter())?;
    let devices = device_files
        .into_iter()
        .map(Device::new_from_fd)
        .collect::<io::Result<Vec<Device>>>()?;
    let output_devices = devices
        .iter()
        .map(UInputDevice::create_from_device)
        .collect::<io::Result<Vec<UInputDevice>>>()?;
    Ok((epoll_fd, devices, output_devices))
}

/// Creates an inotify instance looking at /dev/input and adds it to an epoll instance.
/// Ensures devices isnt too long, which would make the epoll data ambigious.
fn setup_inotify(epoll_fd: RawFd, devices: &[Device]) -> io::Result<Inotify> {
    //Ensure there is space for inotify at last epoll index.
    if devices.len() as u64 >= INOTIFY_DATA {
        eprintln!("number of devices: {}", devices.len());
        return Err(io::Error::new(
            io::ErrorKind::Other,
            "too many device files!",
        ));
    }
    // Set up inotify to listen for new devices being plugged in
    let inotify = inotify_devices()?;
    let epoll_event = epoll::Event::new(EPOLLIN, INOTIFY_DATA);
    epoll::ctl(epoll_fd, EPOLL_CTL_ADD, inotify.as_raw_fd(), epoll_event)?;
    Ok(inotify)
}
