use rdev::display_size;
fn main() {
    let (w, h) = display_size().unwrap();

    println!("Your screen is {:?}x{:?}", w, h);
}
