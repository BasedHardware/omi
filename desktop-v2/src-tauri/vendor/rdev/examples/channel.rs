use rdev::listen;
use std::sync::mpsc::channel;
use std::thread;

fn main() {
    // spawn new thread because listen blocks
    let (schan, rchan) = channel();
    let _listener = thread::spawn(move || {
        listen(move |event| {
            schan
                .send(event)
                .unwrap_or_else(|e| println!("Could not send event {:?}", e));
        })
        .expect("Could not listen");
    });

    let mut events = Vec::new();
    for event in rchan.iter() {
        println!("Received {:?}", event);
        events.push(event);
    }
}
