import Foundation

/// Closed, privacy-safe telemetry contract for the proactive macOS
/// `MemoryAssistant` (the screen-context extraction feature).
///
/// This mirrors the `ChatQueryTelemetryEvent` allowlist pattern: payloads are
/// pure value builders carrying only bounded dimensions. They never include
/// screen pixels, OCR text, window/app names, memory content, prompts, Gemini
/// responses, raw errors, or raw model material. Confidence is retained only as
/// a coarse bucket.
///
/// Two events live here, both distinct from the existing `Memory Extracted`
/// success terminal and from the recording-reconciliation `Memory Created` event
/// (which is a conversation/recording-session proxy, not an extracted memory):
///
/// - `Memory Assistant Setting Changed` — emitted on a user-initiated persisted
///   change to the two assistant settings that gate analysis, so the true
///   activation denominator (monitoring users who also enabled memory
///   notifications) becomes measurable.
///
/// - `Memory Assistant Analysis Run` — emitted once per *actual* Gemini
///   analysis attempt (not per captured frame and not on disabled/gated paths),
///   with a closed terminal `outcome`. It makes the analysis→extraction funnel
///   observable instead of exposing only the success terminal.
enum MemoryAssistantTelemetry {
  /// PostHog event names. Stable identifiers — do not rename (analytics queries
  /// depend on them).
  static let settingChangedEventName = "Memory Assistant Setting Changed"
  static let analysisRunEventName = "Memory Assistant Analysis Run"

  // MARK: - Setting Changed

  /// The two MemoryAssistant settings that gate analysis. Closed set.
  enum Setting: String, CaseIterable {
    /// Assistant master enable.
    case enabled
    /// Notifications enable — the effective analysis gate (defaults off).
    case notificationsEnabled = "notifications_enabled"
  }

  /// True only when the persisted value actually changed, so the event fires on a
  /// real user-initiated change and never on app startup / default reads /
  /// migrations (the getter returns defaults; no migration writes these keys and
  /// `MemoryAssistantSettings.init` is empty). Pure function so the gating is
  /// fully unit-tested; the property setter forwards to `AnalyticsManager`.
  static func settingChangeIsPersistedChange(oldValue: Bool, newValue: Bool) -> Bool {
    oldValue != newValue
  }

  /// Closed-schema payload for the setting-change event. The property carries only
  /// the bounded `setting` dimension and the boolean `value` — no setting history,
  /// prior values, or surrounding context.
  static func settingChangedPayload(setting: Setting, value: Bool) -> [String: Any] {
    [
      "setting": setting.rawValue,
      "value": value,
    ]
  }

  // MARK: - Analysis Run

  /// Terminal outcome of one actual analysis attempt. Closed set — every
  /// reachable analysis terminal maps to exactly one case. Do not invent cases
  /// that cannot occur.
  enum AnalysisOutcome: String, CaseIterable {
    /// Analysis succeeded, produced a memory that passed the confidence
    /// threshold, and was persisted + synced to the backend.
    case synced
    /// Analysis succeeded and produced a memory that was below the confidence
    /// threshold (filtered out before persistence).
    case filteredLowConfidence = "filtered_low_confidence"
    /// Analysis succeeded but produced no new memory (model decided nothing to
    /// extract, or returned an empty result set).
    case noNewMemory = "no_new_memory"
    /// Analysis succeeded and the memory passed the threshold and was saved
    /// locally, but backend synchronization failed.
    case syncFailed = "sync_failed"
    /// The SQLite insert did not complete, so no backend sync was attempted and
    /// no historical `Memory Extracted` success is emitted.
    case localPersistenceFailed = "local_persistence_failed"
    /// Backend create completed, but writing the local synced-state receipt
    /// failed. This is deliberately distinct from a fully synced extraction.
    case syncStatePersistenceFailed = "sync_state_persistence_failed"
    /// The analysis call itself failed (provider error / no decodable result)
    /// before any memory could be classified.
    case analysisFailed = "analysis_failed"
  }

  /// Buckets a raw model confidence `[0, 1]` into closed decile ranges so the
  /// raw score never reaches PostHog. Values outside `[0, 1]` are clamped.
  static func confidenceBucket(_ confidence: Double) -> String {
    let clamped = min(max(confidence, 0), 1)
    // Floor to a decile, capping the lower bound at 90 so the top bucket is the
    // closed range 90_100 (a confidence of exactly 1.0 must not yield "100_100").
    let lower = min(Int((clamped * 10).rounded(.down)) * 10, 90)
    let upper = lower + 10
    return "\(lower)_\(upper)"
  }

  /// Builds the analysis-run payload. `confidence` is only meaningful for
  /// outcomes where the model returned a confidence (a memory was produced); it
  /// is omitted (not bucketed to a fake value) for `noNewMemory` /
  /// `analysisFailed`.
  static func analysisRunPayload(
    outcome: AnalysisOutcome,
    confidence: Double? = nil
  ) -> [String: Any] {
    var properties: [String: Any] = ["outcome": outcome.rawValue]
    if let confidence {
      properties["confidence_bucket"] = confidenceBucket(confidence)
    }
    return properties
  }
}

/// The durability boundary for a proactive memory extraction after the model has
/// produced a candidate. Keeping the three real persistence operations in this
/// injectable helper lets tests exercise SQLite-insert and sync-state failures
/// without constructing the Gemini-backed assistant actor.
enum MemoryAssistantDurability {
  enum Outcome: String, Equatable {
    /// Local SQLite insert, backend create, and local synced-state update all
    /// completed. This is the only fully synced terminal.
    case synced
    /// No local record was durably inserted, so backend sync must not run.
    case localPersistenceFailed = "local_persistence_failed"
    /// The local record exists, but backend create did not succeed.
    case syncFailed = "sync_failed"
    /// Backend create succeeded but the local record could not be marked synced.
    case syncStatePersistenceFailed = "sync_state_persistence_failed"

    /// Preserve the historical `Memory Extracted` success meaning: it requires
    /// a durable local memory record, but is not a claim that the local
    /// `backendSynced` bookkeeping update completed.
    var shouldEmitMemoryExtracted: Bool {
      self != .localPersistenceFailed
    }
  }

  /// Runs the real local-insert → backend-create → local-sync-state sequence.
  /// The closures are deliberately injectable so error boundaries are covered
  /// behaviorally with deterministic SQLite/API stand-ins.
  static func persistAndSync<LocalRecord, BackendMemory>(
    persist: () async -> LocalRecord?,
    sync: (LocalRecord) async -> BackendMemory?,
    markSynced: (LocalRecord, BackendMemory) async throws -> Void
  ) async -> Outcome {
    guard let localRecord = await persist() else {
      return .localPersistenceFailed
    }
    guard let backendMemory = await sync(localRecord) else {
      return .syncFailed
    }
    do {
      try await markSynced(localRecord, backendMemory)
      return .synced
    } catch {
      return .syncStatePersistenceFailed
    }
  }
}
