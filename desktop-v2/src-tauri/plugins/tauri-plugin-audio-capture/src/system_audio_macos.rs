//! macOS system audio capture — delegates to a Swift helper subprocess.
//!
//! Every attempt to call Core Audio Process Taps from Rust (via `objc2` +
//! `coreaudio-sys`) on macOS 14.4+/26 resulted in zero-filled buffers
//! despite identical setup to the Swift reference implementation. Rather
//! than keep chasing the Rust/ObjC ABI mismatch, we shell out to a tiny
//! Swift helper (`swift-helpers/sys-audio-capture/main.swift`) that
//! wraps the exact code known to work in the Swift desktop app. The
//! helper writes 16 kHz mono i16 PCM frames to stdout; we read them into
//! an mpsc channel that feeds the existing mixer / VAD / Deepgram pipeline.

#![cfg(target_os = "macos")]

use std::io::Read;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use tokio::sync::mpsc;

/// Cached source-format string the helper reported on stderr — surfaced
/// by the probe UI. Unlike the Rust version we don't have direct access
/// to the tap's ASBD, so the helper logs it and we grep it out.
static LAST_TAP_FORMAT: std::sync::Mutex<Option<(f64, u32, u32)>> =
    std::sync::Mutex::new(None);

pub fn last_tap_format() -> Option<(f64, u32, u32)> {
    LAST_TAP_FORMAT.lock().ok().and_then(|g| g.as_ref().copied())
}

pub struct SystemAudioCapture {
    child: Option<Child>,
    is_running: Arc<AtomicBool>,
    raw_peak_bits: Arc<std::sync::atomic::AtomicU32>,
}

// SAFETY: The child process handle is !Send on some std versions due to
// its internals, but since macOS 10.10+ it's safe to move across threads;
// we never access it concurrently.
unsafe impl Send for SystemAudioCapture {}

impl SystemAudioCapture {
    pub fn raw_peak(&self) -> f32 {
        f32::from_bits(self.raw_peak_bits.load(Ordering::Relaxed))
    }

    pub fn start(tx: mpsc::Sender<Vec<i16>>) -> Result<Self, String> {
        let helper_path = resolve_helper_path()?;
        tracing::info!(
            "[sys-audio] spawning Swift helper: {}",
            helper_path.display()
        );

        let mut child = Command::new(&helper_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("failed to spawn sys-audio-capture helper: {}", e))?;

        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "helper produced no stdout pipe".to_string())?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| "helper produced no stderr pipe".to_string())?;

        let is_running = Arc::new(AtomicBool::new(true));
        let raw_peak_bits = Arc::new(std::sync::atomic::AtomicU32::new(0));

        // Stdout reader thread: parse raw little-endian i16 PCM into Vec<i16>
        // and push into the tx channel. Blocks on full (back-pressures the
        // helper process via pipe buffer).
        {
            let is_running = is_running.clone();
            let raw_peak_bits = raw_peak_bits.clone();
            std::thread::Builder::new()
                .name("sys-audio-reader".into())
                .spawn(move || {
                    let mut reader = std::io::BufReader::with_capacity(8192, stdout);
                    let mut buf = [0u8; 2048]; // 1024 i16 samples per read
                    loop {
                        if !is_running.load(Ordering::Acquire) {
                            break;
                        }
                        let n = match reader.read(&mut buf) {
                            Ok(0) => break, // EOF — helper exited
                            Ok(n) => n,
                            Err(e) => {
                                tracing::warn!("[sys-audio] reader error: {}", e);
                                break;
                            }
                        };
                        // Align to sample boundary.
                        let n = n & !1;
                        if n == 0 {
                            continue;
                        }
                        let mut samples = Vec::with_capacity(n / 2);
                        let mut local_peak: i32 = 0;
                        for chunk in buf[..n].chunks_exact(2) {
                            let s = i16::from_le_bytes([chunk[0], chunk[1]]);
                            let abs = (s as i32).abs();
                            if abs > local_peak {
                                local_peak = abs;
                            }
                            samples.push(s);
                        }
                        if local_peak > 0 {
                            let normalized = local_peak as f32 / 32768.0;
                            let current =
                                f32::from_bits(raw_peak_bits.load(Ordering::Relaxed));
                            if normalized > current {
                                raw_peak_bits
                                    .store(normalized.to_bits(), Ordering::Relaxed);
                            }
                        }
                        if tx.blocking_send(samples).is_err() {
                            break; // consumer dropped
                        }
                    }
                    tracing::info!("[sys-audio] reader thread exiting");
                })
                .map_err(|e| format!("failed to spawn reader thread: {}", e))?;
        }

        // Stderr reader thread: log + parse the "source format" line so
        // the probe can surface rate/channels/bits.
        std::thread::Builder::new()
            .name("sys-audio-stderr".into())
            .spawn(move || {
                use std::io::BufRead;
                let reader = std::io::BufReader::new(stderr);
                for line in reader.lines().flatten() {
                    tracing::info!("[sys-audio/helper] {}", line);
                    if let Some(fmt) = parse_source_format(&line) {
                        if let Ok(mut slot) = LAST_TAP_FORMAT.lock() {
                            *slot = Some(fmt);
                        }
                    }
                }
            })
            .map_err(|e| format!("failed to spawn stderr thread: {}", e))?;

        Ok(Self {
            child: Some(child),
            is_running,
            raw_peak_bits,
        })
    }
}

impl Drop for SystemAudioCapture {
    fn drop(&mut self) {
        self.is_running.store(false, Ordering::Release);
        if let Some(mut child) = self.child.take() {
            // Closing stdin signals the helper to exit cleanly.
            drop(child.stdin.take());
            // Also send SIGTERM in case stdin close is ignored.
            let _ = child.kill();
            // Reap in a detached thread so Drop returns fast.
            std::thread::spawn(move || {
                let _ = child.wait();
                tracing::info!("[sys-audio] helper reaped");
            });
        }
    }
}

/// Locate the compiled helper binary. Search order:
///   1. `OMI_SYS_AUDIO_HELPER` env override (for manual testing).
///   2. Alongside the main executable (production bundle layout).
///   3. `swift-helpers/bin/sys-audio-capture` relative to the workspace
///      (dev mode — `cargo run` from `desktop-v2/src-tauri/`).
fn resolve_helper_path() -> Result<PathBuf, String> {
    if let Ok(override_path) = std::env::var("OMI_SYS_AUDIO_HELPER") {
        let p = PathBuf::from(override_path);
        if p.is_file() {
            return Ok(p);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // Production: alongside the executable inside the .app bundle.
            let candidate = dir.join("sys-audio-capture");
            if candidate.is_file() {
                return Ok(candidate);
            }
            // Dev: `target/debug/nooto-desktop-v2` → walk up to workspace
            // root and into `swift-helpers/bin/`.
            let mut cur = dir.to_path_buf();
            for _ in 0..6 {
                let candidate = cur.join("swift-helpers/bin/sys-audio-capture");
                if candidate.is_file() {
                    return Ok(candidate);
                }
                if !cur.pop() {
                    break;
                }
            }
        }
    }
    Err(
        "could not find sys-audio-capture helper. Run `scripts/build-sys-audio-helper.sh` \
         or set OMI_SYS_AUDIO_HELPER=/path/to/binary"
            .to_string(),
    )
}

/// Parse helper stderr lines like
/// `[sys-audio-helper] source format: 48000.0Hz 2ch 32bits` into
/// `(rate, channels, bits)`.
fn parse_source_format(line: &str) -> Option<(f64, u32, u32)> {
    let marker = "source format: ";
    let rest = line.find(marker).map(|i| &line[i + marker.len()..])?;
    let mut parts = rest.split_whitespace();
    let rate = parts.next()?.trim_end_matches("Hz").parse::<f64>().ok()?;
    let ch = parts.next()?.trim_end_matches("ch").parse::<u32>().ok()?;
    let bits = parts.next()?.trim_end_matches("bits").parse::<u32>().ok()?;
    Some((rate, ch, bits))
}
