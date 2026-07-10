import Foundation
import XCTest
@testable import Omi_Computer

final class MemoryTaskInterruptionLedger: TaskInterruptionLedgerPersisting {
  var ledger = TaskInterruptionLedger()
  func load() -> TaskInterruptionLedger { ledger }
  func save(_ ledger: TaskInterruptionLedger) { self.ledger = ledger }
}

final class FakeTaskContextualResurfacingClient: TaskContextualResurfacingClient {
  var workflowMode: OmiAPI.TaskWorkflowMode = .read
  var snapshots: [OmiAPI.NormalizedContextSnapshot] = []
  var evaluations: [OmiAPI.EvaluationRequest] = []

  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: 1, workflowMode: workflowMode)
  }

  func replaceTaskContextSnapshot(
    _ snapshot: OmiAPI.NormalizedContextSnapshot
  ) async throws -> OmiAPI.SnapshotReceipt {
    snapshots.append(snapshot)
    return OmiAPI.SnapshotReceipt(
      expiresAt: snapshot.expiresAt,
      replaced: true,
      snapshotId: snapshot.snapshotId
    )
  }

  func evaluateWhatMattersNow(
    _ request: OmiAPI.EvaluationRequest
  ) async throws -> OmiAPI.WhatMattersNowProjection {
    evaluations.append(request)
    return OmiAPI.WhatMattersNowProjection(
      evaluationId: "evaluation-1",
      expiresAt: "2030-01-01T00:00:00Z",
      generatedAt: "2029-12-31T23:00:00Z",
      materialVersion: "material-1",
      outputVersion: "output-1",
      recommendations: [],
      schemaVersion: 1
    )
  }
}

final class TaskContextualResurfacingTests: XCTestCase {
  private let baseDate = Date(timeIntervalSince1970: 1_800_000_000)

  func testNormalizationHashesRawContextAndCoalescesRapidSwitchesByWorkstream() throws {
    let subject = TaskContextSubject(kind: .task, id: "task-1", workstreamID: "workstream-1")
    let first = try XCTUnwrap(TaskLocalContextEvent.appWindow(
      appName: "Slack",
      windowTitle: "Sarah — Project Atlas (3)",
      subject: subject,
      occurredAt: baseDate
    ))
    let cosmeticDuplicate = try XCTUnwrap(TaskLocalContextEvent.appWindow(
      appName: "Slack",
      windowTitle: "Sarah — Project Atlas (9)",
      subject: subject,
      occurredAt: baseDate.addingTimeInterval(1)
    ))
    let document = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .document,
      rawReference: "Project Atlas launch brief",
      subject: subject,
      occurredAt: baseDate.addingTimeInterval(2)
    ))
    var accumulator = TaskContextEventAccumulator()
    accumulator.insert(first, now: baseDate)
    accumulator.insert(cosmeticDuplicate, now: baseDate)
    accumulator.insert(document, now: baseDate)

    XCTAssertEqual(first.referenceHash, cosmeticDuplicate.referenceHash)
    XCTAssertFalse(first.referenceHash.contains("sarah"))
    XCTAssertEqual(accumulator.pendingWorkstreamCount, 1)
    XCTAssertEqual(accumulator.drain(now: baseDate).count, 2)
  }

  func testRapidContextEventsProduceOneEvaluationAndOneBoundedSnapshot() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(client: client, debounceInterval: 60)
    let subject = TaskContextSubject(kind: .workstream, id: "workstream-1", workstreamID: "workstream-1")
    for (kind, reference) in [
      (TaskContextEventKind.appWindow, "Slack tab A"),
      (.person, "Sarah"),
      (.document, "Atlas brief"),
    ] {
      let event = try XCTUnwrap(TaskLocalContextEvent.normalized(
        kind: kind,
        rawReference: reference,
        subject: subject,
        occurredAt: baseDate
      ))
      await service.observe(event)
    }

    let pendingWorkstreams = await service.pendingWorkstreamCount()
    XCTAssertEqual(pendingWorkstreams, 1)
    await service.flush()

    XCTAssertEqual(client.evaluations.count, 1)
    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertEqual(client.snapshots[0].matches?.count, 1)
    XCTAssertEqual(
      client.snapshots[0].matches?.first?.signals.map(\.rawValue).sorted(),
      ["app", "document", "person"]
    )

    for (kind, reference) in [
      (TaskContextEventKind.appWindow, "Slack tab A"),
      (.person, "Sarah"),
      (.document, "Atlas brief"),
    ] {
      let repeated = try XCTUnwrap(TaskLocalContextEvent.normalized(
        kind: kind,
        rawReference: reference,
        subject: subject,
        occurredAt: baseDate
      ))
      await service.observe(repeated)
    }
    await service.flush()
    XCTAssertEqual(client.evaluations.count, 1)
  }

  func testUnmatchedContextClearsPriorSnapshotBeforeReevaluation() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(client: client, debounceInterval: 60)
    let event = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .appWindow,
      rawReference: "Unmatched browser tab",
      occurredAt: baseDate
    ))

    await service.observe(event)
    await service.flush()

    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertEqual(client.snapshots[0].matches?.count, 0)
    XCTAssertEqual(client.evaluations.count, 1)
  }

  @MainActor
  func testLocalMatcherLearnsRecentContextWithoutPersistingRawText() throws {
    let suite = "task-context-matcher-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let matcher = TaskContextSubjectMatcher(defaults: defaults, ownerID: "owner-1")
    let raw = "Sarah — confidential Slack thread"
    let unrelatedRaw = "Unrelated document tab"
    let unrelated = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .document,
      rawReference: unrelatedRaw,
      occurredAt: baseDate.addingTimeInterval(-1)
    ))
    XCTAssertNil(matcher.resolve(unrelated, now: baseDate).subject)
    let first = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .appWindow,
      rawReference: raw,
      occurredAt: baseDate
    ))
    XCTAssertNil(matcher.resolve(first, now: baseDate).subject)

    let subject = TaskContextSubject(kind: .workstream, id: "workstream-1", workstreamID: "workstream-1")
    matcher.bindRecentContext(to: subject, now: baseDate.addingTimeInterval(1))
    matcher.bindRecentContext(
      to: TaskContextSubject(kind: .workstream, id: "workstream-2", workstreamID: "workstream-2"),
      now: baseDate.addingTimeInterval(1)
    )
    let reopened = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .appWindow,
      rawReference: raw,
      occurredAt: baseDate.addingTimeInterval(2)
    ))
    XCTAssertEqual(matcher.resolve(reopened, now: baseDate.addingTimeInterval(2)).subject, subject)
    let unrelatedReopened = try XCTUnwrap(TaskLocalContextEvent.normalized(
      kind: .document,
      rawReference: unrelatedRaw,
      occurredAt: baseDate.addingTimeInterval(2)
    ))
    XCTAssertNil(matcher.resolve(unrelatedReopened, now: baseDate.addingTimeInterval(2)).subject)
    XCTAssertEqual(matcher.resolve(reopened, now: baseDate.addingTimeInterval(4)).subject, subject)

    let persisted = defaults.dictionaryRepresentation().values.compactMap { $0 as? Data }
      .compactMap { String(data: $0, encoding: .utf8) }.joined()
    XCTAssertFalse(persisted.localizedCaseInsensitiveContains("sarah"))
    XCTAssertTrue(persisted.contains("workstream-1"))
  }

  @MainActor
  func testContextualNavigationRouteSurvivesUntilDashboardConsumesIt() {
    let router = ContextualTaskNavigationRouter()
    router.request(recommendationID: "output-1:dedupe-1")
    XCTAssertEqual(router.pendingRecommendationID, "output-1:dedupe-1")
    XCTAssertNil(router.consume(requestedID: "different"))
    XCTAssertEqual(router.consume(), "output-1:dedupe-1")
    XCTAssertNil(router.consume())
  }

  func testRecommendationEligibilityIsIndependentFromInterruptionSettings() {
    let denial = TaskRecommendationEligibility.denial(
      for: TaskRecommendationEligibilityInput(
        isOpen: true,
        expiresAt: baseDate.addingTimeInterval(60),
        hasEvidence: true,
        hasConcreteAction: true,
        dedupeAlreadyActive: false
      ),
      now: baseDate
    )
    XCTAssertNil(denial)

    let trace = gate().evaluate(
      candidate: candidate(),
      configuration: configuration(enabled: false),
      environment: environment()
    )
    XCTAssertEqual(trace.reason, .notEnrolled)
  }

  func testRecommendationEligibilityRejectsWeakOrDuplicateItems() {
    XCTAssertEqual(eligibility(hasEvidence: false), .insufficientEvidence)
    XCTAssertEqual(eligibility(hasConcreteAction: false), .missingConcreteAction)
    XCTAssertEqual(eligibility(dedupeAlreadyActive: true), .duplicate)
    XCTAssertEqual(eligibility(expiresAt: baseDate), .expired)
  }

  func testInterruptionGateHonorsSettingsFocusSnoozeExpiryAndCanWait() {
    let cases: [(TaskInterruptionEnvironment, TaskInterruptionCandidate, TaskInterruptionGateReason)] = [
      (environment(master: false), candidate(), .masterDisabled),
      (environment(frequency: false), candidate(), .frequencyDisabled),
      (environment(ambientFrequency: false), candidate(), .frequencyBudget),
      (environment(task: false), candidate(), .taskDisabled),
      (environment(focus: true), candidate(), .focusSuppressed),
      (environment(snoozed: true), candidate(), .snoozed),
      (environment(), candidate(expiresAt: baseDate), .expired),
      (environment(), candidate(canWait: true), .canWait),
    ]
    for (environment, candidate, expected) in cases {
      XCTAssertEqual(
        gate().evaluate(
          candidate: candidate,
          configuration: configuration(),
          environment: environment
        ).reason,
        expected
      )
    }
  }

  func testInterruptionGateHonorsQuietHoursAcrossMidnight() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let late = ISO8601DateFormatter().date(from: "2027-01-15T23:00:00Z")!
    let midday = ISO8601DateFormatter().date(from: "2027-01-15T12:00:00Z")!

    XCTAssertEqual(
      gate().evaluate(
        candidate: candidate(expiresAt: late.addingTimeInterval(60)),
        configuration: configuration(quiet: true),
        environment: environment(now: late, calendar: calendar)
      ).reason,
      .quietHours
    )
    XCTAssertEqual(
      gate().evaluate(
        candidate: candidate(expiresAt: midday.addingTimeInterval(60)),
        configuration: configuration(),
        environment: environment(now: midday, calendar: calendar)
      ).reason,
      .allowed
    )
  }

  func testInterruptionGateEnforcesDedupeSpacingAndDailyBudget() {
    let persistence = MemoryTaskInterruptionLedger()
    let gate = ProactiveTaskInterruptionGate(persistence: persistence)
    let config = configuration(dailyLimit: 2, spacing: 90 * 60)

    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "one", dedupe: "one"),
      configuration: config,
      environment: environment()
    ).reason, .allowed)
    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "repeat", dedupe: "one"),
      configuration: config,
      environment: environment(now: baseDate.addingTimeInterval(90 * 60))
    ).reason, .duplicate)
    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "two", dedupe: "two"),
      configuration: config,
      environment: environment(now: baseDate.addingTimeInterval(60))
    ).reason, .minimumSpacing)
    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "two", dedupe: "two"),
      configuration: config,
      environment: environment(now: baseDate.addingTimeInterval(90 * 60))
    ).reason, .allowed)
    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "three", dedupe: "three"),
      configuration: config,
      environment: environment(now: baseDate.addingTimeInterval(3 * 60 * 60))
    ).reason, .dailyBudget)
  }

  func testDailyBudgetResetsAtLocalDayBoundaryButSpacingDoesNot() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let beforeMidnight = ISO8601DateFormatter().date(from: "2027-01-15T23:59:00Z")!
    let afterMidnight = ISO8601DateFormatter().date(from: "2027-01-16T00:01:00Z")!
    let persistence = MemoryTaskInterruptionLedger()
    let gate = ProactiveTaskInterruptionGate(persistence: persistence)
    let config = configuration(dailyLimit: 1, spacing: 90 * 60)

    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "before", dedupe: "before", expiresAt: beforeMidnight.addingTimeInterval(300)),
      configuration: config,
      environment: environment(now: beforeMidnight, calendar: calendar)
    ).reason, .allowed)
    XCTAssertEqual(gate.evaluate(
      candidate: candidate(id: "after", dedupe: "after", expiresAt: afterMidnight.addingTimeInterval(300)),
      configuration: config,
      environment: environment(now: afterMidnight, calendar: calendar)
    ).reason, .minimumSpacing)
  }

  func testDogfoodAndShippedEnrollmentRemainIndependent() {
    let dogfood = configuration(enabled: true, shipped: false)
    XCTAssertTrue(dogfood.isEnrolled(cohort: .dogfood))
    XCTAssertFalse(dogfood.isEnrolled(cohort: .beta))
    XCTAssertFalse(dogfood.isEnrolled(cohort: .production))

    let shipped = configuration(enabled: true, shipped: true)
    XCTAssertTrue(shipped.isEnrolled(cohort: .dogfood))
    XCTAssertTrue(shipped.isEnrolled(cohort: .beta))
    XCTAssertTrue(shipped.isEnrolled(cohort: .production))
    XCTAssertFalse(configuration(enabled: false, shipped: true).isEnrolled(cohort: .production))
  }

  @MainActor
  func testArtifactPreparationRequiresPolicyGrantAndDelegatesVersioningToKernel() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("task-preparation-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    var persistedVersions = 0
    let bridge = KernelPreparedArtifactBridge(root: root) {
      workstreamID, logicalKey, kind, fileURL, contentHash, evidenceRefs, grantID in
      persistedVersions += 1
      let artifactID = "kernel-artifact-\(persistedVersions)"
      XCTAssertEqual(grantID, "grant-1")
      return TaskKernelPreparedArtifactReceipt(
        artifactVersion: TaskKernelArtifactVersion(
          sourceArtifactId: "source-\(persistedVersions)",
          logicalKey: logicalKey,
          version: persistedVersions,
          supersedesArtifactId: persistedVersions == 1 ? nil : "kernel-artifact-\(persistedVersions - 1)",
          evidenceRefs: evidenceRefs,
          artifact: TaskKernelArtifactVersion.Artifact(
            artifactId: artifactID,
            kind: kind,
            uri: fileURL.absoluteString,
            contentHash: contentHash
          )
        ),
        deliveries: []
      )
    }
    let evidence = OmiAPI.EvidenceRef(
      deviceId: "device-1",
      excerptHash: "sha256:\(String(repeating: "a", count: 64))",
      id: "local-evidence-1",
      kind: .local_screen,
      scope: .device_local,
      version: "test.v1"
    )
    let firstProposal = ProactiveTaskArtifactProposal(
      workstreamID: "workstream-1",
      logicalKey: "investor-email-sarah",
      kind: "email_draft",
      content: Data("Version one".utf8),
      evidenceRefs: [evidence],
      executionReady: true,
      coordinatorGrantID: "grant-1"
    )
    let denied = try await bridge.prepare(firstProposal, configuration: .safeDefault)
    XCTAssertNil(denied)
    XCTAssertEqual(persistedVersions, 0)

    var allowed = configuration()
    allowed.allowedPreparationKinds = ["email_draft"]
    let missingGrant = ProactiveTaskArtifactProposal(
      workstreamID: "workstream-1",
      logicalKey: "investor-email-sarah",
      kind: "email_draft",
      content: Data("Version one".utf8),
      evidenceRefs: [evidence],
      executionReady: true,
      coordinatorGrantID: nil
    )
    XCTAssertEqual(
      ProactiveTaskPreparationPolicy.denial(proposal: missingGrant, configuration: allowed),
      .missingCoordinatorGrant
    )
    let firstResult = try await bridge.prepare(firstProposal, configuration: allowed)
    let first = try XCTUnwrap(firstResult)
    let secondResult = try await bridge.prepare(
      ProactiveTaskArtifactProposal(
        workstreamID: "workstream-1",
        logicalKey: "investor-email-sarah",
        kind: "email_draft",
        content: Data("Version two after new evidence".utf8),
        evidenceRefs: [evidence],
        executionReady: true,
        coordinatorGrantID: "grant-1"
      ),
      configuration: allowed
    )
    let second = try XCTUnwrap(secondResult)

    XCTAssertEqual(first.version, 1)
    XCTAssertEqual(second.version, 2)
    XCTAssertEqual(second.supersedesArtifactID, "kernel-artifact-1")
    XCTAssertEqual(try String(contentsOf: first.fileURL), "Version one")
    XCTAssertEqual(try String(contentsOf: second.fileURL), "Version two after new evidence")
    XCTAssertNotEqual(first.contentHash, second.contentHash)
    XCTAssertFalse(first.fileURL.lastPathComponent.contains("v1"))
    XCTAssertEqual(persistedVersions, 2)
  }

  @MainActor
  func testPreparedArtifactContinuityUsesKernelSessionVersionAndDeliveryRPC() async throws {
    let fileURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("prepared-kernel-\(UUID().uuidString).artifact")
    try Data("draft".utf8).write(to: fileURL)
    defer { try? FileManager.default.removeItem(at: fileURL) }
    let evidence = OmiAPI.EvidenceRef(
      deviceId: "device-1",
      excerptHash: "sha256:\(String(repeating: "b", count: 64))",
      id: "local-evidence-1",
      kind: .local_screen,
      scope: .device_local,
      version: "test.v1"
    )
    var capturedName = ""
    var capturedInput: [String: Any] = [:]
    let receipt = try await TaskWorkstreamContinuity.persistPreparedArtifact(
      workstreamId: "workstream-1",
      logicalKey: "investor-email",
      kind: "email_draft",
      fileURL: fileURL,
      contentHash: "sha256:\(String(repeating: "c", count: 64))",
      evidenceRefs: [evidence],
      grantId: "grant-1"
    ) { name, input in
      capturedName = name
      capturedInput = input
      let response: [String: Any] = [
        "ok": true,
        "artifactVersion": [
          "sourceArtifactId": "source-1",
          "logicalKey": "investor-email",
          "version": 2,
          "supersedesArtifactId": "artifact-1",
          "evidenceRefs": [[
            "device_id": "device-1",
            "excerpt_hash": "sha256:\(String(repeating: "b", count: 64))",
            "id": "local-evidence-1",
            "kind": "local_screen",
            "scope": "device_local",
            "version": "test.v1",
          ]],
          "artifact": [
            "artifactId": "artifact-2",
            "kind": "email_draft",
            "uri": fileURL.absoluteString,
            "contentHash": "sha256:\(String(repeating: "c", count: 64))",
          ],
        ],
        "deliveries": [],
      ]
      let data = try JSONSerialization.data(withJSONObject: response)
      return try XCTUnwrap(String(data: data, encoding: .utf8))
    }

    XCTAssertEqual(capturedName, "persist_prepared_workstream_artifact")
    XCTAssertEqual(capturedInput["workstreamId"] as? String, "workstream-1")
    XCTAssertEqual(capturedInput["logicalKey"] as? String, "investor-email")
    XCTAssertEqual(capturedInput["grantId"] as? String, "grant-1")
    XCTAssertNil(capturedInput["context"])
    XCTAssertEqual(receipt.artifactVersion.version, 2)
  }

  func testGateTraceAndNormalizedEventContainNoRawPrivateContent() throws {
    let raw = "Sarah private launch document"
    let event = try XCTUnwrap(TaskLocalContextEvent.normalized(kind: .document, rawReference: raw))
    XCTAssertFalse(event.referenceHash.localizedCaseInsensitiveContains("sarah"))
    XCTAssertFalse(Mirror(reflecting: event).children.compactMap(\.label).contains("rawReference"))

    let trace = gate().evaluate(
      candidate: candidate(headline: raw, dedupe: "secret-dedupe-value"),
      configuration: configuration(),
      environment: environment()
    )
    let encoded = String(data: try JSONEncoder().encode(trace), encoding: .utf8)!
    XCTAssertFalse(encoded.contains(raw))
    XCTAssertFalse(encoded.contains("secret-dedupe-value"))
    XCTAssertTrue(encoded.contains("sha256:"))
  }

  func testLegacyPromotionCannotNotifyOrBypassTheCanonicalGate() throws {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let source = try String(contentsOf: testsDirectory.deletingLastPathComponent()
      .appendingPathComponent("Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskPromotionService.swift"))
    XCTAssertFalse(source.contains("New task"))
    XCTAssertFalse(source.contains("sendNotification"))
    XCTAssertFalse(source.contains("respectFrequency: false"))
  }

  private func eligibility(
    hasEvidence: Bool = true,
    hasConcreteAction: Bool = true,
    dedupeAlreadyActive: Bool = false,
    expiresAt: Date? = nil
  ) -> TaskRecommendationEligibilityDenial? {
    TaskRecommendationEligibility.denial(
      for: TaskRecommendationEligibilityInput(
        isOpen: true,
        expiresAt: expiresAt ?? baseDate.addingTimeInterval(60),
        hasEvidence: hasEvidence,
        hasConcreteAction: hasConcreteAction,
        dedupeAlreadyActive: dedupeAlreadyActive
      ),
      now: baseDate
    )
  }

  private func gate() -> ProactiveTaskInterruptionGate {
    ProactiveTaskInterruptionGate(persistence: MemoryTaskInterruptionLedger())
  }

  private func candidate(
    id: String = "recommendation-1",
    headline: String = "Review the updated draft",
    dedupe: String = "dedupe-1",
    expiresAt: Date? = nil,
    canWait: Bool = false
  ) -> TaskInterruptionCandidate {
    TaskInterruptionCandidate(
      recommendationID: id,
      interventionID: "intervention-1",
      dedupeKey: dedupe,
      headline: headline,
      whyNow: "The linked conversation changed the assumptions.",
      recommendedAction: "Review update",
      expiresAt: expiresAt ?? baseDate.addingTimeInterval(24 * 60 * 60),
      canWait: canWait
    )
  }

  private func configuration(
    enabled: Bool = true,
    shipped: Bool = false,
    dailyLimit: Int = 2,
    spacing: TimeInterval = 90 * 60,
    quiet: Bool = false
  ) -> ProactiveTaskInterruptionConfiguration {
    ProactiveTaskInterruptionConfiguration(
      userOptedIn: enabled,
      shippedCohortsEnabled: shipped,
      dailyLimit: dailyLimit,
      minimumSpacing: spacing,
      quietHoursStartMinute: quiet ? 22 * 60 : 0,
      quietHoursEndMinute: quiet ? 8 * 60 : 0,
      allowedPreparationKinds: []
    )
  }

  private func environment(
    cohort: ProactiveTaskCohort = .dogfood,
    master: Bool = true,
    frequency: Bool = true,
    ambientFrequency: Bool = true,
    task: Bool = true,
    focus: Bool = false,
    snoozed: Bool = false,
    now: Date? = nil,
    calendar: Calendar = Calendar(identifier: .gregorian)
  ) -> TaskInterruptionEnvironment {
    TaskInterruptionEnvironment(
      cohort: cohort,
      masterNotificationsEnabled: master,
      frequencyEnabled: frequency,
      ambientFrequencyEligible: ambientFrequency,
      taskNotificationsEnabled: task,
      focusSuppressed: focus,
      snoozed: snoozed,
      now: now ?? baseDate,
      calendar: calendar
    )
  }
}
