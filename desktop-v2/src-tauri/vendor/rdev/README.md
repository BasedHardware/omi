![](https://github.com/Narsil/rdev/workflows/build/badge.svg)
[![Crate](https://img.shields.io/crates/v/rdev.svg)](https://crates.io/crates/rdev)
[![API](https://docs.rs/rdev/badge.svg)](https://docs.rs/rdev)

# rdev

Simple library to listen and send events **globally** to keyboard and mouse on macOS, Windows and Linux
(x11).

You can also check out [Enigo](https://github.com/Enigo-rs/Enigo) which is another
crate which helped me write this one.

This crate is so far a pet project for me to understand the Rust ecosystem.

## Listening to global events

```rust
use rdev::{listen, Event};

// This will block.
if let Err(error) = listen(callback) {
    println!("Error: {:?}", error)
}

fn callback(event: Event) {
    println!("My callback {:?}", event);
    match event.name {
        Some(string) => println!("User wrote {:?}", string),
        None => (),
    }
}
```

### OS Caveats:
When using the `listen` function, the following caveats apply:

### macOS
The process running the blocking `listen` function (loop) needs to be the parent process (no fork before).
The process needs to be granted access to the Accessibility API (i.e. if you're running your process
inside Terminal.app, then Terminal.app needs to be added in
System Preferences > Security & Privacy > Privacy > Accessibility)
If the process is not granted access to the Accessibility API, macOS will silently ignore rdev's
`listen` callback and will not trigger it with events. No error will be generated.

### Linux
The `listen` function uses X11 APIs, and so will not work in Wayland or in the Linux kernel virtual console

## Sending some events

```rust
use rdev::{simulate, Button, EventType, Key, SimulateError};
use std::{thread, time};

fn send(event_type: &EventType) {
    let delay = time::Duration::from_millis(20);
    match simulate(event_type) {
        Ok(()) => (),
        Err(SimulateError) => {
            println!("We could not send {:?}", event_type);
        }
    }
    // Let ths OS catchup (at least MacOS)
    thread::sleep(delay);
}

send(&EventType::KeyPress(Key::KeyS));
send(&EventType::KeyRelease(Key::KeyS));

send(&EventType::MouseMove { x: 0.0, y: 0.0 });
send(&EventType::MouseMove { x: 400.0, y: 400.0 });
send(&EventType::ButtonPress(Button::Left));
send(&EventType::ButtonRelease(Button::Right));
send(&EventType::Wheel {
    delta_x: 0,
    delta_y: 1,
});
```
## Main structs
### Event

In order to detect what a user types, we need to plug to the OS level management
of keyboard state (modifiers like shift, CTRL, but also dead keys if they exist).

`EventType` corresponds to a *physical* event, corresponding to QWERTY layout
`Event` corresponds to an actual event that was received and `Event.name` reflects
what key was interpreted by the OS at that time, it will respect the layout.

```rust
/// When events arrive from the system we can add some information
/// time is when the event was received.
#[derive(Debug)]
pub struct Event {
    pub time: SystemTime,
    pub name: Option<String>,
    pub event_type: EventType,
}
```

Be careful, Event::name, might be None, but also String::from(""), and might contain
not displayable Unicode characters. We send exactly what the OS sends us, so do some sanity checking
before using it.
Caveat: Dead keys don't function yet on Linux

### EventType

In order to manage different OS, the current EventType choices is a mix and match to account for all possible events.
There is a safe mechanism to detect events no matter what, which are the
Unknown() variant of the enum which will contain some OS specific value.
Also, not that not all keys are mapped to an OS code, so simulate might fail if you
try to send an unmapped key. Sending Unknown() variants will always work (the OS might
still reject it).

```rust
/// In order to manage different OS, the current EventType choices is a mix&match
/// to account for all possible events.
#[derive(Debug)]
pub enum EventType {
    /// The keys correspond to a standard qwerty layout, they don't correspond
    /// To the actual letter a user would use, that requires some layout logic to be added.
    KeyPress(Key),
    KeyRelease(Key),
    /// Some mouse will have more than 3 buttons, these are not defined, and different OS will
    /// give different Unknown code.
    ButtonPress(Button),
    ButtonRelease(Button),
    /// Values in pixels
    MouseMove {
        x: f64,
        y: f64,
    },
    /// Note: On Linux, there is no actual delta the actual values are ignored for delta_x
    /// and we only look at the sign of delta_y to simulate wheelup or wheeldown.
    Wheel {
        delta_x: i64,
        delta_y: i64,
    },
}
```


## Getting the main screen size

```rust
use rdev::{display_size};

let (w, h) = display_size().unwrap();
assert!(w > 0);
assert!(h > 0);
```

## Keyboard state

We can define a dummy Keyboard, that we will use to detect
what kind of EventType trigger some String. We get the currently used
layout for now !
Caveat : This is layout dependent. If your app needs to support
layout switching, don't use this!
Caveat: On Linux, the dead keys mechanism is not implemented.
Caveat: Only shift and dead keys are implemented, Alt+Unicode code on Windows won't work.

```rust
use rdev::{Keyboard, EventType, Key, KeyboardState};

let mut keyboard = Keyboard::new().unwrap();
let string = keyboard.add(&EventType::KeyPress(Key::KeyS));
// string == Some("s")
```

## Grabbing global events. (Requires `unstable_grab` feature)

Installing this library with the `unstable_grab` feature adds the `grab` function
which hooks into the global input device event stream.
By supplying this function with a callback, you can intercept
all keyboard and mouse events before they are delivered to applications / window managers.
In the callback, returning None ignores the event and returning the event lets it pass.
There is no modification of the event possible here (yet).

Note: the use of the word `unstable` here refers specifically to the fact that the `grab` API is unstable and subject to change

```rust
#[cfg(feature = "unstable_grab")]
use rdev::{grab, Event, EventType, Key};

#[cfg(feature = "unstable_grab")]
let callback = |event: Event| -> Option<Event> {
    if let EventType::KeyPress(Key::CapsLock) = event.event_type {
        println!("Consuming and cancelling CapsLock");
        None  // CapsLock is now effectively disabled
    }
    else { Some(event) }
};
// This will block.
#[cfg(feature = "unstable_grab")]
if let Err(error) = grab(callback) {
    println!("Error: {:?}", error)
}
```

### OS Caveats:
When using the `listen` and/or `grab` functions, the following caveats apply:

#### macOS
The process running the blocking `grab` function (loop) needs to be the parent process (no fork before).
The process needs to be granted access to the Accessibility API (i.e. if you're running your process
inside Terminal.app, then Terminal.app needs to be added in
System Preferences > Security & Privacy > Privacy > Accessibility)
If the process is not granted access to the Accessibility API, the `grab` call will fail with an
EventTapError (at least in macOS 10.15, possibly other versions as well)

#### Linux
The `grab` function use the `evdev` library to intercept events, so they will work with both X11 and Wayland
In order for this to work, the process running the `listen` or `grab` loop needs to either run as root (not recommended),
or run as a user who's a member of the `input` group (recommended)
Note: on some distros, the group name for evdev access is called `plugdev`, and on some systems, both groups can exist.
When in doubt, add your user to both groups if they exist.

## Serialization

Event data returned by the `listen` and `grab` functions can be serialized and deserialized with
Serde if you install this library with the `serialize` feature.
