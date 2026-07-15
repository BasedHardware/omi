import { useEffect, useState } from 'react'
import { History, Plus } from 'lucide-react'
import { useAppState } from '../../state/appState'
import { useChatSessions } from '../../hooks/useChatSessions'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { Pill } from '../ui/Pill'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/Popover'
import { ChatHistoryPopover } from './ChatHistoryPopover'

// The multi-chat header row above the Hub chat panel: a Synced-Chat indicator, a
// new-chat "+", and a history clock that opens the ChatHistoryPopover. Ported
// from Mac's ChatPage header + ChatHistoryPopover.
//
// GATE (DARK invariant): the header renders ONLY when the `multiChatEnabled` pref
// is ON *and* the chat engine is pi_mono — re-threading routes a turn to a
// per-session kernel conversation, which only the pi_mono path does; under legacy
// there is no per-session memory, so a switcher would be cosmetic. Both gates
// default OFF (the pref is unset; the engine is legacy_sse — a dark main-process
// flag), so by default this returns null and the Hub is byte-identical to today.

/** Gate wrapper: renders the header only when multiChatEnabled && engine==pi_mono
 *  (so the session-fetch hook never runs on the default path). */
export function HubChatHeader(): React.JSX.Element | null {
  const [engine, setEngine] = useState<'legacy_sse' | 'pi_mono' | null>(null)
  const [multiChat, setMultiChat] = useState(() => getPreferences().multiChatEnabled === true)

  useEffect(() => onPreferencesChange((p) => setMultiChat(p.multiChatEnabled === true)), [])

  useEffect(() => {
    const getEngine = window.omi.chatGetEngine
    if (typeof getEngine !== 'function') return
    let cancelled = false
    void getEngine()
      .then((e) => {
        if (!cancelled) setEngine(e)
      })
      .catch(() => {
        /* keep null → header stays hidden (safe default) */
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!multiChat || engine !== 'pi_mono') return null
  return <HubChatHeaderInner />
}

function HubChatHeaderInner(): React.JSX.Element {
  const { chat } = useAppState()
  const sessions = useChatSessions()
  const onDefault = chat.currentThreadId === null

  // Selection re-threads the live engine AND updates the list highlight/state.
  const handleSelect = (id: string | null): void => {
    sessions.selectSession(id)
    chat.switchThread(id)
  }
  const handleCreate = (): void => {
    void sessions.createNewSession().then((created) => {
      if (created) chat.switchThread(created.id)
    })
  }

  return (
    <div className="mb-3 flex items-center gap-2">
      {onDefault ? (
        // On the default shared thread: a static synced indicator.
        <Pill dot="var(--success)" title="Synced with the mobile app">
          Synced Chat
        </Pill>
      ) : (
        // On a session: a clickable pill to return to the default shared thread.
        <Pill dot="var(--success)" onClick={() => handleSelect(null)} title="Back to Synced Chat">
          Synced
        </Pill>
      )}

      <div className="flex-1" />

      <button
        type="button"
        className="focus-ring rounded-md p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
        title="New chat"
        onClick={handleCreate}
      >
        <Plus className="h-4 w-4" />
      </button>

      <Popover>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="focus-ring rounded-md p-1.5 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
            title="Chat history"
          >
            <History className="h-4 w-4" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="p-0">
          <ChatHistoryPopover
            sessions={sessions}
            currentThreadId={chat.currentThreadId}
            onSelect={handleSelect}
            onCreate={handleCreate}
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
