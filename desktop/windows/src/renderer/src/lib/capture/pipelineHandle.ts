// Pure stream-lifecycle glue for the pipeline adapter. The real pipeline setup
// (AudioContext + AudioWorklet.addModule) is async, but the capture host expects a
// SYNCHRONOUS handle whose stop() reliably RELEASES THE MIC — Windows shows the
// mic-in-use indicator until every track is stopped, so a stop that raced ahead of
// setup must still stop the tracks. Kept free of Web Audio / onnx imports so the
// decision logic is node-testable.

/** Minimal duck-typed views so this stays testable without DOM lib types. */
export type StoppableTrack = { stop: () => void }
export type TrackedStream = { getTracks: () => StoppableTrack[] }
export type Teardownable = { stop: () => void }
export type PipelineSetupResult = { ok: true } | { ok: false; error: Error }
export type PipelineHandle = {
  stop: () => void
  /** Resolves after the real audio graph is usable, or with its setup error. */
  ready: Promise<PipelineSetupResult>
}

/**
 * Wrap an in-flight pipeline `setup` promise in a synchronous handle.
 * - stop() before setup resolves → the resolved pipeline is torn down on arrival.
 * - stop() always stops the stream's tracks (mic released) even if setup failed or
 *   never finished.
 * - stop() is idempotent.
 */
export function makePipelineHandle(
  stream: TrackedStream,
  setup: Promise<Teardownable>
): PipelineHandle {
  let stopped = false
  let teardown: (() => void) | null = null

  const ready: Promise<PipelineSetupResult> = setup
    .then((p): PipelineSetupResult => {
      if (stopped) p.stop()
      else teardown = (): void => p.stop()
      return { ok: true }
    })
    .catch(
      (error: unknown): PipelineSetupResult => ({
        ok: false,
        error: error instanceof Error ? error : new Error(String(error))
      })
    )

  return {
    ready,
    stop: (): void => {
      if (stopped) return
      stopped = true
      teardown?.()
      for (const t of stream.getTracks()) {
        try {
          t.stop()
        } catch {
          /* ignore */
        }
      }
    }
  }
}
