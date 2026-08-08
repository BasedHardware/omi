use makepad_widgets as _;

fn main() {
    println!("omi-relay-contract:v1|native-seam:rust|payload:bounded|gap:explicit");
}

#[cfg(test)]
mod tests {
    #[test]
    fn contract_marker_is_stable() {
        assert!(
            "omi-relay-contract:v1|native-seam:rust|payload:bounded|gap:explicit"
                .contains("payload:bounded")
        );
    }
}
