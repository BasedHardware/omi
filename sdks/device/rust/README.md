# Omi device protocol helpers for Rust

This crate lives in `sdks/device/rust` and provides the shared device protocol
helpers and optional STT interface. It is separate from the Rust SDK in
`sdks/rust/omi-device`. See the shared [protocol](../PROTOCOL.md) and
[STT contract](../STT.md).

## Whisper buffering

Enable `stt-whisper` to use `omi_device::whisper::WhisperTranscriber`. Supply a
synchronous runner with the signature `Fn(&[u8]) -> Result<String, String>`;
the crate does not load a Whisper model itself.

Pass raw **PCM16 little-endian, mono, 16 kHz** bytes to `append_pcm`. The existing
batch threshold is five seconds (160,000 bytes). Once that threshold is reached,
the runner receives the entire accumulated buffer in one call. An oversized
append is not split into separate batches.

Call `flush()` when the stream ends to transcribe a shorter final batch.
Successful transcription clears the buffer and returns nonempty text as
`Ok(Some(text))`; an empty transcript returns `Ok(None)` and also clears the
buffer. Flushing an empty buffer returns `Ok(None)` without calling the runner,
so repeated successful flushes do not submit audio twice. Flushing does not close
the transcriber: subsequent `append_pcm` calls are supported.

If the runner returns an error from either method, the original audio remains
buffered. There is no automatic retry. The caller can retry explicitly with
`flush()`, including for a partial batch. Do not append the failed input again:
it is already buffered. Appending new audio after an error adds it to the
retained audio.

## Example

In a consuming project, enable the feature with a path dependency (adjust the
path to your checkout):

```toml
[dependencies]
omi-device = { path = "/path/to/omi/sdks/device/rust", features = ["stt-whisper"] }
```

This runnable `src/main.rs` example uses a demonstration runner so it needs no
model or service. Replace the closure with your Whisper inference integration.

```rust
use omi_device::whisper::WhisperTranscriber;

fn main() -> Result<(), String> {
    let mut transcriber = WhisperTranscriber::new(|pcm: &[u8]| {
        Ok(format!("Runner received {} PCM bytes", pcm.len()))
    });

    // Five seconds of PCM, followed by a shorter final chunk.
    for pcm in [vec![0_u8; 160_000], vec![0_u8; 640]] {
        if let Some(text) = transcriber.append_pcm(&pcm)? {
            println!("{text}");
        }
    }
    if let Some(text) = transcriber.flush()? {
        println!("{text}");
    }
    assert_eq!(transcriber.flush()?, None);
    Ok(())
}
```

Run the crate's hermetic protocol and Whisper buffering tests from
`sdks/device/rust`:

```sh
cargo test --features stt-whisper
```

These tests use injected runners and do not require Bluetooth hardware, a model,
or a live transcription service.
