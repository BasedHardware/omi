use rdev::{grab, Event, EventType, Key};

fn main() {
    // This will block.
    if let Err(error) = grab(callback) {
        println!("Error: {:?}", error)
    }
}

fn callback(event: Event) -> Option<Event> {
    println!("My callback {:?}", event);
    match event.event_type {
        EventType::KeyPress(Key::Tab) => {
            println!("Cancelling tab !");
            None
        }
        _ => Some(event),
    }
}
