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
      "synced", "filtered_low_confidence", "no_new_memory", "sync_failed", "analysis_failed",
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

  // MARK: - Outcome wiring (static contract supplement)
  // The MemoryAssistant actor cannot be hermetically instantiated (it wires
  // GeminiClient / MemoryStorage / APIClient / backend sync), so the reachable
  // analysis-outcome terminals are asserted as a static-wiring tripwire that
  // *supplements* — never replaces — the behavioral builder/enum coverage above.
  func testEveryReachableAnalysisOutcomeIsEmittedFromMemoryAssistant() throws {
    // omi-test-quality: source-inspection -- static contract: the MemoryAssistant actor's external Gemini/SQLite/APIClient deps prevent hermetic behavioral instantiation; this guarantees every reachable analysis-outcome terminal (.synced/.filteredLowConfidence/.noNewMemory/.syncFailed/.analysisFailed) actually emits, so no funnel branch is silently missing.
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/ProactiveAssistants/Assistants/MemoryExtraction/MemoryAssistant.swift"),
      encoding: .utf8
    )
    // recordAnalysisOutcome(...) is the single emit helper; each outcome case
    // must appear at a terminal call site.
    XCTAssertTrue(source.contains("recordAnalysisOutcome(.analysisFailed"))
    XCTAssertTrue(source.contains("recordAnalysisOutcome(.noNewMemory"))
    XCTAssertTrue(source.contains("recordAnalysisOutcome(.filteredLowConfidence"))
    XCTAssertTrue(source.contains("recordAnalysisOutcome(.synced"))
    XCTAssertTrue(source.contains("recordAnalysisOutcome(.syncFailed"))
    // Existing success terminal is preserved (not folded into the new event).
    XCTAssertTrue(source.contains("AnalyticsManager.shared.memoryExtracted(memoryCount: 1)"))
  }
}
