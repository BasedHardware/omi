// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'

// Orb stops its WebGL loop (setVisible(false)) while the bar window is parked
// off-screen, and resumes on unpark — the fix for perf-profile 2026-07-19 hotspot
// #2 (the parked bar is never document.hidden, so the orb otherwise loops at
// display rate forever after the first summon). Stub OrbAnimator to succeed (jsdom
// has no WebGL2) and record every setVisible call; drive the parked signal through
// a mocked window.omiBar.onParked.

const setVisibleCalls: boolean[] = []
let parkedCb: ((p: boolean) => void) | null = null

/* eslint-disable @typescript-eslint/no-empty-function -- no-op OrbAnimator stub */
vi.mock('../../orb/orbAnimator', () => ({
  OrbAnimator: class {
    dispose(): void {}
    setState(): void {}
    setSpeechActive(): void {}
    setVisible(v: boolean): void {
      setVisibleCalls.push(v)
    }
    summon(): void {}
    failGesture(): void {}
    setAmplitude(): void {}
    setMorphTarget(): void {}
  }
}))
/* eslint-enable @typescript-eslint/no-empty-function */

import { Orb } from './Orb'

function installBarApi(): void {
  ;(window as unknown as { omiBar: unknown }).omiBar = {
    onParked: (cb: (p: boolean) => void) => {
      parkedCb = cb
      return () => {
        parkedCb = null
      }
    }
  }
}

beforeEach(() => {
  setVisibleCalls.length = 0
  parkedCb = null
})
afterEach(() => {
  cleanup()
  delete (window as unknown as { omiBar?: unknown }).omiBar
})

describe('Orb — parked-window idle gate', () => {
  it('stops the loop when parked and resumes when unparked', () => {
    installBarApi()
    render(<Orb size={34} state="idle" visible />)
    // Built + visible: the last visibility decision is "render".
    expect(setVisibleCalls.at(-1)).toBe(true)
    expect(parkedCb).toBeTypeOf('function')

    // Main parks the bar off-screen → orb must go 0fps even though `visible` (the
    // BarApp prop, = mode!==null) is still true and document.hidden is false.
    act(() => parkedCb?.(true))
    expect(setVisibleCalls.at(-1)).toBe(false)

    // Reveal → resume.
    act(() => parkedCb?.(false))
    expect(setVisibleCalls.at(-1)).toBe(true)
  })

  it('never goes dark for a non-bar mount (no omiBar at all)', () => {
    // Sidebar / onboarding mounts have no bar-parked feed; the orb must stay live.
    render(<Orb size={22} state="idle" visible />)
    expect(setVisibleCalls.at(-1)).toBe(true)
    expect(setVisibleCalls).not.toContain(false)
  })

  it('stays live when onParked is present but never fires (main targets only the bar)', () => {
    // The shared preload exposes omiBar in EVERY window, so a sidebar/onboarding
    // orb DOES subscribe — but main sends bar:parked only to the bar webContents,
    // so the callback never fires there. Merely subscribing must not dim the orb.
    installBarApi()
    render(<Orb size={22} state="idle" visible />)
    expect(parkedCb).toBeTypeOf('function') // subscribed…
    expect(setVisibleCalls.at(-1)).toBe(true) // …but never parked → stays live
    expect(setVisibleCalls).not.toContain(false)
  })

  it('stays hidden while parked even if the BarApp visible prop is true', () => {
    installBarApi()
    const { rerender } = render(<Orb size={34} state="idle" visible />)
    act(() => parkedCb?.(true))
    expect(setVisibleCalls.at(-1)).toBe(false)
    // A prop churn that keeps visible=true must not un-hide a parked orb.
    rerender(<Orb size={34} state="listening" visible />)
    expect(setVisibleCalls.at(-1)).toBe(false)
  })
})
