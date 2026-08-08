import { useNavigate } from 'react-router-dom'
import type { ChatCitation } from '../../../../shared/types'

/**
 * "Sources" strip beneath an assistant reply — the conversations the answer cited
 * (mirrors macOS ChatBubble's citation cards). The backend already strips the
 * inline `[n]` markers from the message text and hands us the cited conversations
 * in `m.citations`; this surfaces them as tappable chips that open the
 * conversation detail. Neutral, no purple (INV-UI-1).
 *
 * Main-window only: the caller renders this for the `main` variant. The floating
 * bar is a transient overlay with no room for a source list, and navigating a
 * conversation from it would be out of place.
 */
export function ChatCitations({ citations }: { citations: ChatCitation[] }): React.JSX.Element {
  const navigate = useNavigate()
  return (
    <div className="mr-auto mt-1.5 flex max-w-[85%] flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wide text-white/35">Sources</span>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => navigate(`/conversations/${c.id}`)}
            title={c.title}
            className="focus-ring flex max-w-full items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1 text-left transition-colors hover:bg-white/[0.08]"
          >
            {c.emoji ? <span className="shrink-0 text-[13px]">{c.emoji}</span> : null}
            <span className="truncate text-[12px] text-white/70">{c.title}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
