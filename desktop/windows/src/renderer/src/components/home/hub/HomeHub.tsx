import { createElement, useCallback, useEffect, useRef, useState } from 'react'
import { useAppState } from '../../../state/appState'
import { cn } from '../../../lib/utils'
import { HomeCanvasBackground } from '../HomeCanvasBackground'
import { HubHeader } from './HubHeader'
import { HubAskBar } from './HubAskBar'
import { getPendingAttachments } from '../../../lib/chatAttachments'
import { HubSuggestions } from './HubSuggestions'
import { HubStatRibbon } from './HubStatRibbon'
import { HubChatPanel } from './HubChatPanel'
import { HubChatHeader } from '../../chat/HubChatHeader'
import { ChatAppPicker } from '../../chat/ChatAppPicker'
import { HubConnectPanel } from './HubConnectPanel'
import { preloadHubConnectContent } from './hubConnectSlot'
import { getHubHomeWidgets } from './hubHomeWidgetsSlot'
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
// DELIBERATE DEVIATION FROM MAC (Chris's call). Mac's homeStageBottomPadding is a flat
// 26px (DashboardPage.swift:302) and its cluster docks right onto it, low on the stage.
//
// Everything else here is now Mac-exact — the header floats instead of eating 62px of
// stage (see below), the sidebar is gone, and the wordmark lands on the stage's true
// centre. With those bugs fixed the layout still read as bottom-heavy, so this is a real
// design preference, not compensation for a defect: we are deviating from a CORRECT
// baseline, which is the only honest place to deviate from.
//
// Scales with the window so it never crowds a short one; floors at Mac's 26px.
const STAGE_BOTTOM_INSET = 'clamp(26px, 12vh, 128px)'

// Also a deliberate deviation. Mac's Spacer(minLength: 24) (DashboardPage.swift:671) is
// the floor on the wordmark→cluster gap, and it is where the layout actually settles:
// once the wordmark is at the stage's true centre the flexible gap is squeezed to
// exactly that minimum, so 24px IS the gap in practice, not just its floor. Chris wants
// the wordmark to breathe, so raise the floor. Raising it also lifts the wordmark, since
// the top spacer is the only shrinkable item and gives way first.
const WORDMARK_GAP = 56
const STAGE_MAX = 1360
const ASK_MAX_HUB = 980
const ASK_MAX_PANEL = 1280
// The panel's CEILING, not its height. It used to be a fixed
// `clamp(440px, 100vh - 132px, 640px)`, which is computed off the VIEWPORT and so knew
// nothing about the stage's own top padding — at the default 1280x800 that made the
// panel 640px tall inside 676px of stage that already spent 56px on its lead-in, and
// the stage scrolled. The panel now FLEXES to fill whatever the stage actually has and
// merely refuses to grow past this; the message list inside it does the scrolling, as
// it should.
const PANEL_MAX_HEIGHT = 640
// Mac's layout constant for the wordmark's occupied height (DashboardPage.swift:669) —
// its 58px glyphs plus the glow's optical room. Used to place the wordmark at the
// stage's true vertical centre, exactly as Mac does.
const WORDMARK_H = 76

export function HomeHub(): React.JSX.Element {
  const { chat } = useAppState()
  const stats = useHubStats()
  // Track 3's resting-hub widget row (focused-goals chips), or null if unregistered.
  // Rendered via createElement (not <JSX/>) since it is fetched at render time —
  // mirrors HubConnectPanel's slot pattern and satisfies react-hooks/static-components.
  const homeWidgets = getHubHomeWidgets()
  const [mode, setMode] = useState<HomeStageMode>('hub')
  // The draft is LOCAL (not in the app-wide chat hook) so typing re-renders only
  // the ask bar, not the shell and every mounted page.
  const [input, setInput] = useState('')
  const stageRef = useRef<HTMLDivElement>(null)

  const dispatch = useCallback((event: HomeStageEvent): void => {
    setMode((m) => nextStage(m, event))
  }, [])

  // Warm the Connect stage's lazily-imported connections chunk shortly after the Hub
  // mounts, so the first time the user opens Connect the tray renders instantly instead
  // of flashing the Suspense fallback. This runs only here — HomeHub is the Home page,
  // mounted only in the main window — so the code-split still holds for the bar/capture/
  // glow windows, which never open Connect. Deferred to idle so it never competes with
  // the Hub's own first paint.
  useEffect(() => {
    const ric = window.requestIdleCallback
    if (ric) {
      const id = ric(() => preloadHubConnectContent(), { timeout: 2000 })
      return () => window.cancelIdleCallback?.(id)
    }
    const t = window.setTimeout(() => preloadHubConnectContent(), 200)
    return () => window.clearTimeout(t)
  }, [])

  const send = useCallback(
    (text: string): void => {
      // A send is allowed with text, with staged attachments, or both — never
      // empty. useChat.send drains the pending attachments at send time.
      if ((!text.trim() && getPendingAttachments().length === 0) || chat.sending) return
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

      {/* The header FLOATS over the stage; it does not sit in the column.
          Mac stacks it (DashboardPage.swift:584-611):

              ZStack(alignment: .topTrailing) {
                homeStage(...).frame(width: proxy.size.width, height: proxy.size.height)
                homeHeader.padding(.top, 26)
              }

          so the stage gets the window's FULL height and the header consumes none of it.
          It was a sibling row in this flex column, which quietly ate ~62px (26px pad +
          36px tall) off the top of the stage — pushing the wordmark's centre point AND
          the docked cluster down by that much. That is what made the Hub read as
          bottom-heavy, and it is why lifting the bottom inset "fixed" it: I was padding
          the floor to compensate for space being stolen from the ceiling. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-10 mx-auto flex justify-end"
        style={{
          maxWidth: STAGE_MAX,
          paddingLeft: SIDE_INSET,
          paddingRight: SIDE_INSET,
          paddingTop: 26
        }}
      >
        <div className="pointer-events-auto">
          <HubHeader />
        </div>
      </div>

      <div
        className="mx-auto flex h-full flex-col"
        style={{
          maxWidth: STAGE_MAX,
          paddingLeft: SIDE_INSET,
          paddingRight: SIDE_INSET,
          paddingBottom: STAGE_BOTTOM_INSET
        }}
      >
        {/* The stage's height budget. The cluster (ribbon + ask bar + suggestions) is
            shrink-0 and the lead-in spacer is the ONLY shrinkable item, so a shorter
            window eats the empty space above the wordmark and never the controls —
            which is Mac's topInset clamp, reproduced without measuring anything.

            `overflow-y-auto` is a FAIL-SAFE, not the mechanism. Mac has no scroll view
            here, and in the resting hub this never fires (minHeight 600 → ~438px of
            stage content, vs ~384px needed — measured, not assumed). It exists so that
            if someone later adds a 4th suggestion or a taller ask bar and busts that
            arithmetic, the ask bar becomes reachable-by-scroll instead of silently
            clipped off the bottom of the screen, which is what the first version did.
            It earned its keep immediately: a fixed-height chat panel overflowed the
            stage at the DEFAULT window size and this is what made it visible. */}
        <div
          ref={stageRef}
          className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto pt-[74px]"
          data-testid="hub-stage"
          data-mode={mode}
        >
          {isPanelMode(mode) ? (
            <StagePanel key={mode}>
              {mode === 'chat' ? (
                <HubChatPanel
                  messages={chat.history}
                  sending={chat.sending}
                  header={
                    <>
                      <ChatAppPicker />
                      <HubChatHeader />
                    </>
                  }
                >
                  {askBar}
                </HubChatPanel>
              ) : (
                <HubConnectPanel onDismiss={() => dispatch({ type: 'dismissed' })} />
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

              {/* Mac: Spacer(minLength: 24) — absorbs slack, docking the cluster. The
                  min-height (WORDMARK_GAP) is raised above Mac's 24 on Chris's call; see
                  the constant. It grows to fill any extra height, so this is the FLOOR. */}
              <div
                className="w-full shrink-0 grow"
                style={{ minHeight: WORDMARK_GAP }}
                aria-hidden
              />

              <div
                className="flex w-full shrink-0 flex-col items-center"
                style={{ maxWidth: ASK_MAX_HUB }}
                data-testid="hub-cluster"
              >
                {/* Mac order: wordmark → FocusedGoals → stat ribbon. The chip row is
                    one line + shrink-0, so it does not disturb the no-scroll flow. */}
                {homeWidgets && (
                  <div className="mb-[14px] w-full">{createElement(homeWidgets)}</div>
                )}
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
        'w-full min-h-0 flex-1 origin-top transition-[transform,opacity] duration-[460ms]',
        'ease-[cubic-bezier(0.22,1,0.36,1)]',
        entered
          ? 'translate-y-0 scale-100 opacity-100'
          : '-translate-y-[46px] scale-[0.97] opacity-0 motion-reduce:translate-y-0 motion-reduce:scale-100'
      )}
      style={{ maxWidth: ASK_MAX_PANEL, maxHeight: PANEL_MAX_HEIGHT }}
    >
      {children}
    </div>
  )
}
