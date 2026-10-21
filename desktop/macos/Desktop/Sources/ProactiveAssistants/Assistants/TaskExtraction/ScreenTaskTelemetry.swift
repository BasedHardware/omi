import Foundation

/// Written by the serial per-frame coordinator; never holds content or identifiers.
final class ScreenTaskFrameMetrics: @unchecked Sendable {
  var eligibleFrames = 0
  var featureEnabledAtStart = false
  var pipeline = "screen_task_v2"
  var gateOutcome = "none"
  var auditSample = false
  var extractor = "none"
  var outcome = "completed"
  var errorClass = "none"
  var fallbackReason = "none"
  var clientBypass = false
  var invalidItems = 0
  var gateAttempts = 0
  var extractionAttempts = 0
  var legacyAttempts = 0
  var ocrMS: Double = 0
  var retrievalMS: Double = 0
  var gateMS: Double = 0
  var extractionMS: Double = 0
  var deliveryMS: Double = 0
  var counts = ScreenTaskDeliveryCounts()

  func finish(error: Error) {
    errorClass = ScreenTaskErrorPolicy.errorClass(error)
    if errorClass == "legacy_task_reservation_inactive" {
      outcome = "refused"
    } else {
      outcome = "failed"
      counts.failed += 1
    }
  }

  func properties(captureToTerminalMS: Double) -> [String: Any] {
    func timing(_ value: Double) -> Double { value.isFinite ? max(0, min(value, 86_400_000)) : 0 }
    return [
      "pipeline": pipeline, "schema_version": 2, "gate_outcome": gateOutcome,
      "audit_sample": auditSample, "extractor": extractor, "outcome": outcome, "error_class": errorClass,
      "fallback_reason": fallbackReason, "eligible_frames": eligibleFrames,
      "feature_enabled_at_start": featureEnabledAtStart, "client_bypass": clientBypass,
      "invalid_items": max(0, min(invalidItems, 8)), "gate_attempts": gateAttempts,
      "extraction_attempts": extractionAttempts, "legacy_attempts": legacyAttempts,
      "policy_rejected": counts.policyRejected, "outbox_saved": counts.outboxSaved,
      "coalesced": counts.coalesced, "pending_delivered": counts.pendingDelivered, "failed": counts.failed,
      "ocr_ms": timing(ocrMS), "retrieval_ms": timing(retrievalMS), "gate_ms": timing(gateMS),
      "extraction_ms": timing(extractionMS), "delivery_ms": timing(deliveryMS),
      "capture_to_terminal_ms": timing(captureToTerminalMS),
    ]
  }
}
