// Standalone orb harness — the deterministic development surface for the orb
// shader. Plain Chromium page (no Electron, no React): the driver scripts under
// scripts/orb/ build this with vite, serve it, and drive `window.orb` via
// Playwright. Time is ALWAYS injected: `renderAt` takes an explicit t and
// renders exactly one frame, so every check (readPixels invariants, motion
// profile, contact sheet) is reproducible pixel-for-pixel.
//
// URL params:
//   size=<px>      canvas CSS size (default 96)
//   dpr=<n>        device-pixel-ratio override (default real DPR)
//   preset=<name>  choreography preset (default/calm/lively/notch)
//   state=<s>      initial state (idle/listening/thinking/agents)
//   t=<sec>        initial time to render
//   live=1         run the self-throttled OrbAnimator instead (perf checks)
//   bg=checker     checkerboard page background (transparency review)
import './style.css'
import {
  computeOrbFrame,
  ORB_PRESETS,
  DEFAULT_ORB_PARAMS,
  type OrbParams,
  type OrbState
} from '../src/renderer/src/orb/choreography'
import { OrbRenderer, DEFAULT_MORPH_RECT, type OrbRect } from '../src/renderer/src/orb/orbRenderer'
import { OrbAnimator } from '../src/renderer/src/orb/orbAnimator'

type RenderSpec = {
  t: number
  state?: OrbState
  stateTime?: number
  amplitude?: number
  genesisTime?: number
  morph?: number
  preset?: string
  params?: Partial<OrbParams>
  rect?: OrbRect
}

const qs = new URLSearchParams(location.search)
const size = Number(qs.get('size') ?? 96)
const dpr = Number(qs.get('dpr') ?? window.devicePixelRatio ?? 1)
if (qs.get('bg') === 'checker') document.body.classList.add('checker')

const canvas = document.getElementById('orb') as HTMLCanvasElement
canvas.style.width = `${size}px`
canvas.style.height = `${size}px`
canvas.width = Math.round(size * dpr)
canvas.height = Math.round(size * dpr)

function resolveParams(spec: RenderSpec): OrbParams {
  const base = ORB_PRESETS[spec.preset ?? qs.get('preset') ?? 'default'] ?? DEFAULT_ORB_PARAMS
  return spec.params ? { ...base, ...spec.params } : base
}

const api = {
  presets: Object.keys(ORB_PRESETS),
  renderer: null as OrbRenderer | null,
  animator: null as OrbAnimator | null,

  /** Render exactly one deterministic frame. */
  renderAt(spec: RenderSpec): void {
    if (!this.renderer) this.renderer = new OrbRenderer(canvas)
    const frame = computeOrbFrame({
      t: spec.t,
      state: spec.state ?? (qs.get('state') as OrbState) ?? 'idle',
      stateTime: spec.stateTime ?? spec.t,
      amplitude: spec.amplitude,
      genesisTime: spec.genesisTime,
      morph: spec.morph,
      params: resolveParams(spec)
    })
    this.renderer.render(frame, spec.rect ?? DEFAULT_MORPH_RECT)
  },

  /** RGBA readback of the last rendered frame (base64 so it crosses evaluate). */
  pixels(): { width: number; height: number; data: string } {
    if (!this.renderer) throw new Error('renderAt first')
    const bytes = this.renderer.readPixels()
    let bin = ''
    const chunk = 0x8000
    for (let i = 0; i < bytes.length; i += chunk) {
      bin += String.fromCharCode(...bytes.subarray(i, i + chunk))
    }
    return { width: canvas.width, height: canvas.height, data: btoa(bin) }
  },

  // --- Live mode (perf/throttle checks; uses the app's real OrbAnimator) -----
  startLive(state: OrbState = 'idle'): void {
    if (!this.animator) this.animator = new OrbAnimator(canvas)
    this.animator.setState(state)
  },
  liveSetState(state: OrbState): void {
    this.animator?.setState(state)
  },
  liveSetVisible(visible: boolean): void {
    this.animator?.setVisible(visible)
  },
  liveSummon(): void {
    this.animator?.summon()
  },
  liveFrameLog(): number[] {
    return this.animator ? [...this.animator.frameLog] : []
  },
  liveClearLog(): void {
    this.animator?.frameLog.splice(0)
  }
}

declare global {
  interface Window {
    orb: typeof api
  }
}
window.orb = api

// Initial paint so a human opening the page sees something.
if (qs.get('live') === '1') {
  api.startLive((qs.get('state') as OrbState) ?? 'idle')
} else {
  api.renderAt({ t: Number(qs.get('t') ?? 1.2) })
}
