import { useCallback, useEffect, useRef, useState } from 'react'
import { useAppState } from '../../../state/appState'
import { cn } from '../../../lib/utils'
import { HomeCanvasBackground } from '../HomeCanvasBackground'
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
// Mac's layout constant for the wordmark's occupied height (DashboardPage.swift:669) —
// its 58px glyphs plus the glow's optical room. Used to place the wordmark at the
// stage's true vertical centre, exactly as Mac does.
const WORDMARK_H = 76

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
      // The bar re-docks into the panel, so React remounts the input under a new
      // parent and the caret is lost — measured: after clicking the ask bar,
      // document.activeElement was BODY, i.e. the panel opened and then swallowed
      // the very keystrokes the click was inviting. Re-take focus on the way in.
      // SwiftUI's @FocusState survives the equivalent move on Mac; React's does not.
      autoFocus={isPanelMode(mode)}
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

        {/* The stage's height budget. The cluster (ribbon + ask bar + suggestions) is
            shrink-0 and the lead-in spacer is the ONLY shrinkable item, so a shorter
            window eats the empty space above the wordmark and never the controls —
            which is Mac's topInset clamp, reproduced without measuring anything.

            `overflow-y-auto` is a FAIL-SAFE, not the mechanism: at every legal window
            size (minHeight 600 → ~438px of stage content, vs ~384px needed) it never
            triggers, and Mac has no scroll view here. It exists so that if someone
            later adds a 4th suggestion or a taller ask bar and busts the arithmetic,
            the ask bar becomes reachable-by-scroll instead of silently clipped off
            the bottom of the screen — which is exactly what the previous version did. */}
        <div
          ref={stageRef}
          className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto pt-[clamp(20px,7vh,74px)]"
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
              {/* Mac's homeHubStage (DashboardPage.swift:664-704) is exactly three
                  things: a top spacer, the wordmark, and a flexible gap — with the
                  cluster (ribbon → ask bar → suggestions) docked at the bottom.
                  Nothing sits between the wordmark and the ribbon.

                  The top spacer's height is Mac's `topInset`:
                      min( (contentH - wordmark) / 2,           ← true stage centre
                           contentH - wordmark - cluster - 24 ) ← lifted so it can't collide
                  which flexbox reproduces without measuring: give the spacer a basis of
                  the true-centre value and let it SHRINK (it is the only shrinkable
                  item), so a short window eats the lead-in first and the cluster keeps
                  its full height. The wordmark rides down to the centre in a tall
                  window and lifts toward the cluster in a short one — which is why Mac
                  never needs to scroll this screen, and neither do we. */}
              <div
                className="w-full shrink"
                style={{ flexBasis: `calc((100% - ${WORDMARK_H}px) / 2)`, minHeight: 0 }}
                aria-hidden
              />

              {/* Mac hides the wordmark when its `recommendations` array is non-empty.
                  Windows has no recommendations source at all, so that branch is
                  unreachable and the wordmark renders unconditionally. */}
              <h1
                className="shrink-0 select-none font-display text-[58px] font-bold lowercase leading-none text-home-ink"
                style={{ textShadow: '0 0 26px rgb(var(--home-stage-glow-rgb) / 0.46)' }}
              >
                omi.
              </h1>

              {/* Mac: Spacer(minLength: 24) — absorbs the slack, docking the cluster. */}
              <div className="min-h-[24px] w-full shrink-0 grow" aria-hidden />

              <div
                className="flex w-full shrink-0 flex-col items-center"
                style={{ maxWidth: ASK_MAX_HUB }}
                data-testid="hub-cluster"
              >
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
        'w-full shrink-0 origin-top transition-[transform,opacity] duration-[460ms]',
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
