//! Simple library to listen and send events to keyboard and mouse on MacOS, Windows and Linux
//! (x11).
//!
//! You can also check out [Enigo](https://github.com/Enigo-rs/Enigo) which is another
//! crate which helped me write this one.
//!
//! This crate is so far a pet project for me to understand the rust ecosystem.
//!
//! # Listening to global events
//!
//! ```no_run
//! use rdev::{listen, Event};
//!
//! // This will block.
//! if let Err(error) = listen(callback) {
//!     println!("Error: {:?}", error)
//! }
//!
//! fn callback(event: Event) {
//!     println!("My callback {:?}", event);
//!     match event.name {
//!         Some(string) => println!("User wrote {:?}", string),
//!         None => (),
//!     }
//! }
//! ```
//!
//! ## OS Caveats:
//! When using the `listen` function, the following caveats apply:
//!
//! ## Mac OS
//! The process running the blocking `listen` function (loop) needs to be the parent process (no fork before).
//! The process needs to be granted access to the Accessibility API (ie. if you're running your process
//! inside Terminal.app, then Terminal.app needs to be added in
//! System Preferences > Security & Privacy > Privacy > Accessibility)
//! If the process is not granted access to the Accessibility API, MacOS will silently ignore rdev's
//! `listen` calleback and will not trigger it with events. No error will be generated.
//!
//! ## Linux
//! The `listen` function uses X11 APIs, and so will not work in Wayland or in the linux kernel virtual console
//!
//! # Sending some events
//!
//! ```no_run
//! use rdev::{simulate, Button, EventType, Key, SimulateError};
//! use std::{thread, time};
//!
//! fn send(event_type: &EventType) {
//!     let delay = time::Duration::from_millis(20);
//!     match simulate(event_type) {
//!         Ok(()) => (),
//!         Err(SimulateError) => {
//!             println!("We could not send {:?}", event_type);
//!         }
//!     }
//!     // Let ths OS catchup (at least MacOS)
//!     thread::sleep(delay);
//! }
//!
//! send(&EventType::KeyPress(Key::KeyS));
//! send(&EventType::KeyRelease(Key::KeyS));
//!
//! send(&EventType::MouseMove { x: 0.0, y: 0.0 });
//! send(&EventType::MouseMove { x: 400.0, y: 400.0 });
//! send(&EventType::ButtonPress(Button::Left));
//! send(&EventType::ButtonRelease(Button::Right));
//! send(&EventType::Wheel {
//!     delta_x: 0,
//!     delta_y: 1,
//! });
//! ```
//! # Main structs
//! ## Event
//!
//! In order to detect what a user types, we need to plug to the OS level management
//! of keyboard state (modifiers like shift, ctrl, but also dead keys if they exist).
//!
//! `EventType` corresponds to a *physical* event, corresponding to QWERTY layout
//! `Event` corresponds to an actual event that was received and `Event.name` reflects
//! what key was interpreted by the OS at that time, it will respect the layout.
//!
//! ```no_run
//! # use crate::rdev::EventType;
//! # use std::time::SystemTime;
//! /// When events arrive from the system we can add some information
//! /// time is when the event was received.
//! #[derive(Debug)]
//! pub struct Event {
//!     pub time: SystemTime,
//!     pub name: Option<String>,
//!     pub event_type: EventType,
//! }
//! ```
//!
//! Be careful, Event::name, might be None, but also String::from(""), and might contain
//! not displayable unicode characters. We send exactly what the OS sends us so do some sanity checking
//! before using it.
//! Caveat: Dead keys don't function yet on Linux
//!
//! ## EventType
//!
//! In order to manage different OS, the current EventType choices is a mix&match
//! to account for all possible events.
//! There is a safe mechanism to detect events no matter what, which are the
//! Unknown() variant of the enum which will contain some OS specific value.
//! Also not that not all keys are mapped to an OS code, so simulate might fail if you
//! try to send an unmapped key. Sending Unknown() variants will always work (the OS might
//! still reject it).
//!
//! ```no_run
//! # use crate::rdev::{Key, Button};
//! /// In order to manage different OS, the current EventType choices is a mix&match
//! /// to account for all possible events.
//! #[derive(Debug)]
//! pub enum EventType {
//!     /// The keys correspond to a standard qwerty layout, they don't correspond
//!     /// To the actual letter a user would use, that requires some layout logic to be added.
//!     KeyPress(Key),
//!     KeyRelease(Key),
//!     /// Some mouse will have more than 3 buttons, these are not defined, and different OS will
//!     /// give different Unknown code.
//!     ButtonPress(Button),
//!     ButtonRelease(Button),
//!     /// Values in pixels
//!     MouseMove {
//!         x: f64,
//!         y: f64,
//!     },
//!     /// Note: On Linux, there is no actual delta the actual values are ignored for delta_x
//!     /// and we only look at the sign of delta_y to simulate wheelup or wheeldown.
//!     Wheel {
//!         delta_x: i64,
//!         delta_y: i64,
//!     },
//! }
//! ```
//!
//!
//! # Getting the main screen size
//!
//! ```no_run
//! use rdev::{display_size};
//!
//! let (w, h) = display_size().unwrap();
//! assert!(w > 0);
//! assert!(h > 0);
//! ```
//!
//! # Keyboard state
//!
//! We can define a dummy Keyboard, that we will use to detect
//! what kind of EventType trigger some String. We get the currently used
//! layout for now !
//! Caveat : This is layout dependent. If your app needs to support
//! layout switching don't use this !
//! Caveat: On Linux, the dead keys mechanism is not implemented.
//! Caveat: Only shift and dead keys are implemented, Alt+unicode code on windows
//! won't work.
//!
//! ```no_run
//! use rdev::{Keyboard, EventType, Key, KeyboardState};
//!
//! let mut keyboard = Keyboard::new().unwrap();
//! let string = keyboard.add(&EventType::KeyPress(Key::KeyS));
//! // string == Some("s")
//! ```
//!
//! # Grabbing global events. (Requires `unstable_grab` feature)
//!
//! Installing this library with the `unstable_grab` feature adds the `grab` function
//! which hooks into the global input device event stream.
//! by suppling this function with a callback, you can intercept
//! all keyboard and mouse events before they are delivered to applications / window managers.
//! In the callback, returning None ignores the event and returning the event let's it pass.
//! There is no modification of the event possible here (yet).
//!
//! Note: the use of the word `unstable` here refers specifically to the fact that the `grab` API is unstable and subject to change
//!
//! ```no_run
//! #[cfg(feature = "unstable_grab")]
//! use rdev::{grab, Event, EventType, Key};
//!
//! #[cfg(feature = "unstable_grab")]
//! let callback = |event: Event| -> Option<Event> {
//!     if let EventType::KeyPress(Key::CapsLock) = event.event_type {
//!         println!("Consuming and cancelling CapsLock");
//!         None  // CapsLock is now effectively disabled
//!     }
//!     else { Some(event) }
//! };
//! // This will block.
//! #[cfg(feature = "unstable_grab")]
//! if let Err(error) = grab(callback) {
//!     println!("Error: {:?}", error)
//! }
//! ```
//!
//! ## OS Caveats:
//! When using the `listen` and/or `grab` functions, the following caveats apply:
//!
//! ### Mac OS
//! The process running the blocking `grab` function (loop) needs to be the parent process (no fork before).
//! The process needs to be granted access to the Accessibility API (ie. if you're running your process
//! inside Terminal.app, then Terminal.app needs to be added in
//! System Preferences > Security & Privacy > Privacy > Accessibility)
//! If the process is not granted access to the Accessibility API, the `grab` call will fail with an
//! EventTapError (at least in MacOS 10.15, possibly other versions as well)
//!
//! ### Linux
//! The `grab` function use the `evdev` library to intercept events, so they will work with both X11 and Wayland
//! In order for this to work, the process runnign the `listen` or `grab` loop needs to either run as root (not recommended),
//! or run as a user who's a member of the `input` group (recommended)
//! Note: on some distros, the group name for evdev access is called `plugdev`, and on some systems, both groups can exist.
//! When in doubt, add your user to both groups if they exist.
//!
//! # Serialization
//!
//! Event data returned by the `listen` and `grab` functions can be serialized and de-serialized with
//! Serde if you install this library with the `serialize` feature.
mod rdev;
pub use crate::rdev::{
    Button, DisplayError, Event, EventType, GrabCallback, GrabError, Key, KeyboardState,
    ListenError, SimulateError,
};

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "macos")]
pub use crate::macos::Keyboard;
#[cfg(target_os = "macos")]
use crate::macos::{display_size as _display_size, listen as _listen, simulate as _simulate};

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
pub use crate::linux::Keyboard;
#[cfg(target_os = "linux")]
use crate::linux::{display_size as _display_size, listen as _listen, simulate as _simulate};

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
pub use crate::windows::Keyboard;
#[cfg(target_os = "windows")]
use crate::windows::{display_size as _display_size, listen as _listen, simulate as _simulate};

/// Listening to global events. Caveat: On MacOS, you require the listen
/// loop needs to be the primary app (no fork before) and need to have accessibility
/// settings enabled.
///
/// ```no_run
/// use rdev::{listen, Event};
///
/// fn callback(event: Event) {
///     println!("My callback {:?}", event);
///     match event.name{
///         Some(string) => println!("User wrote {:?}", string),
///         None => ()
///     }
/// }
/// fn main(){
///     // This will block.
///     if let Err(error) = listen(callback) {
///         println!("Error: {:?}", error)
///     }
/// }
/// ```
pub fn listen<T>(callback: T) -> Result<(), ListenError>
where
    T: FnMut(Event) + 'static,
{
    _listen(callback)
}

/// Sending some events
///
/// ```no_run
/// use rdev::{simulate, Button, EventType, Key, SimulateError};
/// use std::{thread, time};
///
/// fn send(event_type: &EventType) {
///     let delay = time::Duration::from_millis(20);
///     match simulate(event_type) {
///         Ok(()) => (),
///         Err(SimulateError) => {
///             println!("We could not send {:?}", event_type);
///         }
///     }
///     // Let ths OS catchup (at least MacOS)
///     thread::sleep(delay);
/// }
///
/// fn my_shortcut() {
///     send(&EventType::KeyPress(Key::KeyS));
///     send(&EventType::KeyRelease(Key::KeyS));
///
///     send(&EventType::MouseMove { x: 0.0, y: 0.0 });
///     send(&EventType::MouseMove { x: 400.0, y: 400.0 });
///     send(&EventType::ButtonPress(Button::Left));
///     send(&EventType::ButtonRelease(Button::Right));
///     send(&EventType::Wheel {
///         delta_x: 0,
///         delta_y: 1,
///     });
/// }
/// ```
pub fn simulate(event_type: &EventType) -> Result<(), SimulateError> {
    _simulate(event_type)
}

/// Returns the size in pixels of the main screen.
/// This is useful to use with x, y from MouseMove Event.
///
/// ```no_run
/// use rdev::{display_size};
///
/// let (w, h) = display_size().unwrap();
/// println!("My screen size : {:?}x{:?}", w, h);
/// ```
pub fn display_size() -> Result<(u64, u64), DisplayError> {
    _display_size()
}

#[cfg(feature = "unstable_grab")]
#[cfg(target_os = "linux")]
pub use crate::linux::grab as _grab;
#[cfg(feature = "unstable_grab")]
#[cfg(target_os = "macos")]
pub use crate::macos::grab as _grab;
#[cfg(feature = "unstable_grab")]
#[cfg(target_os = "windows")]
pub use crate::windows::grab as _grab;
#[cfg(any(feature = "unstable_grab"))]
/// Grabbing global events. In the callback, returning None ignores the event
/// and returning the event let's it pass. There is no modification of the event
/// possible here.
/// Caveat: On MacOS, you require the grab
/// loop needs to be the primary app (no fork before) and need to have accessibility
/// settings enabled.
/// On Linux, you need rw access to evdev devices in /etc/input/ (usually group membership in `input` group is enough)
///
/// ```no_run
/// use rdev::{grab, Event, EventType, Key};
///
/// fn callback(event: Event) -> Option<Event> {
///     println!("My callback {:?}", event);
///     match event.event_type{
///         EventType::KeyPress(Key::Tab) => None,
///         _ => Some(event),
///     }
/// }
/// fn main(){
///     // This will block.
///     if let Err(error) = grab(callback) {
///         println!("Error: {:?}", error)
///     }
/// }
/// ```
#[cfg(any(feature = "unstable_grab"))]
pub fn grab<T>(callback: T) -> Result<(), GrabError>
where
    T: Fn(Event) -> Option<Event> + 'static,
{
    _grab(callback)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_keyboard_state() {
        // S
        let mut keyboard = Keyboard::new().unwrap();
        let char_s = keyboard.add(&EventType::KeyPress(Key::KeyS)).unwrap();
        assert_eq!(
            char_s,
            "s".to_string(),
            "This test should pass only on Qwerty layout !"
        );
        let n = keyboard.add(&EventType::KeyRelease(Key::KeyS));
        assert_eq!(n, None);

        // Shift + S
        keyboard.add(&EventType::KeyPress(Key::ShiftLeft));
        let char_s = keyboard.add(&EventType::KeyPress(Key::KeyS)).unwrap();
        assert_eq!(char_s, "S".to_string());
        let n = keyboard.add(&EventType::KeyRelease(Key::KeyS));
        assert_eq!(n, None);
        keyboard.add(&EventType::KeyRelease(Key::ShiftLeft));

        // Reset
        keyboard.add(&EventType::KeyPress(Key::ShiftLeft));
        keyboard.reset();
        let char_s = keyboard.add(&EventType::KeyPress(Key::KeyS)).unwrap();
        assert_eq!(char_s, "s".to_string());
        let n = keyboard.add(&EventType::KeyRelease(Key::KeyS));
        assert_eq!(n, None);
        keyboard.add(&EventType::KeyRelease(Key::ShiftLeft));

        // UsIntl layout required
        // let n = keyboard.add(&EventType::KeyPress(Key::Quote));
        // assert_eq!(n, Some("".to_string()));
        // let m = keyboard.add(&EventType::KeyRelease(Key::Quote));
        // assert_eq!(m, None);
        // let e = keyboard.add(&EventType::KeyPress(Key::KeyE)).unwrap();
        // assert_eq!(e, "é".to_string());
        // keyboard.add(&EventType::KeyRelease(Key::KeyE));
    }
}
