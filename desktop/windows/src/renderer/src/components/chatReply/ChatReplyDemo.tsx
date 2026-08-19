// Canned onboarding/hub demo: a personal inbound DM and the reply Omi would
// draft as you. Always visible — the live Beeper path is optional and must not
// gate this payoff (same idea as AskDemoStep's Mac comparison image).

type ChatReplyDemoProps = {
  /** Drive the enter fade from the parent (AskDemo-style rAF). */
  revealed?: boolean
}

export function ChatReplyDemo({ revealed = true }: ChatReplyDemoProps): React.JSX.Element {
  return (
    <div
      data-testid="chat-reply-demo"
      className={
        'flex w-full flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.03] p-4 text-left transition-all duration-500 ease-out ' +
        (revealed ? 'translate-y-0 opacity-100' : 'translate-y-3 opacity-0')
      }
    >
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-white/35">
        WhatsApp · Alex
      </p>
      <Bubble who="them">hey what time does your flight land tomorrow?</Bubble>
      <Bubble who="you">{`6:40pm — I'll text when I'm through baggage.`}</Bubble>
      <p className="text-[11px] text-white/35">Drafted by Omi from your memories. You send it.</p>
    </div>
  )
}

function Bubble({ who, children }: { who: 'them' | 'you'; children: string }): React.JSX.Element {
  const mine = who === 'you'
  return (
    <div className={'flex ' + (mine ? 'justify-end' : 'justify-start')}>
      <p
        className={
          'max-w-[85%] rounded-2xl px-3.5 py-2 text-[13px] leading-snug ' +
          (mine ? 'bg-white text-black' : 'bg-white/[0.08] text-white/85')
        }
      >
        {children}
      </p>
    </div>
  )
}
