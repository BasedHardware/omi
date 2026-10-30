import Foundation
import VoiceTurnDomain

/// Replacement observations for the frozen collector. PostHog emission stays at the
/// existing call sites; this type only adds the shadow copy when the transport flag is on.
enum ClientTelemetryShadow {
  private static let lock = NSLock()
  nonisolated(unsafe) private static var recorder: ((ClientTelemetryObservation) -> Void)?
  nonisolated(unsafe) private static var dropRecorder: ((ClientTelemetryDropReason) -> Void)?

  static func resetForTests() {
    lock.lock()
    recorder = nil
    dropRecorder = nil
    lock.unlock()
  }

  static func setRecorderForTests(_ recorder: ((ClientTelemetryObservation) -> Void)?) {
    lock.lock()
    self.recorder = recorder
    lock.unlock()
  }

  static func setDropRecorderForTests(_ recorder: ((ClientTelemetryDropReason) -> Void)?) {
    lock.lock()
    dropRecorder = recorder
    lock.unlock()
  }

  static func captureScreenTaskTerminal(ownerID: String?, properties: [String: Any], occurredAt: Date = Date()) {
    guard ClientTelemetryFlags.transportShadowEnabled else { return }
    guard let channel = ClientTelemetryFlags.resolvedChannel() else { return }
    guard let ownerID, !ownerID.isEmpty else {
      noteDrop(.missingOwner)
      return
    }
    guard
      let observation = screenTaskObservation(
        ownerID: ownerID, properties: properties, occurredAt: occurredAt, channel: channel)
    else {
      noteDrop(.invalid)
      return
    }
    deliver(observation)
  }

  static func capturePhysicalVoice(
    phase: String,
    turnID: String,
    intent: String,
    route: String,
    reason: String?,
    durationMs: Int?
  ) {
    captureVoice(
      population: "physical_shortcut",
      phase: phase,
      operationRaw: turnID,
      intent: intent,
      route: route,
      reason: reason,
      durationMs: durationMs,
      outcome: phase == "terminal" ? physicalOutcome(reason: reason) : nil
    )
  }

  static func captureFloatingVoice(_ event: ChatQueryTelemetryEvent) {
    let context: ChatQueryTelemetryContext
    let phase: String
    let outcome: String?
    let reason: String?
    let durationMs: Int?
    switch event {
    case .started(let started):
      guard started.surface == "floating_voice" else { return }
      context = started
      phase = "started"
      outcome = nil
      reason = nil
      durationMs = nil
    case .completed(let completed, let duration, _):
      guard completed.surface == "floating_voice" else { return }
      context = completed
      phase = "terminal"
      outcome = "success"
      reason = nil
      durationMs = duration
    case .failed(let failed, let duration, let errorClass, _, _, _):
      guard failed.surface == "floating_voice" else { return }
      context = failed
      phase = "terminal"
      outcome = "failure"
      reason = bounded(errorClass.rawValue, allowed: floatingFailureReasons)
      durationMs = duration
    case .cancelled(let cancelled, let duration, let cancelReason, _):
      guard cancelled.surface == "floating_voice" else { return }
      context = cancelled
      phase = "terminal"
      outcome = "excluded"
      reason = bounded(cancelReason.rawValue, allowed: floatingCancelReasons)
      durationMs = duration
    }
    captureVoice(
      population: "floating_voice",
      phase: phase,
      operationRaw: context.attemptId,
      intent: "legacy",
      route: "floating_voice",
      reason: reason,
      durationMs: durationMs,
      outcome: outcome
    )
  }

  static func captureFallback(area: String, from: String, to: String, reason: String, outcome: String) {
    guard ClientTelemetryFlags.transportShadowEnabled else { return }
    guard let channel = ClientTelemetryFlags.resolvedChannel() else { return }
    guard let ownerID = ClientTelemetryIdentity.currentOwnerID(), !ownerID.isEmpty else {
      noteDrop(.missingOwner)
      return
    }
    let operationID = UUID()
    let attributes: [String: ClientTelemetryJSON] = [
      "area": .string(bounded(area, allowed: fallbackAreas, fallback: "other")),
      "from": .string(from),
      "operation_id": .string(operationID.uuidString.lowercased()),
      "outcome": .string(bounded(outcome, allowed: fallbackOutcomes, fallback: "degraded")),
      "reason": .string(reason),
      "to": .string(to),
    ]
    guard let observation = make(ownerID: ownerID, channel: channel, family: "fallback", attributes: attributes)
    else { return }
    deliver(observation)
  }

  static func screenTaskObservation(
    ownerID: String,
    properties: [String: Any],
    occurredAt: Date,
    channel: String,
    eventID: UUID = UUID(),
    operationID: UUID = UUID()
  ) -> ClientTelemetryObservation? {
    var attributes: [String: ClientTelemetryJSON] = [
      "operation_id": .string(operationID.uuidString.lowercased()),
      "schema_version": .int(2),
    ]
    for key in screenTaskStrings {
      attributes[key] = .string(screenTaskString(key, properties: properties))
    }
    for key in screenTaskInts {
      attributes[key] = .int(screenTaskInt(key, properties: properties))
    }
    for key in screenTaskBools {
      attributes[key] = .bool(screenTaskBool(key, properties: properties))
    }
    for key in screenTaskDurations {
      attributes[key] = .int(screenTaskDuration(key, properties: properties))
    }
    return make(
      ownerID: ownerID,
      channel: channel,
      family: "screen_task",
      attributes: attributes,
      occurredAt: occurredAt,
      eventID: eventID
    )
  }

  static func voiceObservation(
    ownerID: String,
    channel: String,
    population: String,
    phase: String,
    operationRaw: String,
    intent: String,
    route: String,
    reason: String?,
    durationMs: Int?,
    outcome: String?,
    occurredAt: Date = Date(),
    eventID: UUID = UUID()
  ) -> ClientTelemetryObservation? {
    let operationID = ClientTelemetryCodec.stableUUID(operationRaw)
    let boundedPopulation = bounded(population, allowed: populations)
    let boundedPhase = bounded(phase, allowed: phases)
    let boundedRoute = bounded(route, allowed: routes)
    let boundedIntent = bounded(intent, allowed: intents)
    var attributes: [String: ClientTelemetryJSON] = [
      "intent": .string(boundedIntent),
      "operation_id": .string(operationID.uuidString.lowercased()),
      "phase": .string(boundedPhase),
      "population": .string(boundedPopulation),
      "route": .string(boundedRoute),
    ]
    let boundedOutcome = outcome.map { bounded($0, allowed: outcomes) }
    if let boundedOutcome { attributes["outcome"] = .string(boundedOutcome) }
    if let reason { attributes["reason"] = .string(bounded(reason, allowed: voiceReasons)) }
    if boundedOutcome == "success", let durationMs, (0...86_400_000).contains(durationMs) {
      attributes["latency_ms"] = .int(durationMs)
    }
    return make(
      ownerID: ownerID,
      channel: channel,
      family: "voice_turn",
      attributes: attributes,
      occurredAt: occurredAt,
      eventID: eventID
    )
  }

  private static func captureVoice(
    population: String,
    phase: String,
    operationRaw: String,
    intent: String,
    route: String,
    reason: String?,
    durationMs: Int?,
    outcome: String?
  ) {
    guard ClientTelemetryFlags.transportShadowEnabled else { return }
    guard let channel = ClientTelemetryFlags.resolvedChannel() else { return }
    guard let ownerID = ClientTelemetryIdentity.currentOwnerID(), !ownerID.isEmpty else {
      noteDrop(.missingOwner)
      return
    }
    guard
      let observation = voiceObservation(
        ownerID: ownerID,
        channel: channel,
        population: population,
        phase: phase,
        operationRaw: operationRaw,
        intent: intent,
        route: route,
        reason: reason,
        durationMs: durationMs,
        outcome: outcome
      )
    else { return }
    deliver(observation)
  }

  private static func physicalOutcome(reason: String?) -> String {
    guard let reason, voiceTerminalReasons.contains(reason) else { return "unknown" }
    switch reason {
    case "success": return "success"
    case "too_short", "silent_rejected", "cancelled", "owner_changed", "interrupted_by_barge_in",
      "explicit_interrupt", "cleanup":
      return "excluded"
    default: return "failure"
    }
  }

  private static func deliver(_ observation: ClientTelemetryObservation) {
    lock.lock()
    let recorder = recorder
    lock.unlock()
    if let recorder {
      recorder(observation)
      return
    }
    Task { await ClientTelemetryTransport.shared.enqueue(observation) }
  }

  private static func noteDrop(_ reason: ClientTelemetryDropReason) {
    lock.lock()
    let recorder = dropRecorder
    lock.unlock()
    if let recorder {
      recorder(reason)
      return
    }
    Task { await ClientTelemetryTransport.shared.recordDrop(reason) }
  }

  private static func make(
    ownerID: String,
    channel: String,
    family: String,
    attributes: [String: ClientTelemetryJSON],
    occurredAt: Date = Date(),
    eventID: UUID = UUID()
  ) -> ClientTelemetryObservation? {
    guard channel == "production" || channel == "beta" else { return nil }
    guard families.contains(family) else { return nil }
    return ClientTelemetryObservation(
      eventID: eventID,
      occurredAt: occurredAt,
      platform: "macos",
      channel: channel,
      family: family,
      attributes: attributes,
      ownerID: ownerID,
      enqueuedAt: occurredAt,
      attemptCount: 0
    )
  }

  private static func bounded(_ value: String, allowed: Set<String>, fallback: String = "unknown") -> String {
    allowed.contains(value) ? value : fallback
  }

  private static func screenTaskString(_ key: String, properties: [String: Any]) -> String {
    let raw = properties[key] as? String ?? "unknown"
    let allowed = screenTaskStringSets[key] ?? ["unknown"]
    return allowed.contains(raw) ? raw : "unknown"
  }

  private static func screenTaskInt(_ key: String, properties: [String: Any]) -> Int {
    let value = properties[key]
    let number: Int
    if let int = value as? Int {
      number = int
    } else if let double = value as? Double {
      number = Int(double.rounded())
    } else if let ns = value as? NSNumber, CFGetTypeID(ns) != CFBooleanGetTypeID() {
      number = ns.intValue
    } else {
      number = 0
    }
    return max(0, number)
  }

  private static func screenTaskBool(_ key: String, properties: [String: Any]) -> Bool {
    let value = properties[key]
    if let bool = value as? Bool { return bool }
    if let ns = value as? NSNumber, CFGetTypeID(ns) == CFBooleanGetTypeID() { return ns.boolValue }
    return false
  }

  private static func screenTaskDuration(_ key: String, properties: [String: Any]) -> Int {
    let raw = properties[key] as? Double ?? (properties[key] as? NSNumber)?.doubleValue ?? 0
    guard raw.isFinite else { return 0 }
    return min(max(Int(raw.rounded()), 0), 86_400_000)
  }

  private static let families: Set<String> = ["screen_task", "voice_turn", "fallback"]
  private static let populations: Set<String> = ["physical_shortcut", "floating_voice"]
  private static let phases: Set<String> = ["started", "terminal"]
  private static let intents: Set<String> = ["hold", "locked", "legacy", "unknown"]
  private static let outcomes: Set<String> = ["success", "failure", "excluded", "unknown"]
  private static let routes: Set<String> = [
    "undecided", "hub_warm_wait", "hub", "omni_stt", "deepgram_batch", "deepgram_live", "on_device_asr",
    "floating_voice", "unknown",
  ]
  private static let voiceTerminalReasons = Set(VoiceTurnTerminalReason.allCases.map(\.rawValue))
  private static let floatingFailureReasons: Set<String> = [
    "agent_error", "agent_runtime", "attachment_upload", "authentication", "bridge_unavailable",
    "bridge_start_failed", "browser_extension_missing", "concurrent_request", "encoding", "quota",
    "resource_exhausted", "session_setup", "timeout", "tool_stall", "transient_network", "unknown",
  ]
  private static let floatingCancelReasons: Set<String> = ["superseded", "task_cancelled", "user_stop", "unknown"]
  private static let voiceReasons = voiceTerminalReasons.union(floatingFailureReasons).union(floatingCancelReasons)
    .union(["unknown"])
  private static let fallbackAreas: Set<String> = [
    "realtime_hub", "ptt_cascade", "screen_task_gate", "screen_task_extraction", "other",
  ]
  private static let fallbackOutcomes: Set<String> = ["recovered", "degraded", "exhausted"]
  private static let screenTaskStrings = [
    "pipeline", "gate_outcome", "extractor", "outcome", "error_class", "fallback_reason",
  ]
  private static let screenTaskInts = [
    "eligible_frames", "invalid_items", "gate_attempts", "extraction_attempts", "legacy_attempts",
    "policy_rejected", "outbox_saved", "coalesced", "pending_delivered", "failed",
  ]
  private static let screenTaskBools = ["audit_sample", "feature_enabled_at_start", "client_bypass"]
  private static let screenTaskDurations = [
    "ocr_ms", "retrieval_ms", "gate_ms", "extraction_ms", "delivery_ms", "capture_to_terminal_ms",
  ]
  private static let screenTaskStringSets: [String: Set<String>] = [
    "pipeline": ["screen_task_v2", "legacy", "unknown"],
    "gate_outcome": ["none", "passed", "rejected", "fail_open", "unknown"],
    "extractor": ["gemini_3_8", "legacy", "none", "unknown"],
    "outcome": ["completed", "failed", "refused", "disabled", "dedupe_skipped", "gate_rejected", "unknown"],
    "error_class": [
      "none", "legacy_task_reservation_inactive", "auth", "plan_or_quota", "backpressure", "http_terminal",
      "owner_revoked", "privacy_revoked", "cancelled", "delivery_failure", "stopped", "gate_budget_cooldown",
      "invalid_response", "provider_outage", "provider_5xx", "admission_denied", "local_failure", "unknown",
      "timeout", "offline",
    ],
    "fallback_reason": [
      "none", "ocr_unusable", "gate_invalid_response", "provider_5xx", "timeout", "offline", "dispatch_disabled",
      "unknown",
    ],
  ]
}
