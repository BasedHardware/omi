import { useEffect, useState } from 'react'
import { Check, ChevronDown, MessageSquare } from 'lucide-react'
import { useAppState } from '../../state/appState'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import type { ChatApp } from '../../lib/chatApps'
import { useChatApps } from '../../hooks/useChatApps'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/Popover'
import { cn } from '../../lib/utils'

// The chat-app / persona picker (Mac ChatPage header picker parity). A compact
// selector at the head of the Hub chat panel: pick an installed chat/persona app to
// scope the conversation to it, or "omi" for the default assistant.
//
// GATE (DARK by default): renders only when the `chatAppPickerEnabled` pref is ON
// *and* the user actually has enabled chat-capable apps. The pref defaults OFF
// (undefined ⇒ off), so by default this returns null and the chat surface is
// byte-identical to today. `selectedAppId` still lives in useChat; with the picker
// hidden it is simply never set, so the send path stays on the default main chat.
//
// Selecting an app calls `useChat().selectApp(id)`, which threads `app_id` into the
// session/message calls and resets to that app's default chat (Mac's `selectApp`).

function AppIcon({ image, size }: { image: string; size: number }): React.JSX.Element {
  if (!image) {
    return (
      <span
        className="flex shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5"
        style={{ width: size, height: size }}
      >
        <MessageSquare
          className="text-white/60"
          style={{ width: size * 0.55, height: size * 0.55 }}
        />
      </span>
    )
  }
  return (
    <img
      src={image}
      alt=""
      width={size}
      height={size}
      className="shrink-0 rounded-full border border-white/10 object-cover"
      style={{ width: size, height: size }}
      onError={(e) => {
        ;(e.target as HTMLImageElement).style.visibility = 'hidden'
      }}
    />
  )
}

/** Presentational picker — a trigger button + a popover of assistants. Pure over
 *  its props so it renders identically from tests and the container. */
export function ChatAppPickerView(props: {
  apps: ChatApp[]
  selectedAppId: string | null
  onSelect: (id: string | null) => void
}): React.JSX.Element {
  const { apps, selectedAppId, onSelect } = props
  const [open, setOpen] = useState(false)
  const selected = selectedAppId ? apps.find((a) => a.id === selectedAppId) : undefined

  const pick = (id: string | null): void => {
    onSelect(id)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="focus-ring flex items-center gap-2 rounded-lg px-2 py-1 text-left transition-colors hover:bg-white/10"
          title="Chat assistant"
          aria-label="Select chat assistant"
        >
          <AppIcon image={selected?.image ?? ''} size={22} />
          <span className="max-w-[160px] truncate text-[13px] font-medium text-white/90">
            {selected ? selected.name : 'omi'}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-white/40" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <div className="max-h-[min(60vh,360px)] overflow-y-auto py-1">
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/30">
            Select Assistant
          </div>

          {/* Default (no app) — the main Omi assistant. */}
          <AssistantRow
            name="omi"
            author="Default assistant"
            image=""
            selected={selectedAppId === null}
            onSelect={() => pick(null)}
          />

          {apps.length > 0 && <div className="my-1 h-px bg-white/10" />}

          {apps.map((a) => (
            <AssistantRow
              key={a.id}
              name={a.name}
              author={a.author}
              image={a.image}
              selected={a.id === selectedAppId}
              onSelect={() => pick(a.id)}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function AssistantRow(props: {
  name: string
  author: string
  image: string
  selected: boolean
  onSelect: () => void
}): React.JSX.Element {
  const { name, author, image, selected, onSelect } = props
  return (
    <button
      type="button"
      className={cn(
        'flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-white/10',
        selected && 'bg-white/[0.06]'
      )}
      onClick={onSelect}
    >
      <AppIcon image={image} size={28} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-white/90">{name}</div>
        {author && <div className="truncate text-[11px] text-white/45">{author}</div>}
      </div>
      {selected && <Check className="h-4 w-4 shrink-0 text-white/80" />}
    </button>
  )
}

/** Gated container: reads the pref + fetches chat apps + wires selection into the
 *  shared chat engine. Renders nothing unless the pref is ON and there is at least
 *  one chat-capable app (Mac disables its picker when `chatApps.isEmpty`). */
export function ChatAppPicker(): React.JSX.Element | null {
  const [enabled, setEnabled] = useState(() => getPreferences().chatAppPickerEnabled === true)
  useEffect(() => onPreferencesChange((p) => setEnabled(p.chatAppPickerEnabled === true)), [])

  const { chat } = useAppState()
  const { chatApps } = useChatApps()

  if (!enabled || chatApps.length === 0) return null

  return (
    <div className="mb-3 flex items-center">
      <ChatAppPickerView
        apps={chatApps}
        selectedAppId={chat.selectedAppId}
        onSelect={chat.selectApp}
      />
    </div>
  )
}
