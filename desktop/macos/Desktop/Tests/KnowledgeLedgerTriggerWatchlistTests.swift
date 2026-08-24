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
        "action": ["type": "agent_prompt", "prompt": "Give me the next release step."],
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
    XCTAssertEqual(
      trigger.action,
      KnowledgeLedgerTriggerAction(type: "agent_prompt", prompt: "Give me the next release step."))
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

  func testDuplicateObjectKeysFailClosedBeforeDecoding() {
    let payloads = [
      #"{"keywords":["release"],"keywords":[]}"#,
      #"{"time":{"start":"09:00","start":"10:00","end":"11:00"}}"#,
      #"{"calendar":{"event_keywords":["planning"],"event_keywords":[]}}"#,
      #"{"embedding":{"prototype_id":"first","prototype_id":"second"}}"#,
      #"{"keywords":["release"],"\u006beywords":[]}"#,
    ]

    for (index, payload) in payloads.enumerated() {
      let row = KnowledgeLedgerTriggerRow(
        id: "duplicate-\(index)",
        triggerConditionJSON: Data(payload.utf8)
      )
      guard case .failure(.malformed(_)) = KnowledgeLedgerTriggerCompiler.compile(row) else {
        return XCTFail("duplicate object keys must be quarantined: \(payload)")
      }
    }
  }

  func testObservationBoundsAreDeterministicAndFingerprintIgnoresInputOrdering() {
    let longLabel = String(repeating: "L", count: KnowledgeLedgerTriggerObservation.maxEntityLabelCharacters + 40)
    let longSelector = String(repeating: "S", count: KnowledgeLedgerTriggerObservation.maxSelectorCharacters + 40)
    let longCalendar = String(repeating: "C", count: KnowledgeLedgerTriggerObservation.maxCalendarFieldCharacters + 40)
    let labels =
      (0..<(KnowledgeLedgerTriggerObservation.maxEntityLabels + 20)).map { "entity-\($0)" }
      + [longLabel, "  ENTITY-1  "]
    let calendarEvents =
      (0..<(KnowledgeLedgerTriggerObservation.maxCalendarEvents + 10)).map {
        KnowledgeLedgerTriggerCalendarEvent(title: "Event \($0)", eventType: "Meeting")
      } + [KnowledgeLedgerTriggerCalendarEvent(title: longCalendar, eventType: longCalendar)]
    var scores = [String: Double]()
    for index in 0..<(KnowledgeLedgerTriggerObservation.maxEmbeddingScores + 10) {
      scores[String(format: "prototype-%02d", index)] = 0.5
    }
    scores[" duplicate"] = 0.9
    scores["duplicate "] = 0.7
    scores["not-finite"] = .infinity
    scores[String(repeating: "k", count: KnowledgeLedgerTriggerObservation.maxEmbeddingKeyCharacters + 1)] = 0.9

    let first = KnowledgeLedgerTriggerObservation(
      eventID: "  \(String(repeating: "e", count: KnowledgeLedgerTriggerObservation.maxEventIDCharacters + 40))  ",
      text: "release",
      entityLabels: labels,
      appName: "  \(longSelector)  ",
      windowTitle: "  \(longSelector)  ",
      calendarEvents: calendarEvents,
      embeddingScores: scores
    )
    let second = KnowledgeLedgerTriggerObservation(
      eventID: first.eventID,
      text: "release",
      entityLabels: Array(labels.reversed()),
      appName: longSelector.lowercased(),
      windowTitle: longSelector.lowercased(),
      calendarEvents: Array(calendarEvents.reversed()),
      embeddingScores: scores
    )

    XCTAssertNil(first.eventID)
    XCTAssertEqual(first.entityLabels.count, KnowledgeLedgerTriggerObservation.maxEntityLabels)
    XCTAssertTrue(
      first.entityLabels.allSatisfy { $0.count <= KnowledgeLedgerTriggerObservation.maxEntityLabelCharacters })
    XCTAssertEqual(first.appName?.count, KnowledgeLedgerTriggerObservation.maxSelectorCharacters)
    XCTAssertEqual(first.windowTitle?.count, KnowledgeLedgerTriggerObservation.maxSelectorCharacters)
    XCTAssertEqual(first.calendarEvents.count, KnowledgeLedgerTriggerObservation.maxCalendarEvents)
    XCTAssertTrue(
      first.calendarEvents.allSatisfy {
        $0.title.count <= KnowledgeLedgerTriggerObservation.maxCalendarFieldCharacters
          && $0.eventType.count <= KnowledgeLedgerTriggerObservation.maxCalendarFieldCharacters
      })
    XCTAssertEqual(first.embeddingScores.count, KnowledgeLedgerTriggerObservation.maxEmbeddingScores)
    XCTAssertTrue(
      first.embeddingScores.keys.allSatisfy { $0.count <= KnowledgeLedgerTriggerObservation.maxEmbeddingKeyCharacters })
    XCTAssertNil(first.embeddingScores["not-finite"])
    XCTAssertNil(
      first.embeddingScores[
        String(repeating: "k", count: KnowledgeLedgerTriggerObservation.maxEmbeddingKeyCharacters + 1)])
    XCTAssertEqual(first.embeddingScores["duplicate"], 0.7)
    XCTAssertEqual(first, second)
    XCTAssertEqual(first.fingerprint, second.fingerprint)
  }

  func testDecodedObservationUsesBoundsAndIsStableAcrossReorderedJSON() throws {
    let labels = (0..<(KnowledgeLedgerTriggerObservation.maxEntityLabels + 20)).map { "Entity \($0)" }
    let events = (0..<(KnowledgeLedgerTriggerObservation.maxCalendarEvents + 10)).map {
      ["title": "Event \($0)", "eventType": "Meeting"]
    }
    var scores: [String: Double] = [:]
    for index in 0..<(KnowledgeLedgerTriggerObservation.maxEmbeddingScores + 10) {
      scores["prototype-\(index)"] = 0.5
    }
    let longSelector = String(repeating: "S", count: KnowledgeLedgerTriggerObservation.maxSelectorCharacters + 40)

    func decode(labels: [String], events: [[String: String]]) throws -> KnowledgeLedgerTriggerObservation {
      let payload: [String: Any] = [
        "eventID": String(repeating: "e", count: KnowledgeLedgerTriggerObservation.maxEventIDCharacters + 1),
        "text": String(repeating: "t", count: KnowledgeLedgerTriggerObservation.maxTextCharacters + 200),
        "entityLabels": labels,
        "appName": longSelector,
        "windowTitle": longSelector,
        "calendarEvents": events,
        "embeddingScores": scores,
      ]
      return try JSONDecoder().decode(
        KnowledgeLedgerTriggerObservation.self,
        from: JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
      )
    }

    let first = try decode(labels: labels, events: events)
    let second = try decode(labels: Array(labels.reversed()), events: Array(events.reversed()))

    XCTAssertNil(first.eventID)
    XCTAssertEqual(first.text.count, KnowledgeLedgerTriggerObservation.maxTextCharacters)
    XCTAssertEqual(first.entityLabels.count, KnowledgeLedgerTriggerObservation.maxEntityLabels)
    XCTAssertEqual(first.appName?.count, KnowledgeLedgerTriggerObservation.maxSelectorCharacters)
    XCTAssertEqual(first.windowTitle?.count, KnowledgeLedgerTriggerObservation.maxSelectorCharacters)
    XCTAssertEqual(first.calendarEvents.count, KnowledgeLedgerTriggerObservation.maxCalendarEvents)
    XCTAssertEqual(first.embeddingScores.count, KnowledgeLedgerTriggerObservation.maxEmbeddingScores)
    XCTAssertEqual(first, second)
    XCTAssertEqual(first.fingerprint, second.fingerprint)
  }

  func testPathologicalDecodedCandidateCollectionsFailClosedBeforeNormalization() throws {
    var scores: [String: Double] = [:]
    for index in 0...KnowledgeLedgerTriggerObservation.maxEmbeddingScoreCandidates {
      scores["prototype-\(index)"] = 0.5
    }
    let payload: [String: Any] = [
      "entityLabels": (0...KnowledgeLedgerTriggerObservation.maxEntityLabelCandidates).map { "entity-\($0)" },
      "calendarEvents": (0...KnowledgeLedgerTriggerObservation.maxCalendarEventCandidates).map {
        ["title": "event-\($0)", "eventType": "meeting"]
      },
      "embeddingScores": scores,
    ]

    let observation = try JSONDecoder().decode(
      KnowledgeLedgerTriggerObservation.self,
      from: JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    )

    XCTAssertTrue(observation.entityLabels.isEmpty)
    XCTAssertTrue(observation.calendarEvents.isEmpty)
    XCTAssertTrue(observation.embeddingScores.isEmpty)
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
