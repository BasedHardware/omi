import { useEffect, useRef, useState } from 'react'
import { Markdown } from '../Markdown'

// Smooth text reveal, decoupled from SSE chunk sizes so a reply streams in evenly
// instead of landing in bulky jumps. Rendered as markdown either way. Shared by
// the floating bar (BarChatSurface) and the main window (Home) so both threads
// stream the same way. `startRevealed` renders the full text immediately (for any
// message that isn't the one currently streaming).
const REVEAL_MS = 16
const REVEAL_MIN_CHARS = 2

export function RevealMarkdown({
  text,
  startRevealed
}: {
  text: string
  startRevealed: boolean
}): React.JSX.Element {
  const [shown, setShown] = useState(startRevealed ? text.length : 0)
  const targetRef = useRef(text)
  // eslint-disable-next-line react-hooks/refs -- intentional latest-ref / lazy-init (reads newest value in once-registered listeners & imperative loops, avoids stale closures)
  targetRef.current = text
  useEffect(() => {
    // A revealed message (every message except the one currently streaming) needs
    // no timer — arming one per message would leave N idle 62Hz intervals ticking
    // forever in an open thread. When streaming ends the parent flips this to true,
    // re-running the effect so the reveal interval is cleared.
    if (startRevealed) return
    const id = setInterval(() => {
      setShown((prev) => {
        const t = targetRef.current.length
        if (prev >= t) return prev
        const step = Math.max(REVEAL_MIN_CHARS, Math.ceil((t - prev) / 24))
        return Math.min(t, prev + step)
      })
    }, REVEAL_MS)
    return () => clearInterval(id)
  }, [startRevealed])
  // Revealed messages always render in full — so a stream that finishes mid-reveal
  // (startRevealed flips true, interval cleared) shows the whole reply, not a
  // frozen prefix.
  return <Markdown text={startRevealed ? text : text.slice(0, shown)} />
}
