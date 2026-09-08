import XCTest

@testable import Omi_Computer

final class KnowledgeLedgerTriggerRuntimeTests: XCTestCase {
  func testDefaultOffAndCompatibilityRollbackPreserveAmbientFallbackWithoutEvaluation() throws {
    let projection = try makeProjection([keywordTrigger(id: "planned", keyword: "release")])
    let observation = KnowledgeLedgerTriggerObservation(text: "release")

    let defaultOff = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: projection,
      observation: observation,
      day: "2026-08-24")
    let rollback = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: projection,
      observation: observation,
      day: "2026-08-24",
      authority: authority(mode: .compatibilityRollback))
    let killed = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: projection,
      observation: observation,
      day: "2026-08-24",
      authority: authority(killSwitchEnabled: true))

    for result in [defaultOff, rollback, killed] {
      XCTAssertEqual(result.status, .inactive)
      XCTAssertEqual(result.nextLane, .ambientFallback)
      XCTAssertTrue(result.matches.isEmpty)
      XCTAssertTrue(result.ambiguous.isEmpty)
      XCTAssertTrue(result.noMatches.isEmpty)
      XCTAssertTrue(result.projectionQuarantine.isEmpty)
    }
  }

  func testEnabledRuntimeRejectsCorruptWakeupCountersWithoutOverflow() throws {
    let projection = try makeProjection([keywordTrigger(id: "planned", keyword: "release")])
    for (used, expectedID) in [(Int.max, "planned"), (-1, "negative")] {
      let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: projection,
        observation: KnowledgeLedgerTriggerObservation(text: "release"),
        day: "2026-08-24",
        authority: authority(),
        wakeupsUsedByTrigger: [expectedID: used])

      XCTAssertEqual(result.status, .rejected)
      XCTAssertEqual(result.rejection, .invalidWakeupCounter(expectedID))
      XCTAssertEqual(result.nextLane, .none)
      XCTAssertTrue(result.matches.isEmpty)
      XCTAssertTrue(result.projectionQuarantine.isEmpty)
    }

    let saturated = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: projection,
      observation: KnowledgeLedgerTriggerObservation(text: "release"),
      day: "2026-08-24",
      authority: authority(),
      wakeupsUsedByTrigger: ["planned": Int.max - 1])
    XCTAssertEqual(saturated.status, .evaluated)
    XCTAssertEqual(saturated.matches.first?.decision.wakeupsUsed, Int.max)
  }

  func testRollbackAuthorityWinsBeforeOversizedDarkRuntimeState() throws {
    let oversizedEntries = try (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWatchlistEntries).map {
      try compiled(keywordTrigger(id: "oversized-\($0)", keyword: "release"))
    }
    let oversizedQuarantine = (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWatchlistEntries).map {
      KnowledgeLedgerTriggerWatchlistProjection.QuarantinedRow(id: "quarantined-\($0)", failure: .closedRow)
    }
    let projection = KnowledgeLedgerTriggerWatchlistProjection(
      entries: oversizedEntries,
      quarantined: oversizedQuarantine)
    let oversizedWakeups = Dictionary(
      uniqueKeysWithValues: (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWakeupCounterCandidates).map {
        ("trigger-\($0)", 1)
      })

    let authorities = [
      KnowledgeLedgerTriggerRuntimeAuthority.defaultOff,
      authority(mode: .compatibilityRollback),
      authority(killSwitchEnabled: true),
    ]
    for authority in authorities {
      let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: projection,
        observation: KnowledgeLedgerTriggerObservation(text: "release"),
        day: "not-a-day",
        authority: authority,
        wakeupsUsedByTrigger: oversizedWakeups)

      XCTAssertEqual(result.status, .inactive)
      XCTAssertNil(result.rejection)
      XCTAssertEqual(result.nextLane, .ambientFallback)
      XCTAssertTrue(result.matches.isEmpty)
      XCTAssertTrue(result.ambiguous.isEmpty)
      XCTAssertTrue(result.noMatches.isEmpty)
    }
  }

  func testEnabledRuntimeEvaluatesEveryLocalSelectorAndPrioritizesPlannedMatch() throws {
    let trigger = try KnowledgeLedgerTriggerRow(
      id: "planned",
      triggerCondition: [
        "schema_version": "jit_trigger.v1",
        "match_mode": "all",
        "entity_aliases": ["project": ["Omi"]],
        "keywords": ["release"],
        "apps": ["Slack"],
        "windows": ["#release"],
        "time": ["weekdays": [0], "start": "09:00", "end": "10:00", "timezone": "UTC"],
        "calendar": ["event_keywords": ["planning"], "event_types": ["meeting"]],
        "embedding": embeddingCondition("release-intent"),
      ],
      modelID: "local-embedder",
      modelVersion: "v1",
      threshold: 0.82,
      wakeupBudgetPerDay: 2)
    var date = DateComponents()
    date.calendar = Calendar(identifier: .gregorian)
    date.timeZone = TimeZone(secondsFromGMT: 0)
    date.year = 2026
    date.month = 8
    date.day = 24
    date.hour = 9
    date.minute = 30

    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([trigger]),
      observation: KnowledgeLedgerTriggerObservation(
        eventID: "event-1",
        text: "Omi release",
        entityLabels: ["Omi"],
        appName: "Slack",
        windowTitle: "#release planning",
        occurredAt: date.date,
        calendarEvents: [.init(title: "Planning", eventType: "Meeting")],
        embeddingScores: ["release-intent": 0.9]),
      day: "2026-08-24",
      authority: authority(),
      embeddingContract: .init(
        modelID: "local-embedder", modelVersion: "v1", language: "en",
        prototypeRevision: "prototype-v1"))

    XCTAssertEqual(result.status, .evaluated)
    XCTAssertEqual(result.nextLane, .plannedTrigger)
    XCTAssertEqual(result.matches.map(\.triggerID), ["planned"])
    XCTAssertEqual(
      result.matches.first?.decision.matchedConditions,
      ["app", "calendar", "embedding:release-intent", "entity:project", "keywords", "time", "window"])
    XCTAssertTrue(result.ambiguous.isEmpty)
    XCTAssertTrue(result.rejectedEntries.isEmpty)
  }

  func testAmbiguousPlannedTriggerPrecedesAmbientAndNeverInvokesAFullModelLane() throws {
    let trigger = try KnowledgeLedgerTriggerRow(
      id: "needs-local-score",
      triggerCondition: ["embedding": embeddingCondition("intent")],
      modelID: "local-embedder",
      modelVersion: "v1",
      threshold: 0.82)

    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([trigger]),
      observation: KnowledgeLedgerTriggerObservation(text: "unrelated"),
      day: "2026-08-24",
      authority: authority(),
      embeddingContract: .init(
        modelID: "local-embedder", modelVersion: "v1", language: "en",
        prototypeRevision: "prototype-v1"))

    XCTAssertEqual(result.nextLane, .boundedPlannedTriage)
    XCTAssertEqual(result.ambiguous.map(\.triggerID), ["needs-local-score"])
    XCTAssertFalse(KnowledgeLedgerTriggerRuntimeNextLane.allCasesForTest.contains("full_model"))
  }

  func testNoPlannedCandidateUsesCheapAmbientFallback() throws {
    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([keywordTrigger(id: "planned", keyword: "release")]),
      observation: KnowledgeLedgerTriggerObservation(text: "lunch"),
      day: "2026-08-24",
      authority: authority())

    XCTAssertEqual(result.status, .evaluated)
    XCTAssertEqual(result.nextLane, .ambientFallback)
    XCTAssertEqual(result.noMatches.map(\.triggerID), ["planned"])
  }

  /// Owner decision 2026-09-01: an account with no standing trigger hands off to
  /// the bounded ambient lane instead of going silent (the #12452 behaviour left
  /// every trigger-less JIT account with zero proactive output).
  func testEmptyCompleteWatchlistFallsThroughToAmbient() throws {
    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([] as [KnowledgeLedgerTriggerRow]),
      observation: KnowledgeLedgerTriggerObservation(text: "lunch"),
      day: "2026-08-24",
      authority: authority())

    XCTAssertEqual(result.status, .evaluated)
    XCTAssertEqual(result.nextLane, .ambientFallback)
    XCTAssertTrue(result.matches.isEmpty)
    XCTAssertTrue(result.noMatches.isEmpty)
  }

  func testOwnerGenerationSnapshotAndDayFailuresAreFailClosed() throws {
    let projection = try makeProjection([keywordTrigger(id: "planned", keyword: "release")])
    let observation = KnowledgeLedgerTriggerObservation(text: "release")
    let cases: [(KnowledgeLedgerTriggerRuntimeAuthority, String, KnowledgeLedgerTriggerRuntimeRejection)] = [
      (authority(authorizationIsCurrent: false), "2026-08-24", .staleAuthorization),
      (authority(snapshotOwnerID: "owner-b"), "2026-08-24", .snapshotOwnerMismatch),
      (authority(snapshotAccountGeneration: 8), "2026-08-24", .snapshotGenerationMismatch),
      (authority(snapshotIsAuthoritative: false), "2026-08-24", .nonAuthoritativeSnapshot),
      (authority(), "2026-02-30", .invalidDay),
    ]

    for (authority, day, rejection) in cases {
      let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: projection, observation: observation, day: day, authority: authority)
      XCTAssertEqual(result.status, .rejected)
      XCTAssertEqual(result.rejection, rejection)
      XCTAssertEqual(result.nextLane, .none)
      XCTAssertTrue(result.matches.isEmpty)
    }
  }

  func testEmbeddingModelAndVersionContractsRejectOnlyUnsafeEntries() throws {
    let safe = try keywordTrigger(id: "keyword", keyword: "release")
    let unsafe = [
      try embeddingTrigger(id: "model", modelID: "other-embedder", modelVersion: "v1", threshold: 0.82),
      try embeddingTrigger(id: "version", modelID: "local-embedder", modelVersion: "v2", threshold: 0.82),
    ]
    let projection = try makeProjection(unsafe + [safe])

    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: projection,
      observation: KnowledgeLedgerTriggerObservation(text: "release", embeddingScores: ["intent": 0.99]),
      day: "2026-08-24",
      authority: authority(),
      embeddingContract: .init(
        modelID: "local-embedder", modelVersion: "v1", language: "en",
        prototypeRevision: "prototype-v1"))

    XCTAssertEqual(result.nextLane, .plannedTrigger)
    XCTAssertEqual(result.matches.map(\.triggerID), ["keyword"])
    XCTAssertEqual(
      result.rejectedEntries,
      [
        .init(triggerID: "model", reason: .embeddingModelMismatch),
        .init(triggerID: "version", reason: .embeddingVersionMismatch),
      ])
  }

  func testRejectedOrQuarantinedPlannedAuthoritySuppressesAmbientUntilSafelyEvaluated() throws {
    let rejected = try embeddingTrigger(
      id: "missing-contract", modelID: "local-embedder", modelVersion: "v1", threshold: 0.8)
    let rejectedResult = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([rejected]),
      observation: KnowledgeLedgerTriggerObservation(embeddingScores: ["intent": 0.99]),
      day: "2026-08-24",
      authority: authority())
    let quarantinedResult = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: .init(
        entries: [],
        quarantined: [.init(id: "unsafe", failure: .malformed("invalid trigger"))]),
      observation: KnowledgeLedgerTriggerObservation(),
      day: "2026-08-24",
      authority: authority())

    for result in [rejectedResult, quarantinedResult] {
      XCTAssertEqual(result.status, .evaluated)
      XCTAssertEqual(result.nextLane, .none)
      XCTAssertTrue(result.matches.isEmpty)
      XCTAssertTrue(result.ambiguous.isEmpty)
    }
    XCTAssertEqual(rejectedResult.rejectedEntries.map(\.triggerID), ["missing-contract"])
    XCTAssertEqual(quarantinedResult.projectionQuarantine.map(\.id), ["unsafe"])
  }

  func testConfirmedPlannedWinnerStillOutranksRejectedSibling() throws {
    let confirmed = try keywordTrigger(id: "confirmed", keyword: "release")
    let rejected = try embeddingTrigger(
      id: "missing-contract", modelID: "local-embedder", modelVersion: "v1", threshold: 0.8)

    let result = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection([rejected, confirmed]),
      observation: KnowledgeLedgerTriggerObservation(
        text: "release", embeddingScores: ["intent": 0.99]),
      day: "2026-08-24",
      authority: authority())

    XCTAssertEqual(result.nextLane, .plannedTrigger)
    XCTAssertEqual(result.matches.map(\.triggerID), ["confirmed"])
    XCTAssertEqual(result.rejectedEntries.map(\.triggerID), ["missing-contract"])
  }

  func testEvaluationIsBoundedAndDeterministicAcrossProjectionOrder() throws {
    let rows = try (0..<12).map { try keywordTrigger(id: String(format: "trigger-%02d", $0), keyword: "release") }
    let first = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection(rows),
      observation: KnowledgeLedgerTriggerObservation(text: "release"),
      day: "2026-08-24",
      authority: authority())
    let second = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: try makeProjection(rows.reversed()),
      observation: KnowledgeLedgerTriggerObservation(text: "release"),
      day: "2026-08-24",
      authority: authority())

    XCTAssertEqual(first, second)
    XCTAssertEqual(first.matches.map(\.triggerID), rows.map(\.id).sorted())

    let oversizedEntries = try (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWatchlistEntries).map {
      try compiled(keywordTrigger(id: "oversized-\($0)", keyword: "release"))
    }
    let oversized = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: .init(entries: oversizedEntries, quarantined: []),
      observation: KnowledgeLedgerTriggerObservation(text: "release"),
      day: "2026-08-24",
      authority: authority())
    XCTAssertEqual(oversized.rejection, .watchlistBoundsExceeded)
    XCTAssertEqual(oversized.nextLane, .none)

    let duplicate = try compiled(keywordTrigger(id: "duplicate", keyword: "release"))
    let duplicateResult = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: .init(entries: [duplicate, duplicate], quarantined: []),
      observation: KnowledgeLedgerTriggerObservation(text: "release"),
      day: "2026-08-24",
      authority: authority())
    XCTAssertEqual(duplicateResult.rejection, .duplicateTriggerID("duplicate"))

    let oversizedQuarantine = (0...KnowledgeLedgerTriggerWatchlistRuntime.maxWatchlistEntries).map {
      KnowledgeLedgerTriggerWatchlistProjection.QuarantinedRow(id: "quarantined-\($0)", failure: .closedRow)
    }
    let quarantineResult = KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
      projection: .init(entries: [], quarantined: oversizedQuarantine),
      observation: KnowledgeLedgerTriggerObservation(),
      day: "2026-08-24",
      authority: authority())
    XCTAssertEqual(quarantineResult.rejection, .watchlistBoundsExceeded)
    XCTAssertTrue(quarantineResult.projectionQuarantine.isEmpty)
  }

  func testRuntimeCapMatchesAuthoritativeSnapshotCap() throws {
    let atCap = try (0..<500).map {
      try compiled(keywordTrigger(id: "at-cap-\($0)", keyword: "release"))
    }
    let aboveCap = try (0..<501).map {
      try compiled(keywordTrigger(id: "above-cap-\($0)", keyword: "release"))
    }

    XCTAssertEqual(KnowledgeLedgerTriggerWatchlistRuntime.maxWatchlistEntries, 500)
    XCTAssertEqual(
      KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: .init(entries: atCap, quarantined: []),
        observation: .init(text: "release"),
        day: "2026-08-24",
        authority: authority()
      ).status,
      .evaluated)
    XCTAssertEqual(
      KnowledgeLedgerTriggerWatchlistRuntime.evaluate(
        projection: .init(entries: aboveCap, quarantined: []),
        observation: .init(text: "release"),
        day: "2026-08-24",
        authority: authority()
      ).rejection,
      .watchlistBoundsExceeded)
  }

  private func authority(
    mode: KnowledgeLedgerTriggerRuntimeAuthority.Mode = .enabled,
    killSwitchEnabled: Bool = false,
    authorizationIsCurrent: Bool = true,
    snapshotOwnerID: String = "owner-a",
    snapshotAccountGeneration: Int = 7,
    snapshotIsAuthoritative: Bool = true
  ) -> KnowledgeLedgerTriggerRuntimeAuthority {
    KnowledgeLedgerTriggerRuntimeAuthority(
      mode: mode,
      killSwitchEnabled: killSwitchEnabled,
      ownerID: "owner-a",
      accountGeneration: 7,
      snapshotOwnerID: snapshotOwnerID,
      snapshotAccountGeneration: snapshotAccountGeneration,
      snapshotIsAuthoritative: snapshotIsAuthoritative,
      authorizationIsCurrent: authorizationIsCurrent)
  }

  private func keywordTrigger(id: String, keyword: String) throws -> KnowledgeLedgerTriggerRow {
    try KnowledgeLedgerTriggerRow(
      id: id,
      triggerCondition: ["schema_version": "jit_trigger.v1", "keywords": [keyword]])
  }

  private func embeddingTrigger(
    id: String,
    modelID: String?,
    modelVersion: String?,
    threshold: Double?
  ) throws -> KnowledgeLedgerTriggerRow {
    try KnowledgeLedgerTriggerRow(
      id: id,
      triggerCondition: [
        "embedding": embeddingCondition(
          "intent", modelID: modelID ?? "local-embedder", modelVersion: modelVersion ?? "v1")
      ],
      modelID: modelID,
      modelVersion: modelVersion,
      threshold: threshold)
  }

  private func embeddingCondition(
    _ prototypeID: String, modelID: String = "local-embedder", modelVersion: String = "v1"
  ) -> [String: Any] {
    [
      "prototype_id": prototypeID, "prototype_revision": "prototype-v1",
      "model_id": modelID, "model_version": modelVersion, "language": "en",
      "min_similarity": 0.82,
    ]
  }

  private func makeProjection<S: Sequence>(_ rows: S) throws -> KnowledgeLedgerTriggerWatchlistProjection
  where S.Element == KnowledgeLedgerTriggerRow {
    KnowledgeLedgerTriggerWatchlistProjection(
      entries: try rows.map(compiled),
      quarantined: [])
  }

  private func compiled(_ row: KnowledgeLedgerTriggerRow) throws -> KnowledgeLedgerCompiledTrigger {
    guard case .success(let trigger) = KnowledgeLedgerTriggerCompiler.compile(row) else {
      throw KnowledgeLedgerTriggerCompileFailure.malformed("test fixture failed")
    }
    return trigger
  }
}

extension KnowledgeLedgerTriggerRuntimeNextLane {
  fileprivate static var allCasesForTest: [String] {
    [none, plannedTrigger, boundedPlannedTriage, ambientFallback].map(\.rawValue)
  }
}
