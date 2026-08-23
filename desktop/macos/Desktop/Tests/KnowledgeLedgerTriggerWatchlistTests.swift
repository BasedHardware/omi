import Foundation
import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerTriggerWatchlistTests: XCTestCase {
  func testCompilerPreservesMetadataAndEvaluatesBoundedLocalSelectors() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "trigger-release",
      triggerCondition: [
        "schema_version": "jit_trigger.v1",
        "match_mode": "all",
        "entity_aliases": ["project": ["omi", "omi app"]],
        "keywords": ["release"],
        "apps": ["Slack"],
        "windows": ["#release"],
        "embedding": ["prototype_id": "release-intent", "min_similarity": 0.8],
      ],
      modelID: "local-trigger-model",
      modelVersion: "2026-08",
      threshold: 0.91,
      wakeupBudgetPerDay: 2
    )
    let trigger = try compiled(row)

    XCTAssertEqual(trigger.metadata.modelID, "local-trigger-model")
    XCTAssertEqual(trigger.metadata.modelVersion, "2026-08")
    XCTAssertEqual(trigger.metadata.threshold, 0.91)
    XCTAssertEqual(trigger.metadata.wakeupBudgetPerDay, 2)
    let observation = KnowledgeLedgerTriggerObservation(
      eventID: "event-1",
      text: "Omi release discussion",
      entityLabels: ["Omi"],
      appName: "Slack",
      windowTitle: "#release",
      embeddingScores: ["release-intent": 0.81]
    )
    let decision = KnowledgeLedgerTriggerEvaluator.evaluate(trigger, observation: observation, day: "2026-08-23")
    XCTAssertEqual(decision.status, .match)
    XCTAssertEqual(decision.reason, "all_conditions_satisfied")
    XCTAssertEqual(decision.wakeupsUsed, 1)
    XCTAssertEqual(decision.wakeupBudgetDay, "2026-08-23")
  }

  func testUnknownFutureMalformedAndClosedRowsFailClosed() throws {
    let unknown = try KnowledgeLedgerTriggerRow(
      id: "unknown",
      triggerCondition: ["keywords": ["release"], "future_selector": true]
    )
    XCTAssertThrowsError(try requireFailure(unknown))

    let future = try KnowledgeLedgerTriggerRow(
      id: "future",
      triggerCondition: ["schema_version": "jit_trigger.v2", "keywords": ["release"]]
    )
    XCTAssertThrowsError(try requireFailure(future))

    let malformed = try KnowledgeLedgerTriggerRow(id: "malformed", triggerCondition: [:])
    XCTAssertThrowsError(try requireFailure(malformed))

    let superseded = try KnowledgeLedgerTriggerRow(
      id: "superseded",
      triggerCondition: ["keywords": ["release"]],
      supersededBy: "newer"
    )
    XCTAssertThrowsError(try requireFailure(superseded))

    let thirdParty = try KnowledgeLedgerTriggerRow(
      id: "third-party",
      triggerCondition: ["keywords": ["release"]],
      subjectScope: "third_party"
    )
    XCTAssertThrowsError(try requireFailure(thirdParty))
  }

  func testAmbiguousAndMissingContextNeverBecomeMatch() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "ambiguous",
      triggerCondition: [
        "entity_aliases": ["project": ["acme"], "person": ["acme"]],
        "embedding": ["prototype_id": "prototype", "min_similarity": 0.8],
      ]
    )
    let trigger = try compiled(row)
    let ambiguous = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger,
      observation: KnowledgeLedgerTriggerObservation(text: "Acme"),
      day: "2026-08-23"
    )
    XCTAssertEqual(ambiguous.status, .ambiguous)
    XCTAssertEqual(ambiguous.missingConditions, ["embedding:prototype", "entity:person", "entity:project"])

    let mismatch = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger,
      observation: KnowledgeLedgerTriggerObservation(text: "Other"),
      day: "2026-08-23"
    )
    XCTAssertEqual(mismatch.status, .noMatch)
    XCTAssertEqual(mismatch.reason, "condition_not_satisfied")
  }

  func testTimeCalendarAndEmbeddingUseOnlySuppliedLocalEvidence() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "calendar",
      triggerCondition: [
        "time": ["weekdays": [0], "start": "09:00", "end": "10:00", "timezone": "UTC"],
        "calendar": ["event_keywords": ["planning"], "event_types": ["meeting"]],
      ]
    )
    let trigger = try compiled(row)
    var dateComponents = DateComponents()
    dateComponents.calendar = Calendar(identifier: .gregorian)
    dateComponents.timeZone = TimeZone(secondsFromGMT: 0)
    dateComponents.year = 2026
    dateComponents.month = 8
    dateComponents.day = 24  // Monday, ISO weekday 0.
    dateComponents.hour = 9
    dateComponents.minute = 30
    let observation = KnowledgeLedgerTriggerObservation(
      occurredAt: dateComponents.date,
      calendarEvents: [KnowledgeLedgerTriggerCalendarEvent(title: "Planning", eventType: "Meeting")]
    )
    let decision = KnowledgeLedgerTriggerEvaluator.evaluate(trigger, observation: observation, day: "2026-08-24")
    XCTAssertEqual(decision.status, .match)
    XCTAssertEqual(decision.matchedConditions, ["calendar", "time"])
  }

  func testPerTriggerDayBudgetIsPureAndDeterministic() throws {
    let row = try KnowledgeLedgerTriggerRow(
      id: "budgeted",
      triggerCondition: ["keywords": ["release"]],
      wakeupBudgetPerDay: 1
    )
    let trigger = try compiled(row)
    let observation = KnowledgeLedgerTriggerObservation(eventID: "same", text: "release")
    let first = KnowledgeLedgerTriggerEvaluator.evaluate(trigger, observation: observation, day: "2026-08-23")
    let replay = KnowledgeLedgerTriggerEvaluator.evaluate(trigger, observation: observation, day: "2026-08-23")
    XCTAssertEqual(first, replay)
    XCTAssertEqual(first.status, .match)
    XCTAssertEqual(first.wakeupsUsed, 1)

    let exhausted = KnowledgeLedgerTriggerEvaluator.evaluate(
      trigger,
      observation: observation,
      day: "2026-08-23",
      wakeupsUsed: first.wakeupsUsed
    )
    XCTAssertEqual(exhausted.status, .noMatch)
    XCTAssertEqual(exhausted.reason, "wakeup_budget_exhausted")
    XCTAssertEqual(exhausted.wakeupsUsed, 1)
  }

  private func compiled(_ row: KnowledgeLedgerTriggerRow) throws -> KnowledgeLedgerCompiledTrigger {
    guard case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compile(row) else {
      XCTFail("expected valid trigger")
      throw KnowledgeLedgerTriggerCompileFailure.malformed("test fixture failed")
    }
    return trigger
  }

  private func requireFailure(_ row: KnowledgeLedgerTriggerRow) throws -> KnowledgeLedgerCompiledTrigger {
    guard case .failure(let failure) = KnowledgeLedgerTriggerCompiler.compile(row) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("expected compile failure")
    }
    throw failure
  }
}
