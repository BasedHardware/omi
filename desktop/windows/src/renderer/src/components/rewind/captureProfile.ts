// Resolution/quality profile for Rewind screen capture. Pure and side-effect free
// so the tradeoff is unit-tested rather than buried in the capture host.
//
// Why two profiles instead of one higher value: the getUserMedia stream is decoded
// continuously in the renderer, so its resolution sets the steady-state cost of
// having capture on (1080p@30fps froze; 1080p@2fps was laggy — hence the 720p@1fps
// baseline). Users who need OCR of on-screen text can opt into `high`, accepting the
// cost; everyone else keeps the perf-tuned default. Frame rate stays at 1fps in both
// — only the per-frame resolution/quality changes (#10489).

export type RewindCaptureProfile = {
  /** getUserMedia mandatory max stream dimensions. */
  maxWidth: number
  maxHeight: number
  /** Longest sampled canvas edge; frames larger than this are downscaled. */
  maxEdge: number
  /** JPEG encode quality (0–1) for the stored frame. */
  jpegQuality: number
}

const STANDARD: RewindCaptureProfile = {
  maxWidth: 1280,
  maxHeight: 720,
  maxEdge: 1600,
  jpegQuality: 0.6
}

// Higher resolution + less JPEG compression so small on-screen text survives for
// OCR. Bounded at 1080p (not native) to keep the opt-in cost predictable.
const HIGH_RES: RewindCaptureProfile = {
  maxWidth: 1920,
  maxHeight: 1080,
  maxEdge: 1920,
  jpegQuality: 0.85
}

export function rewindCaptureProfile(highResCapture: boolean): RewindCaptureProfile {
  return highResCapture ? HIGH_RES : STANDARD
}

/**
 * Sampled canvas dimensions for a source video of `videoWidth`×`videoHeight` under
 * `profile`. Preserves aspect ratio and never upscales (scale capped at 1).
 */
export function sampledCanvasSize(
  videoWidth: number,
  videoHeight: number,
  profile: RewindCaptureProfile
): { width: number; height: number } {
  const longest = Math.max(videoWidth, videoHeight)
  const scale = longest > 0 ? Math.min(1, profile.maxEdge / longest) : 1
  return { width: Math.round(videoWidth * scale), height: Math.round(videoHeight * scale) }
}
