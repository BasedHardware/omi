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
): { stop: () => void } {
  let stopped = false
  let teardown: (() => void) | null = null

  setup
    .then((p) => {
      if (stopped) p.stop()
      else teardown = (): void => p.stop()
    })
    .catch(() => {
      /* setup failed — stop() still releases the tracks below */
    })

  return {
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
