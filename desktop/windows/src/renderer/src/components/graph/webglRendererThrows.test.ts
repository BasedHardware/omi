// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import * as THREE from 'three'

// The load-bearing fact behind BrainGraph's probe + ErrorBoundary: when Chromium
// refuses a 3D context (GPU crash loop → domain-blocked origin), getContext returns
// null and three's WebGLRenderer CONSTRUCTOR THROWS. Onboarding mounts BrainGraph
// directly with no boundary above it, so that throw would unmount the whole React
// tree — a blank app, not just a blank map.
//
// If a three upgrade ever changes this to a soft failure, this test fails and the
// guard around it can be reconsidered. Verified against three r184.
describe('three.js WebGLRenderer on a refused context', () => {
  it('throws (so a WebGL surface MUST be probed and/or boundary-guarded)', () => {
    const canvas = document.createElement('canvas')
    canvas.getContext = (() => null) as never
    expect(() => new THREE.WebGLRenderer({ canvas })).toThrow(/creating WebGL context/i)
  })
})
