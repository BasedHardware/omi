import { describe, it, expect } from 'vitest'
import { classifyVadFailure } from './vadFallback'

describe('classifyVadFailure', () => {
  it('maps model/asset fetch failures to asset_load_failed', () => {
    expect(
      classifyVadFailure('Encountered an error while loading model file /vad/silero_vad_v5.onnx')
    ).toBe('asset_load_failed')
    expect(classifyVadFailure('Failed to fetch')).toBe('asset_load_failed')
    expect(classifyVadFailure('GET /vad/ort-wasm-simd-threaded.wasm 404 (Not Found)')).toBe(
      'asset_load_failed'
    )
  })

  it('maps wasm/onnx runtime failures to wasm_init_failed', () => {
    expect(classifyVadFailure('no available backend found. ERR: [wasm] ...')).toBe(
      'wasm_init_failed'
    )
    expect(classifyVadFailure('WebAssembly.instantiate(): out of memory')).toBe('wasm_init_failed')
    expect(classifyVadFailure('onnxruntime error: session creation failed')).toBe(
      'wasm_init_failed'
    )
  })

  it('falls back to other for unrecognized messages', () => {
    expect(classifyVadFailure('something unexpected happened')).toBe('other')
    expect(classifyVadFailure('')).toBe('other')
  })

  it('prefers asset_load_failed when a wasm file 404s (asset problem, not runtime)', () => {
    expect(classifyVadFailure('failed to load wasm: 404 not found')).toBe('asset_load_failed')
  })
})
