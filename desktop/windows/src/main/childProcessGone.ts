// What to do when Chromium reports a child process gone.
//
// Extracted from the index.ts handler so the decision is testable without an
// Electron app — and because getting it wrong poisons every downstream signal.
//
// The trap: on Windows a NORMAL app quit tears children down with
// TerminateProcess, which Chromium reports as `type=GPU reason=killed
// exitCode=1` — indistinguishable, field by field, from a real GPU kill. Only
// `reason === 'clean-exit'` was filtered, so every clean quit appended a fatal
// "GPU crash" line to crash.log and broadcast GPU_CONTEXT_LOST at windows that
// were already being destroyed. Five quits looked exactly like a five-crash loop
// — it fooled a human reading the log, and it would have made any fleet-wide
// fallback/Sentry telemetry keyed off this handler worthless (every clean quit in
// the fleet reporting a GPU crash). `isQuitting()` is the discriminator: the
// before-quit hook sets it before children are torn down.
export type ChildProcessGoneDetails = {
  type: string
  reason: string
}

export type ChildProcessGoneDecision = {
  // Append a fatal line to crash.log (a real, unexpected death).
  fatal: boolean
  // Tell live windows their WebGL contexts died so they can remount.
  broadcastGpuLoss: boolean
}

export function classifyChildProcessGone(
  details: ChildProcessGoneDetails,
  quitting: boolean
): ChildProcessGoneDecision {
  // Intentional teardown, either way it's reported.
  if (details.reason === 'clean-exit') return { fatal: false, broadcastGpuLoss: false }
  // We are shutting down: children dying is EXPECTED, whatever reason Chromium
  // attaches to it. Nothing is left to recover, and the windows are on their way
  // out — broadcasting at them is pointless at best.
  if (quitting) return { fatal: false, broadcastGpuLoss: false }
  // A genuine, unexpected death while the app is running.
  return { fatal: true, broadcastGpuLoss: details.type === 'GPU' }
}
