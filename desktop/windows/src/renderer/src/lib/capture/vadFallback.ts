// Pure mapping of a Silero/onnxruntime init error to the AGENTS.md bounded fallback
// `reason` enum — kept free of the onnx import (unlike vadModel.ts) so it is
// node-testable without dragging the wasm runtime into the test env.

export type VadFallbackReason = 'asset_load_failed' | 'wasm_init_failed' | 'other'

/** Classify a VAD init failure message into the bounded reason set. Asset/fetch
 *  problems are checked first so a 404 on the wasm binary reads as an asset
 *  failure, not a runtime one. */
export function classifyVadFailure(message: string): VadFallbackReason {
  const m = (message || '').toLowerCase()
  if (/model file|fetch|404|not found|failed to load|network|http/.test(m))
    return 'asset_load_failed'
  if (/wasm|webassembly|backend|onnxruntime|\bort\b|onnx/.test(m)) return 'wasm_init_failed'
  return 'other'
}
