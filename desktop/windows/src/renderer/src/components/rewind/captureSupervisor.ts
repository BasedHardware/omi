// Restart supervision for the Rewind capture stream. Pure event wiring, kept out
// of the capture host so the "stream died → we noticed" contract is unit-tested.
//
// A getUserMedia desktop track can end mid-session for reasons the power/lock
// directive doesn't cover — a display reconfiguration, a GPU/driver reset, or the
// captured source going away. When that happens the <video> goes dead but the
// sampling loop keeps drawing it, so every frame is blank/dark until the app is
// restarted (#10504). Watching each video track's `ended` event lets the host
// rebuild the stream instead of silently capturing darkness.

/**
 * Invoke `onDeath` once when any of the stream's video tracks ends. Returns an
 * unsubscribe that detaches the listeners (call it before tearing the stream
 * down so a stop we initiated doesn't count as a death).
 *
 * `onDeath` fires at most once even if several tracks end — the caller rebuilds
 * the whole stream, so the first death is all that matters.
 */
export function onCaptureStreamDeath(stream: MediaStream, onDeath: () => void): () => void {
  const tracks = stream.getVideoTracks()
  let fired = false
  const handler = (): void => {
    if (fired) return
    fired = true
    onDeath()
  }
  for (const track of tracks) {
    track.addEventListener('ended', handler)
  }
  return () => {
    for (const track of tracks) {
      track.removeEventListener('ended', handler)
    }
  }
}
