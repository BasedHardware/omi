/// Video chunk encoder — pipes raw RGBA frames to ffmpeg for H.264 MP4 output.
/// Produces 60-second fragmented MP4 chunks (first chunk 5s for fast startup).

use anyhow::{Context, Result};
use image::RgbaImage;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::Instant;

const CHUNK_DURATION_SECS: u64 = 60;
const FIRST_CHUNK_DURATION_SECS: u64 = 5;
const ASPECT_RATIO_CHANGE_THRESHOLD: f64 = 0.2;
const MAX_CONSECUTIVE_FAILURES: u32 = 5;

pub struct VideoChunkEncoder {
    videos_dir: PathBuf,
    ffmpeg_path: PathBuf,
    ffmpeg_child: Option<Child>,
    ffmpeg_stdin: Option<std::process::ChildStdin>,
    chunk_start: Option<Instant>,
    current_width: u32,
    current_height: u32,
    current_aspect: f64,
    frame_count: usize,
    chunk_index: u32,
    has_finalized_any: bool,
    consecutive_failures: u32,
}

impl VideoChunkEncoder {
    pub fn new(videos_dir: PathBuf, ffmpeg_override: Option<String>) -> Result<Self> {
        let ffmpeg_path = match ffmpeg_override {
            Some(ref p) if !p.is_empty() => PathBuf::from(p),
            _ => find_ffmpeg().ok_or_else(|| anyhow::anyhow!("ffmpeg not found in PATH"))?,
        };

        if !ffmpeg_path.exists() && ffmpeg_override.is_some() {
            anyhow::bail!("Configured ffmpeg path does not exist: {}", ffmpeg_path.display());
        }

        std::fs::create_dir_all(&videos_dir).context("create videos dir")?;

        Ok(Self {
            videos_dir,
            ffmpeg_path,
            ffmpeg_child: None,
            ffmpeg_stdin: None,
            chunk_start: None,
            current_width: 0,
            current_height: 0,
            current_aspect: 0.0,
            frame_count: 0,
            chunk_index: 0,
            has_finalized_any: false,
            consecutive_failures: 0,
        })
    }

    pub fn add_frame(&mut self, rgba: &RgbaImage) -> Result<()> {
        if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES {
            anyhow::bail!("Too many consecutive ffmpeg failures, encoder disabled");
        }

        let w = rgba.width();
        let h = rgba.height();
        let aspect = w as f64 / h as f64;

        let aspect_changed = self.current_width > 0
            && ((aspect - self.current_aspect).abs() / self.current_aspect) > ASPECT_RATIO_CHANGE_THRESHOLD;

        let chunk_expired = self.chunk_start.map(|start| {
            let limit = if self.has_finalized_any { CHUNK_DURATION_SECS } else { FIRST_CHUNK_DURATION_SECS };
            start.elapsed().as_secs() >= limit
        }).unwrap_or(false);

        if aspect_changed || chunk_expired {
            if let Err(e) = self.finalize_current() {
                tracing::warn!("[VIDEO] Finalize error during split: {e}");
            }
        }

        if self.ffmpeg_child.is_none() {
            self.start_new_chunk(w, h)?;
        }

        let stdin = self.ffmpeg_stdin.as_mut()
            .ok_or_else(|| anyhow::anyhow!("No ffmpeg stdin"))?;

        match stdin.write_all(rgba.as_raw()) {
            Ok(()) => {
                self.frame_count += 1;
                self.consecutive_failures = 0;
                Ok(())
            }
            Err(e) => {
                self.consecutive_failures += 1;
                tracing::error!("[VIDEO] Write frame failed ({}/{}): {e}",
                    self.consecutive_failures, MAX_CONSECUTIVE_FAILURES);
                self.kill_ffmpeg();
                Err(e.into())
            }
        }
    }

    fn start_new_chunk(&mut self, width: u32, height: u32) -> Result<()> {
        let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S");
        let chunk_path = self.videos_dir.join(format!("chunk_{ts}_{}.mp4", self.chunk_index));
        self.chunk_index += 1;

        // Ensure even dimensions (H.264 requires this)
        let ew = width + (width % 2);
        let eh = height + (height % 2);

        let mut child = Command::new(&self.ffmpeg_path)
            .args([
                "-f", "rawvideo",
                "-pixel_format", "rgba",
                "-video_size", &format!("{ew}x{eh}"),
                "-framerate", "1",
                "-i", "pipe:0",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                "-f", "mp4",
                "-y",
            ])
            .arg(&chunk_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .context("Failed to spawn ffmpeg")?;

        self.ffmpeg_stdin = child.stdin.take();
        self.ffmpeg_child = Some(child);
        self.chunk_start = Some(Instant::now());
        self.current_width = width;
        self.current_height = height;
        self.current_aspect = width as f64 / height as f64;
        self.frame_count = 0;

        tracing::info!("[VIDEO] Started chunk: {} ({}x{})", chunk_path.display(), ew, eh);
        Ok(())
    }

    pub fn finalize_current(&mut self) -> Result<Option<PathBuf>> {
        drop(self.ffmpeg_stdin.take());

        if let Some(mut child) = self.ffmpeg_child.take() {
            match child.wait() {
                Ok(status) => {
                    if status.success() {
                        self.has_finalized_any = true;
                        tracing::info!("[VIDEO] Chunk finalized ({} frames)", self.frame_count);
                    } else {
                        tracing::warn!("[VIDEO] ffmpeg exited with: {status}");
                    }
                }
                Err(e) => {
                    tracing::warn!("[VIDEO] ffmpeg wait error: {e}");
                }
            }
        }

        self.chunk_start = None;
        Ok(None)
    }

    fn kill_ffmpeg(&mut self) {
        drop(self.ffmpeg_stdin.take());
        if let Some(mut child) = self.ffmpeg_child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.chunk_start = None;
    }
}

impl Drop for VideoChunkEncoder {
    fn drop(&mut self) {
        let _ = self.finalize_current();
    }
}

/// Search for ffmpeg in common locations.
pub fn find_ffmpeg() -> Option<PathBuf> {
    let candidates = [
        "ffmpeg",
        "ffmpeg.exe",
    ];

    for name in &candidates {
        if let Ok(output) = Command::new(if cfg!(windows) { "where" } else { "which" })
            .arg(name)
            .output()
        {
            if output.status.success() {
                let path = String::from_utf8_lossy(&output.stdout).trim().lines().next()?.to_string();
                let p = PathBuf::from(&path);
                if p.exists() {
                    return Some(p);
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        let program_files = std::env::var("ProgramFiles").unwrap_or_default();
        let extras = [
            PathBuf::from(&program_files).join("ffmpeg").join("bin").join("ffmpeg.exe"),
            PathBuf::from(r"C:\ffmpeg\bin\ffmpeg.exe"),
        ];
        for p in &extras {
            if p.exists() {
                return Some(p.clone());
            }
        }
    }

    None
}

/// Check if ffmpeg is available.
pub fn is_ffmpeg_available() -> bool {
    find_ffmpeg().is_some()
}
