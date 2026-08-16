// A transient chip that surfaces WHY a push-to-talk hold produced no reply —
// "Hold longer to record", "Mic heard nothing…", "Microphone unavailable",
// "Transcription failed…". It sits just BELOW the collapsed pill (the bar window
// is oversized and mostly transparent, so there is room), because during a
// summon-hotkey hold the bar is a pill, not the expanded panel — the panel's
// limit-notice strip is invisible then.
//
// Mac parity: macOS renders the same text INLINE in the notch
// (FloatingControlBarView `Text(state.pttHintText)`, set by
// PushToTalkManager.finishTooShortPTTTurnWithHint). The narrow Windows pill can't
// fit a full sentence, so the equivalent chip drops just under it.
//
// Purely informational and defensive: it renders NOTHING when there is no message
// (the success path is untouched), and the styling is click-through
// (pointer-events:none in bar.css) so it can never interfere with the pill's
// hit-rect, the orb, or the bar's motion. The message text comes straight from
// usePushToTalk's own self-clearing hint/error timers — this component owns no
// timer and no state.
export function BarHintStrip({ text }: { text: string | null }): React.JSX.Element | null {
  if (!text) return null
  return (
    <div className="bar-hint" role="status">
      {text}
    </div>
  )
}
