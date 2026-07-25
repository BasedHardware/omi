import Foundation
import XCTest

@testable import Omi_Computer

/// Behavioral contract for the proactive MemoryAssistant telemetry added to close
/// the macOS memory-funnel observability gap. Mirrors the `ChatQueryTelemetryEvent`
/// allowlist pattern: every test asserts the closed schema and that no
/// screen/memory/model content can reach PostHog — not just literal event strings.
final class MemoryAssistantTelemetryTests: XCTestCase {
  // MARK: - Setting Changed

  func testSettingEnumIsClosedSet() {
    XCTAssertEqual(MemoryAssistantTelemetry.Setting.enabled.rawValue, "enabled")
    XCTAssertEqual(
      MemoryAssistantTelemetry.Setting.notificationsEnabled.rawValue, "notifications_enabled")
    // Exhaustive closed set: exactly these two settings gate analysis.
    XCTAssertEqual(
      Set(MemoryAssistantTelemetry.Setting.allCases.map(\.rawValue)),
      Set(["enabled", "notifications_enabled"]))
  }

  func testSettingChangeFiresOnlyOnRealPersistedChange() {
    // A real change in either direction is a user-initiated persisted change.
    XCTAssertTrue(
      MemoryAssistantTelemetry.settingChangeIsPersistedChange(oldValue: false, newValue: true))
    XCTAssertTrue(
      MemoryAssistantTelemetry.settingChangeIsPersistedChange(oldValue: true, newValue: false))
    // No-op (the same value written again, e.g. a re-render or reset to current)
    // must NOT fire — and neither must the startup/default-read case where the
    // persisted value equals the value being "set".
    XCTAssertFalse(
      MemoryAssistantTelemetry.settingChangeIsPersistedChange(oldValue: true, newValue: true))
    XCTAssertFalse(
      MemoryAssistantTelemetry.settingChangeIsPersistedChange(oldValue: false, newValue: false))
  }

  func testSettingChangedPayloadIsClosedSchemaAndCarriesNoContent() {
    let payload = MemoryAssistantTelemetry.settingChangedPayload(setting: .notificationsEnabled, value: true)
    // Exactly two bounded dimensions; no history, prior values, or context.
    XCTAssertEqual(Set(payload.keys), Set(["setting", "value"]))
    XCTAssertEqual(payload["setting"] as? String, "notifications_enabled")
    XCTAssertEqual(payload["value"] as? Bool, true)
  }

  // MARK: - Analysis Run

  func testAnalysisOutcomeEnumIsClosedAndSourceFaithful() {
    let expected: Set<String> = [
      "synced", "filtered_low_confidence", "no_new_memory", "sync_failed", "local_persistence_failed",
      "sync_state_persistence_failed", "analysis_failed",
    ]
    let actual = Set(MemoryAssistantTelemetry.AnalysisOutcome.allCases.map(\.rawValue))
    XCTAssertEqual(actual, expected)
  }

  func testConfidenceBucketClampsAndProducesClosedDecileRanges() {
    // Clamping below 0 and above 1.
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(-0.5), "0_10")
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(1.5), "90_100")
    // Decile boundaries (floor semantics).
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(0.0), "0_10")
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(0.69), "60_70")
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(0.70), "70_80")
    XCTAssertEqual(MemoryAssistantTelemetry.confidenceBucket(0.999), "90_100")
    // The bucket is always a closed-range string, never the raw float.
    let bucket = MemoryAssistantTelemetry.confidenceBucket(0.7321)
    let validBuckets: Set<String> = [
      "0_10", "10_20", "20_30", "30_40", "40_50",
      "50_60", "60_70", "70_80", "80_90", "90_100",
    ]
    XCTAssertTrue(validBuckets.contains(bucket))
  }

  func testAnalysisRunPayloadAlwaysCarriesOutcomeAndOmitsConfidenceWhenAbsent() {
    let payload = MemoryAssistantTelemetry.analysisRunPayload(outcome: .noNewMemory)
    XCTAssertEqual(payload["outcome"] as? String, "no_new_memory")
    XCTAssertEqual(Set(payload.keys), Set(["outcome"]))
    // no_new_memory / analysis_failed have no model confidence to report.
    XCTAssertNil(MemoryAssistantTelemetry.analysisRunPayload(outcome: .analysisFailed)["confidence_bucket"])
  }

  func testAnalysisRunPayloadBucketsConfidenceForOutcomesThatProducedAMemory() {
    let synced = MemoryAssistantTelemetry.analysisRunPayload(outcome: .synced, confidence: 0.82)
    XCTAssertEqual(synced["outcome"] as? String, "synced")
    XCTAssertEqual(synced["confidence_bucket"] as? String, "80_90")
    XCTAssertEqual(Set(synced.keys), Set(["outcome", "confidence_bucket"]))

    let filtered = MemoryAssistantTelemetry.analysisRunPayload(
      outcome: .filteredLowConfidence, confidence: 0.42)
    XCTAssertEqual(filtered["confidence_bucket"] as? String, "40_50")

    let failed = MemoryAssistantTelemetry.analysisRunPayload(outcome: .syncFailed, confidence: 0.91)
    XCTAssertEqual(failed["confidence_bucket"] as? String, "90_100")
  }

  func testAnalysisRunPayloadCannotLeakContentEvenWithAdversarialInputs() {
    // The builder only accepts an outcome + a numeric confidence; there is no
    // string/content parameter, so no memory text, app name, or model output can
    // appear regardless of what the caller holds.
    for outcome in MemoryAssistantTelemetry.AnalysisOutcome.allCases {
      let payload = MemoryAssistantTelemetry.analysisRunPayload(outcome: outcome, confidence: 0.75)
      let jsonData = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
      XCTAssertNotNil(jsonData, "analysis-run payload must be JSON-serializable")
      let serialized = String(data: jsonData ?? Data(), encoding: .utf8) ?? ""
      XCTAssertFalse(serialized.contains("secret"))
      XCTAssertFalse(serialized.contains("memory content"))
      XCTAssertFalse(serialized.contains("Safari"))
      // No raw model score leaks — only the bucket.
      XCTAssertFalse(serialized.contains("0.75"))
    }
  }

}

/// Deterministic actor used to exercise the exact production durability pipeline
/// without a Gemini/API/SQLite fixture. The pipeline itself is the object used by
/// `MemoryAssistant`, and it emits through the production AnalyticsManager.
private actor MemoryAssistantDurabilityFixtureRunner: MemoryAssistantDurabilityRunning {
  private let outcome: MemoryAssistantDurability.Outcome

  init(outcome: MemoryAssistantDurability.Outcome) {
    self.outcome = outcome
  }

  func persistAndSync(_ request: MemoryAssistantDurabilityRequest) async -> MemoryAssistantDurability.Outcome {
    outcome
  }
}

@MainActor
final class MemoryAssistantDurabilityPipelineTests: XCTestCase {
  private typealias CapturedEvent = (name: String, properties: [String: Any])
  private var captured: [CapturedEvent] = []

  override func setUp() {
    super.setUp()
    captured = []
    AnalyticsManager.shared.setMemoryAssistantTelemetryCaptureForTests { [weak self] name, properties in
      self?.captured.append((name, properties))
    }
  }

  override func tearDown() {
    AnalyticsManager.shared.setMemoryAssistantTelemetryCaptureForTests(nil)
    captured = []
    super.tearDown()
  }

  func testProductionPipelineEmitsTerminalAndHistoricalSuccessForEveryDurabilityOutcome() async {
    let cases: [(MemoryAssistantDurability.Outcome, String, Bool)] = [
      (.localPersistenceFailed, "local_persistence_failed", false),
      (.syncFailed, "sync_failed", true),
      (.syncStatePersistenceFailed, "sync_state_persistence_failed", true),
      (.synced, "synced", true),
    ]

    for (outcome, expectedTerminal, expectsHistoricalSuccess) in cases {
      captured = []
      let pipeline = MemoryAssistantDurabilityPipeline(
        runner: MemoryAssistantDurabilityFixtureRunner(outcome: outcome)
      )
      let result = await pipeline.persistSyncAndEmit(
        MemoryAssistantDurabilityRequest(
          memory: ExtractedMemory(content: "test memory", category: .system, sourceApp: "Test", confidence: 0.82),
          screenshotId: nil,
          contextSummary: "test",
          windowTitle: nil,
          ownerID: "test-owner"
        ),
        confidence: 0.82
      )

      XCTAssertEqual(result, outcome)
      XCTAssertEqual(captured.first?.name, MemoryAssistantTelemetry.analysisRunEventName)
      XCTAssertEqual(captured.first?.properties["outcome"] as? String, expectedTerminal)
      XCTAssertEqual(captured.first?.properties["confidence_bucket"] as? String, "80_90")

      let historical = captured.filter { $0.name == "Memory Extracted" }
      XCTAssertEqual(historical.count, expectsHistoricalSuccess ? 1 : 0)
      if expectsHistoricalSuccess {
        XCTAssertEqual(historical.first?.properties as? [String: Int], ["memory_count": 1])
      }
      XCTAssertEqual(captured.count, expectsHistoricalSuccess ? 2 : 1)
    }
  }
}

/// Behavioral proof that `Memory Assistant Setting Changed` records exactly one
/// closed, bounded event per real user-initiated persisted change.
///
/// The capture seam lives on `AnalyticsManager`'s main-actor boundary, so these
/// tests observe the real event and exact payload without a mutable unsafe global.
@MainActor
final class MemoryAssistantSettingChangeTelemetryTests: XCTestCase {
  private static let enabledKey = "memoryAssistantEnabled"
  private static let notificationsKey = "memoryNotificationsEnabled"
  private var savedEnabled = false
  private var savedNotifications = false
  private var captured: [(name: String, properties: [String: Any])] = []

  override func setUp() {
    super.setUp()
    savedEnabled = UserDefaults.standard.bool(forKey: Self.enabledKey)
    savedNotifications = UserDefaults.standard.bool(forKey: Self.notificationsKey)
    captured = []
    AnalyticsManager.shared.setMemoryAssistantTelemetryCaptureForTests { [weak self] name, properties in
      self?.captured.append((name, properties))
    }
  }

  override func tearDown() {
    UserDefaults.standard.set(savedEnabled, forKey: Self.enabledKey)
    UserDefaults.standard.set(savedNotifications, forKey: Self.notificationsKey)
    AnalyticsManager.shared.setMemoryAssistantTelemetryCaptureForTests(nil)
    captured = []
    super.tearDown()
  }

  func testUserToggleCapturesExactlyOneClosedEventWithExactPayload() {
    UserDefaults.standard.set(false, forKey: Self.enabledKey)
    XCTAssertTrue(MemoryAssistantSettings.shared.applyUserSettingChange(.enabled, value: true))
    XCTAssertFalse(MemoryAssistantSettings.shared.applyUserSettingChange(.enabled, value: true))

    XCTAssertEqual(captured.count, 1)
    XCTAssertEqual(captured[0].name, MemoryAssistantTelemetry.settingChangedEventName)
    XCTAssertEqual(Set(captured[0].properties.keys), Set(["setting", "value"]))
    XCTAssertEqual(captured[0].properties["setting"] as? String, "enabled")
    XCTAssertEqual(captured[0].properties["value"] as? Bool, true)
  }

  func testRemoteSyncAndResetEmitNoSettingChangeEvent() {
    SettingsSyncManager.shared.applyRemoteSettings(
      AssistantSettingsResponse(memory: MemorySettingsResponse(enabled: false, notificationsEnabled: true))
    )
    MemoryAssistantSettings.shared.resetToDefaults()

    XCTAssertTrue(captured.isEmpty)
  }
}
