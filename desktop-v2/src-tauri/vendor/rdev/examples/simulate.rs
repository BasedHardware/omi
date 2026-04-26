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

fn main() {
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
}
