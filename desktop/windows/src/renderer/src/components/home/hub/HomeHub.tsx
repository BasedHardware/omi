import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppState } from '../../../state/appState'
import { cn } from '../../../lib/utils'
import { HomeCanvasBackground } from '../HomeCanvasBackground'
import { QuickTaskWidget } from '../QuickTaskWidget'
import { QuickGoalsWidget } from '../QuickGoalsWidget'
import { HubHeader } from './HubHeader'
import { HubAskBar } from './HubAskBar'
import { HubSuggestions } from './HubSuggestions'
import { HubStatRibbon } from './HubStatRibbon'
import { HubChatPanel } from './HubChatPanel'
import { useHubStats } from './useHubStats'
import { nextStage, isPanelMode } from './hubStage'
import type { HomeStageEvent, HomeStageMode } from './hubStage'

// The Hub — the Home screen, ported from the macOS DashboardPage. One lit stage
// with three modes: the resting `hub`, the `chat` panel, and `connect`.
//
// Layout constants are Mac's, in px. The side inset and the ask-bar width are the
// two responsive ones; everything else is fixed, because on Mac these are elements
// on a stage that grows around them, not elements that stretch with it.
const SIDE_INSET = 'min(96px, max(30px, 6vw))'
const STAGE_MAX = 1360
const ASK_MAX_HUB = 980
const ASK_MAX_PANEL = 1280
const PANEL_HEIGHT = 'clamp(440px, 100vh - 132px, 640px)'

export function HomeHub(): React.JSX.Element {
  const { chat } = useAppState()
  const stats = useHubStats()
  const [mode, setMode] = useState<HomeStageMode>('hub')
  // The draft is LOCAL (not in the app-wide chat hook) so typing re-renders only
  // the ask bar, not the shell and every mounted page.
  const [input, setInput] = useState('')
  const stageRef = useRef<HTMLDivElement>(null)

  const dispatch = useCallback((event: HomeStageEvent): void => {
    setMode((m) => nextStage(m, event))
  }, [])

  const send = useCallback(
    (text: string): void => {
      if (!text.trim() || chat.sending) return
      setInput('')
      dispatch({ type: 'submitted' })
      void chat.send(text)
    },
    [chat, dispatch]
  )

  // Esc leaves any panel. Click-outside does the same — but only from a panel, and
  // only for clicks that land outside the stage content, so a click on the paper
  // around the panel dismisses it while a click inside does not.
  useEffect(() => {
    if (!isPanelMode(mode)) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') dispatch({ type: 'dismissed' })
    }
    const onDown = (e: MouseEvent): void => {
      const stage = stageRef.current
      if (stage && !stage.contains(e.target as Node)) dispatch({ type: 'dismissed' })
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onDown)
    }
  }, [mode, dispatch])

  const askBar = (
    <HubAskBar
      value={input}
      onChange={setInput}
      onSubmit={() => send(input)}
      onFocus={() => dispatch({ type: 'askFocused' })}
      sending={chat.sending}
      connectActive={mode === 'connect'}
      onToggleConnect={() => dispatch({ type: 'connectToggled' })}
    />
  )

  return (
    <div className="relative h-full overflow-hidden">
      <HomeCanvasBackground />

      <div
        className="mx-auto flex h-full flex-col"
        style={{
          maxWidth: STAGE_MAX,
          paddingLeft: SIDE_INSET,
          paddingRight: SIDE_INSET,
          paddingBottom: 26
        }}
      >
        <div className="flex shrink-0 justify-end pt-[26px]">
          <HubHeader />
        </div>

        <div
          ref={stageRef}
          className="flex min-h-0 flex-1 flex-col items-center pt-[74px]"
          data-testid="hub-stage"
          data-mode={mode}
        >
          {isPanelMode(mode) ? (
            <StagePanel key={mode}>
              {mode === 'chat' ? (
                <HubChatPanel messages={chat.history} sending={chat.sending}>
                  {askBar}
                </HubChatPanel>
              ) : (
                <ConnectPanelPlaceholder />
              )}
            </StagePanel>
          ) : (
            <>
              {/* Mac hides the wordmark when its `recommendations` array is non-empty.
                  Windows has no recommendations source at all, so that branch is
                  unreachable and the wordmark renders unconditionally. It is NOT keyed
                  to the widgets below — they are not recommendations. */}
              <h1
                className="select-none font-display text-[58px] font-bold lowercase leading-none text-home-ink"
                style={{ textShadow: '0 0 26px rgb(var(--home-stage-glow-rgb) / 0.46)' }}
              >
                omi
              </h1>

              <div className="min-h-[24px] flex-1" />

              <div className="flex w-full flex-col items-center" style={{ maxWidth: ASK_MAX_HUB }}>
                {/* Mac fills these two cluster slots with WhatMattersNow and
                    FocusedGoals. Neither exists on Windows yet — Track 3 adds them —
                    so the Hub mounts the two widgets the legacy Home already renders,
                    which are their Windows content. They are mounted AS-IS: the
                    palette pass onto home.* rides with the Track 3 swap, not this PR.
                    Dropping them would silently take tasks and goals off the default
                    screen the day the Hub ships. */}
                <div className="mb-2.5 w-full">
                  <QuickTaskWidget />
                </div>
                <div className="mb-2.5 w-full">
                  <QuickGoalsWidget />
                </div>
                <div className="mb-[14px] w-full">
                  <HubStatRibbon counts={stats} />
                </div>
                {askBar}
                <div className="mt-3 w-full">
                  <HubSuggestions onPick={send} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// Mac's "homeDropFromTop": the panel drops in from above, top-anchored, with a
// spring. The CSS translation is a 460ms ease-out on transform + opacity — an
// honest approximation of spring(0.46, 0.86), not a port of it.
//
// Under OS-level reduced motion the 46px of travel and the scale are dropped (per
// the motion charter, travel is what triggers motion sickness, not the fade), so
// only the opacity animates. The in-app "reduce motion" kill-switch zeroes the
// duration on top of that.
function StagePanel({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [entered, setEntered] = useState(false)
  useEffect(() => {
    const raf = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div
      className={cn(
        'w-full origin-top transition-[transform,opacity] duration-[460ms]',
        'ease-[cubic-bezier(0.22,1,0.36,1)]',
        entered
          ? 'translate-y-0 scale-100 opacity-100'
          : '-translate-y-[46px] scale-[0.97] opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100'
      )}
      style={{ maxWidth: ASK_MAX_PANEL, height: PANEL_HEIGHT }}
    >
      {children}
    </div>
  )
}

// Connect is a follow-up PR (the integrations tray). This is the panel chrome it
// will fill — built, but deliberately empty rather than half-built.
function ConnectPanelPlaceholder(): React.JSX.Element {
  return (
    <div
      className="flex h-full w-full items-center justify-center rounded-[26px] border"
      style={{
        borderColor: 'rgb(var(--home-stage-glow-rgb) / 0.14)',
        backgroundImage:
          'linear-gradient(to bottom, rgb(255 255 255 / 0.03), rgb(var(--home-stage-glow-rgb) / 0.05))',
        boxShadow: '0 18px 44px rgb(0 0 0 / 0.42)'
      }}
    >
      <p className="text-[13px] font-medium text-home-muted">Connections are coming soon.</p>
    </div>
  )
}
