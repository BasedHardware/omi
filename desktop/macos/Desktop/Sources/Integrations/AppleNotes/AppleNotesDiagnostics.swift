import Foundation

/// Injection seam over the shared desktop fallback telemetry helper.
///
/// This is deliberately *not* a new counter: `DesktopAppleNotesDiagnostics`
/// forwards straight to `DesktopDiagnosticsManager.recordFallback`, the one
/// helper the fallback-telemetry contract allows. The protocol exists only so a
/// test can assert which fallbacks a code path records — and, just as
/// importantly, that a hard failure records none.
protocol AppleNotesDiagnosticsRecording: Sendable {
  func recordFallback(
    area: String,
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) async
}

struct DesktopAppleNotesDiagnostics: AppleNotesDiagnosticsRecording {
  func recordFallback(
    area: String,
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) async {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: area,
      from: from,
      to: to,
      reason: reason,
      outcome: outcome
    )
  }
}
