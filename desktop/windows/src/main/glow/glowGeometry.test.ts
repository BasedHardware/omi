import { describe, it, expect } from 'vitest'
import {
  planGlow,
  inflate,
  cornerRadiusFor,
  intersectsAnyDisplay,
  isSnapped,
  isExclusiveFullscreen,
  WINDOW_PAD,
  CORNER_RADIUS,
  type DisplayLike,
  type GlowTargetInput
} from './glowGeometry'

// A 1920x1080 display at 100% with a 40px taskbar — the user's actual layout.
const DISPLAY: DisplayLike = {
  bounds: { x: 0, y: 0, width: 1920, height: 1080 },
  workArea: { x: 0, y: 0, width: 1920, height: 1040 }
}
const DISPLAYS = [DISPLAY]

function input(over: Partial<GlowTargetInput>): GlowTargetInput {
  return {
    targetDip: { x: 400, y: 200, width: 900, height: 600 },
    displays: DISPLAYS,
    className: 'Notepad',
    maximized: false,
    minimized: false,
    visible: true,
    ...over
  }
}

describe('planGlow — the shipped bug', () => {
  // THE REGRESSION TEST. v1 fed GetWindowRect straight into the geometry. For a
  // maximized window GetWindowRect includes the invisible DWM resize border and
  // deliberately hangs off-screen: on this display it is (-8,-8) 1936x1048. v1's
  // four edge bands then landed off the top, left and right of the screen, and
  // only the bottom band survived — the user's "one long bar at the bottom a
  // couple centimetres above the bottom of my screen".
  //
  // A maximized window's TRUE frame (DWM extended frame bounds) is the work area.
  // A rect that spills outside it means our geometry source is wrong, so we draw
  // nothing rather than a fragment.
  it('rejects the exact maximized GetWindowRect rect — no window is shown', () => {
    const decision = planGlow(
      input({
        targetDip: { x: -8, y: -8, width: 1936, height: 1048 },
        maximized: true,
        className: 'Chrome_WidgetWin_1'
      })
    )
    expect(decision.ok).toBe(false)
    expect(decision.ok === false && decision.reason).toBe('untrusted-bounds')
  })

  it('accepts the same window read via DWM extended frame bounds (= the work area)', () => {
    const decision = planGlow(
      input({
        targetDip: { x: 0, y: 0, width: 1920, height: 1040 },
        maximized: true,
        className: 'Chrome_WidgetWin_1'
      })
    )
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    // Square corners (Win11 doesn't round maximized windows) and the maximized
    // flag the renderer needs — the outward glow is off-screen/under the taskbar,
    // so the ring's `inset` shadow layer is the only visible part.
    expect(decision.plan.radius).toBe(0)
    expect(decision.plan.maximized).toBe(true)
    expect(decision.plan.windowBounds).toEqual({
      x: -WINDOW_PAD,
      y: -WINDOW_PAD,
      width: 1920 + WINDOW_PAD * 2,
      height: 1040 + WINDOW_PAD * 2
    })
  })
})

describe('planGlow — happy path', () => {
  it('plans a padded, rounded overlay around a normal window', () => {
    const decision = planGlow(input({}))
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    expect(decision.plan.windowBounds).toEqual({
      x: 400 - WINDOW_PAD,
      y: 200 - WINDOW_PAD,
      width: 900 + WINDOW_PAD * 2,
      height: 600 + WINDOW_PAD * 2
    })
    expect(decision.plan.pad).toBe(WINDOW_PAD)
    expect(decision.plan.radius).toBe(CORNER_RADIUS)
    expect(decision.plan.maximized).toBe(false)
  })

  it('squares the corners for a snapped (half-screen) window', () => {
    const decision = planGlow(
      input({ targetDip: { x: 0, y: 0, width: 960, height: 1040 }, className: 'CabinetWClass' })
    )
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    expect(decision.plan.radius).toBe(0)
    expect(decision.plan.maximized).toBe(true)
  })

  it('scales with the display: geometry is DIP, so a 150% monitor needs no special case', () => {
    // The caller converts physical→DIP before planning; a 150% display's 1280x832
    // DIP work area behaves identically.
    const scaled: DisplayLike = {
      bounds: { x: 0, y: 0, width: 1280, height: 720 },
      workArea: { x: 0, y: 0, width: 1280, height: 693 }
    }
    const decision = planGlow(
      input({
        displays: [scaled],
        targetDip: { x: 100, y: 100, width: 600, height: 400 }
      })
    )
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    expect(decision.plan.pad).toBe(WINDOW_PAD)
  })
})

describe('planGlow — every failed gate draws nothing', () => {
  it.each([
    ['no foreground window', { targetDip: null }, 'no-window'],
    ['the desktop', { className: 'Progman' }, 'shell-window'],
    ['the taskbar', { className: 'Shell_TrayWnd' }, 'shell-window'],
    ['the Start/search flyout', { className: 'Windows.UI.Core.CoreWindow' }, 'shell-window'],
    ['an unreadable class', { className: null }, 'shell-window'],
    ['a hidden window', { visible: false }, 'not-visible'],
    ['a minimized window', { minimized: true }, 'minimized'],
    [
      'a window parked at the Win32 hidden corner',
      { targetDip: { x: -32000, y: -32000, width: 900, height: 600 } },
      'minimized'
    ],
    [
      'a tooltip-sized window',
      { targetDip: { x: 100, y: 100, width: 80, height: 400 } },
      'too-small'
    ],
    ['a degenerate rect', { targetDip: { x: 100, y: 100, width: 0, height: 0 } }, 'too-small'],
    [
      'a rect on no display at all',
      { targetDip: { x: 5000, y: 5000, width: 900, height: 600 } },
      'offscreen'
    ],
    [
      'an exclusive-fullscreen app (never paint over a game)',
      { targetDip: { x: 0, y: 0, width: 1920, height: 1080 } },
      'fullscreen'
    ]
  ])('draws nothing for %s', (_label, over, reason) => {
    const decision = planGlow(input(over as Partial<GlowTargetInput>))
    expect(decision.ok).toBe(false)
    expect(decision.ok === false && decision.reason).toBe(reason)
  })
})

describe('planGlow — multi-monitor', () => {
  // A secondary display to the right, positioned in DIP space by Electron.
  const SECOND: DisplayLike = {
    bounds: { x: 1920, y: 0, width: 1280, height: 720 },
    workArea: { x: 1920, y: 0, width: 1280, height: 693 }
  }

  it('plans around a window on the secondary display', () => {
    const decision = planGlow(
      input({
        displays: [DISPLAY, SECOND],
        targetDip: { x: 2000, y: 100, width: 800, height: 500 }
      })
    )
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    expect(decision.plan.windowBounds.x).toBe(2000 - WINDOW_PAD)
  })

  it('honours the secondary display work area when maximized there', () => {
    const decision = planGlow(
      input({
        displays: [DISPLAY, SECOND],
        targetDip: { x: 1920, y: 0, width: 1280, height: 693 },
        maximized: true
      })
    )
    expect(decision.ok).toBe(true)
    if (!decision.ok) return
    expect(decision.plan.radius).toBe(0)
  })

  it('still rejects a bad maximized rect on the secondary display', () => {
    const decision = planGlow(
      input({
        displays: [DISPLAY, SECOND],
        targetDip: { x: 1912, y: -8, width: 1296, height: 701 },
        maximized: true
      })
    )
    expect(decision.ok).toBe(false)
    expect(decision.ok === false && decision.reason).toBe('untrusted-bounds')
  })
})

describe('geometry primitives', () => {
  it('inflate grows on every side', () => {
    expect(inflate({ x: 10, y: 20, width: 100, height: 50 }, 5)).toEqual({
      x: 5,
      y: 15,
      width: 110,
      height: 60
    })
  })

  it('cornerRadiusFor squares snapped and maximized windows only', () => {
    expect(cornerRadiusFor({ maximized: false, snapped: false })).toBe(CORNER_RADIUS)
    expect(cornerRadiusFor({ maximized: true, snapped: false })).toBe(0)
    expect(cornerRadiusFor({ maximized: false, snapped: true })).toBe(0)
  })

  it('intersectsAnyDisplay is false for a rect entirely off every display', () => {
    expect(intersectsAnyDisplay({ x: 0, y: 0, width: 10, height: 10 }, DISPLAYS)).toBe(true)
    expect(intersectsAnyDisplay({ x: -500, y: 0, width: 100, height: 100 }, DISPLAYS)).toBe(false)
  })

  it('isSnapped detects a left-half snap but not a free-floating window', () => {
    expect(isSnapped({ x: 0, y: 0, width: 960, height: 1040 }, DISPLAYS)).toBe(true)
    expect(isSnapped({ x: 960, y: 0, width: 960, height: 1040 }, DISPLAYS)).toBe(true)
    expect(isSnapped({ x: 300, y: 200, width: 900, height: 600 }, DISPLAYS)).toBe(false)
  })

  it('isExclusiveFullscreen matches display bounds, not the work area', () => {
    expect(isExclusiveFullscreen({ x: 0, y: 0, width: 1920, height: 1080 }, DISPLAYS)).toBe(true)
    // Maximized: stops at the taskbar — NOT fullscreen.
    expect(isExclusiveFullscreen({ x: 0, y: 0, width: 1920, height: 1040 }, DISPLAYS)).toBe(false)
  })
})
