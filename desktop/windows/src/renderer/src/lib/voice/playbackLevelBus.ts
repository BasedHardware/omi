// Window-scoped signal for the loudness of Omi's OWN audible reply — the
// linear 0..1 peak of the PCM actually played out, posted by the player worklet
// (~31Hz while playing, one trailing 0 at burst end; see PlaybackLevelMeter).
//
// Why a module-level signal and not a config thread: the PCM player is
// constructed deep inside the provider sessions (hubSession / geminiSession),
// whose construction chain runs through the turn driver. A shared signal lets
// the player publish and the hub driver host (→ IPC → bar orb) subscribe
// without threading a callback through that chain. Only one player audibly
// plays at a time (the voice-output lease), so the stream is unambiguous.
//
// Built on lib/signal.ts (the codebase's tested pub/sub primitive). Its
// replay-current-value-on-subscribe is benign here: the value is only read
// while a reply is actually speaking, and a mount-time replay is stale past
// PLAYBACK_LEVEL_FRESH_MS anyway.
import { createSignal, type Signal } from '../signal'

export const playbackLevel: Signal<number> = createSignal(0)
