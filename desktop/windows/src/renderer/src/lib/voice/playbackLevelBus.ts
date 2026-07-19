// Renderer-local pub/sub for the loudness of Omi's OWN audible reply — the
// linear 0..1 peak of the PCM actually played out, posted by the player worklet
// (~31Hz while playing, one trailing 0 at burst end; see PlaybackLevelMeter).
//
// Why a bus and not a config thread: the PCM player is constructed deep inside
// the provider sessions (hubSession / geminiSession), whose construction chain
// runs through the turn driver. A module-level bus lets the player publish and
// a host component (VoiceHubDriverHost → IPC → bar orb) subscribe without
// threading a callback through files an in-flight branch owns. Window-scoped by
// nature (one module instance per renderer); only one player audibly plays at a
// time (the voice-output lease), so the stream is unambiguous.

type PlaybackLevelListener = (level: number) => void

const listeners = new Set<PlaybackLevelListener>()

/** Publish the latest played-audio peak (canonical linear 0..1). */
export function publishPlaybackLevel(level: number): void {
  for (const listener of [...listeners]) listener(level)
}

/** Subscribe to played-audio peaks. Returns an unsubscribe fn. */
export function subscribePlaybackLevel(cb: PlaybackLevelListener): () => void {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}
