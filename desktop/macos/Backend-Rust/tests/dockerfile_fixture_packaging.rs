#[test]
fn dockerfile_copies_llm_stub_fixtures() {
    let dockerfile = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/Dockerfile"))
        .expect("read desktop backend Dockerfile");

    assert!(
        dockerfile.contains("COPY fixtures ./fixtures"),
        "the Docker build must include fixtures used by include_str! in the LLM stub"
    );
}
