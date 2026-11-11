import GRDB
import XCTest

@testable import Omi_Computer

/// Regression coverage for the canonical capture outbox 422 wedge.
///
/// The extraction model is asked for a canonical task id in
/// `duplicate_of`/`refines_task` but sometimes echoes the referenced task's
/// *title*. The adapter forwarded that string verbatim as `task_id`, the
/// backend's StableId pattern (`^[A-Za-z0-9][A-Za-z0-9._:-]*$`) rejected it
/// with HTTP 422, and the outbox drain retried the identical payload forever —
/// six permanently rejected rows produced a burst of six 422s on every drain.
/// These tests pin both halves of the fix: non-conforming task references are
/// treated as absent, and validation-class rejections poison the row after a
/// bounded number of attempts instead of retrying indefinitely.
final class CandidateOutboxValidationPoisonTests: XCTestCase {

  // MARK: - Task reference sanitization

  func testCanonicalTaskReferenceRejectsTaskTitles() {
    // Real values observed wedged in a field outbox: titles, not ids.
    XCTAssertNil(
      ScreenCandidateAdapter.canonicalTaskReference(
        "Fix Omi Windows app time context issue for Schlemosel"))
    XCTAssertNil(
      ScreenCandidateAdapter.canonicalTaskReference(
        "Help Aida implement Apple login option on Omi Windows app"))
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference("Review Omi PR #11580"))
  }

  func testCanonicalTaskReferenceAcceptsStableIds() {
    XCTAssertEqual(ScreenCandidateAdapter.canonicalTaskReference("task-budget"), "task-budget")
    XCTAssertEqual(
      ScreenCandidateAdapter.canonicalTaskReference("cand_f5777d77f4c68185543a9f12d444af6a"),
      "cand_f5777d77f4c68185543a9f12d444af6a")
    XCTAssertEqual(ScreenCandidateAdapter.canonicalTaskReference("screen:dev:42"), "screen:dev:42")
    XCTAssertEqual(ScreenCandidateAdapter.canonicalTaskReference("a.b-c_d:e"), "a.b-c_d:e")
  }

  func testCanonicalTaskReferenceEnforcesStableIdShape() {
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference(nil))
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference(""))
    // First character must be alphanumeric.
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference("-task"))
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference(".hidden"))
    // Non-ASCII and whitespace are outside the backend pattern.
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference("tâche-1"))
    XCTAssertNil(ScreenCandidateAdapter.canonicalTaskReference("task 1"))
    // Backend StableId caps at 128 characters.
    XCTAssertNil(
      ScreenCandidateAdapter.canonicalTaskReference(String(repeating: "a", count: 129)))
    XCTAssertNotNil(
      ScreenCandidateAdapter.canonicalTaskReference(String(repeating: "a", count: 128)))
  }

  // MARK: - Adapter behavior with unusable references

  private func makeTask(
    captureKind: String,
    alreadyDone: Bool = false,
    duplicateOf: String? = nil,
    refinesTask: String? = nil
  ) -> ExtractedTask {
    ExtractedTask(
      title: "Fix Omi Windows app time context issue for Schlemosel",
      description: nil,
      priority: .high,
      sourceApp: "Telegram",
      inferredDeadline: nil,
      confidence: 0.9,
      tags: [],
      sourceCategory: "direct_request",
      sourceSubcategory: "commitment",
      captureKind: captureKind,
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: alreadyDone,
      duplicateOf: duplicateOf,
      refinesTask: refinesTask,
      ownershipConfidence: 0.95
    )
  }

  func testCompletionAgainstTitleReferenceProducesNoCandidate() throws {
    // already_done + a title-valued refines_task used to build a
    // TaskCompleteCandidate whose task_id could never validate (HTTP 422).
    // With the reference treated as absent there is no completion target, so
    // the adapter must return no candidate; the outbox drain then discards the
    // row instead of retrying a doomed payload.
    let decision = ScreenCandidateAdapter.adapt(
      task: makeTask(
        captureKind: "already_done",
        alreadyDone: true,
        refinesTask: "Fix Omi Windows app time context issue for Schlemosel"),
      dueAt: nil,
      localEvidenceID: "screen-2391",
      deviceID: "macos_device"
    )
    XCTAssertEqual(decision.outcome, .proposeCompletion)
    XCTAssertNil(decision.candidate)
  }

  func testDuplicateWithTitleReferenceFallsBackToCreateCandidate() throws {
    // A duplicate_of that is not a StableId cannot target an update; the
    // capture must fall back to the create policy instead of emitting a
    // TaskUpdateCandidate the backend deterministically rejects.
    let decision = ScreenCandidateAdapter.adapt(
      task: makeTask(
        captureKind: "direct_request",
        duplicateOf: "Help Aida implement Apple login option on Omi Windows app"),
      dueAt: nil,
      localEvidenceID: "screen-2389",
      deviceID: "macos_device"
    )
    guard case .taskCreate = try XCTUnwrap(decision.candidate) else {
      return XCTFail("Unusable duplicate reference must fall back to a create Candidate")
    }
  }

  func testValidDuplicateReferenceStillProposesEnrichment() throws {
    // Sanitization must not swallow genuine StableId references.
    let decision = ScreenCandidateAdapter.adapt(
      task: makeTask(captureKind: "direct_request", duplicateOf: "task-existing-42"),
      dueAt: nil,
      localEvidenceID: "screen-7",
      deviceID: "macos_device"
    )
    XCTAssertEqual(decision.outcome, .proposeEnrichment)
    guard case .taskUpdate(let candidate) = try XCTUnwrap(decision.candidate) else {
      return XCTFail("A valid duplicate reference must still propose an update Candidate")
    }
    XCTAssertEqual(candidate.taskId, "task-existing-42")
  }

  // MARK: - Retry classification

  func testValidationRejectionsArePermanent() {
    XCTAssertTrue(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 422)))
    XCTAssertTrue(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 400)))
  }

  func testTransientFailuresRemainRetryable() {
    XCTAssertFalse(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 401)))
    XCTAssertFalse(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 409)))
    XCTAssertFalse(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 429)))
    XCTAssertFalse(
      CandidateOutboxRetryPolicy.isPermanentRejection(APIError.httpError(statusCode: 500)))
    XCTAssertFalse(
      CandidateOutboxRetryPolicy.isPermanentRejection(URLError(.notConnectedToInternet)))
    XCTAssertFalse(CandidateOutboxRetryPolicy.isPermanentRejection(APIError.invalidResponse))
  }
}

/// Storage-level poisoning contract: a bounded number of permanent rejections
/// removes the row from the retry drain without erasing the evidence.
final class CanonicalOutboxRejectionStorageTests: XCTestCase {
  private var testUserId = ""
  private var userDir: URL?

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "outbox-poison-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await StagedTaskStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = try XCTUnwrap(
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first)
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await StagedTaskStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    try await super.tearDown()
  }

  private func insertOutboxRow() async throws -> Int64 {
    let record = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(
        backendSynced: false,
        description: "Fix Omi Windows app time context issue for Schlemosel",
        source: "candidate_outbox",
        createdAt: Date(),
        updatedAt: Date()))
    return try XCTUnwrap(record.id)
  }

  func testRejectionCountPersistsAndRowStaysRetryableBelowLimit() async throws {
    let id = try await insertOutboxRow()

    let first = try await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: id)
    XCTAssertEqual(first, .willRetry(rejections: 1))
    let second = try await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: id)
    XCTAssertEqual(second, .willRetry(rejections: 2))

    let pending = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(
      pending.contains { $0.id == id },
      "Below the poison limit the row must remain in the retry drain")

    // The count is durable (metadata), so attempts survive an app restart.
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }
    let record = try await dbQueue.read { try StagedTaskRecord.fetchOne($0, key: id) }
    XCTAssertEqual(record?.metadata?["outbox_permanent_rejections"] as? Int, 2)
  }

  func testThirdValidationRejectionPoisonsRowOutOfRetryDrain() async throws {
    let id = try await insertOutboxRow()

    _ = try await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: id)
    _ = try await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: id)
    let third = try await StagedTaskStorage.shared.recordCanonicalOutboxRejection(id: id)
    XCTAssertEqual(third, .poisoned(rejections: 3))

    let pending = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertFalse(
      pending.contains { $0.id == id },
      "A poisoned row must never re-enter the retry drain")

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }
    let record = try await dbQueue.read { try StagedTaskRecord.fetchOne($0, key: id) }
    XCTAssertEqual(record?.deleted, true)
    XCTAssertEqual(record?.metadata?["outbox_poisoned"] as? Bool, true)
    XCTAssertEqual(record?.metadata?["outbox_permanent_rejections"] as? Int, 3)
  }
}
