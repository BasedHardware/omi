use rdev::listen;
use std::thread;
use tokio::sync::mpsc;

#[tokio::main]
async fn main() {
    // spawn new thread because listen blocks
    let (schan, mut rchan) = mpsc::unbounded_channel();
    let _listener = thread::spawn(move || {
        listen(move |event| {
            schan
                .send(event)
                .unwrap_or_else(|e| println!("Could not send event {:?}", e));
        })
        .expect("Could not listen");
    });

    loop {
        let event = rchan.recv().await;
        println!("Received {:?}", event);
    }
}
