import Foundation
import XCTest

@testable import Omi_Computer

final class SiriIntentServiceTests: XCTestCase {
  func testOpenTaskRechecksTheCurrentIndexedScope() {
    let now = Date()
    var task = ActionItemRecord(backendId: "open-task", backendSynced: true, description: "Task")
    XCTAssertTrue(SiriNavigator.taskIsOpenable(task, now: now))
    task.taskStatus = "cancelled"
    XCTAssertFalse(SiriNavigator.taskIsOpenable(task, now: now))
    task.taskStatus = "active"
    task.completed = true
    task.completedAt = now.addingTimeInterval(-SiriIndexScope.completedTaskAge - 1)
    XCTAssertFalse(SiriNavigator.taskIsOpenable(task, now: now))
    task.completed = false
    task.isLocked = true
    XCTAssertFalse(SiriNavigator.taskIsOpenable(task, now: now))
  }
  func testSpotlightIndexingStartsAtMacOS27() {
    guard #available(macOS 15.4, *) else { return }
    XCTAssertFalse(
      SiriIndexer.supportsSpotlightIndexing(
        OperatingSystemVersion(majorVersion: 15, minorVersion: 4, patchVersion: 0)))
    XCTAssertFalse(
      SiriIndexer.supportsSpotlightIndexing(
        OperatingSystemVersion(majorVersion: 26, minorVersion: 6, patchVersion: 0)))
    XCTAssertTrue(
      SiriIndexer.supportsSpotlightIndexing(
        OperatingSystemVersion(majorVersion: 27, minorVersion: 0, patchVersion: 0)))
  }

  func testSpotlightIndexIsIsolatedByBundleAndOwner() {
    guard #available(macOS 15.4, *) else { return }
    let production = SiriIndexer.indexName(bundleID: "com.omi.desktop", owner: "same-user")
    let beta = SiriIndexer.indexName(bundleID: "com.omi.desktop.beta", owner: "same-user")
    let named = SiriIndexer.indexName(bundleID: "com.omi.desktop.dev.siri-probe", owner: "same-user")
    XCTAssertEqual(Set([production, beta, named]).count, 3)
    XCTAssertNotEqual(production, SiriIndexer.indexName(bundleID: "com.omi.desktop", owner: "other-user"))
  }

  func testSyncIndexChangesAreBoundedAndSerializedPerAccount() async {
    actor Calls {
      var sizes: [Int] = []
      var inFlight = 0
      var peak = 0
      func run(_ ids: [String]) async {
        inFlight += 1
        peak = max(peak, inFlight)
        sizes.append(ids.count)
        await Task.yield()
        inFlight -= 1
      }
      func result() -> ([Int], Int) { (sizes, peak) }
    }
    let calls = Calls()
    let batcher = SiriIndexBatcher { _, _, ids in await calls.run(ids) }
    await batcher.enqueue(owner: "owner-a", kind: .memory, ids: (0..<1_000).map(String.init))
    await batcher.waitUntilIdle(owner: "owner-a")
    let (sizes, peak) = await calls.result()
    XCTAssertEqual(sizes.reduce(0, +), 1_000)
    XCTAssertLessThanOrEqual(sizes.count, 5)
    XCTAssertTrue(sizes.allSatisfy { $0 <= 200 })
    XCTAssertEqual(peak, 1)
  }

  private enum BackendStub: CaseIterable, Sendable {
    case auth, network, quota, rateLimited, server

    var failure: SiriFailure {
      switch self {
      case .auth: .auth
      case .network: .network
      case .quota: .quota
      case .rateLimited: .rateLimited
      case .server: .server
      }
    }

    var error: Error {
      switch self {
      case .auth: APIError.unauthorized
      case .network: URLError(.notConnectedToInternet)
      case .quota: APIError.httpError(statusCode: 402)
      case .rateLimited: APIError.httpError(statusCode: 429)
      case .server: APIError.httpError(statusCode: 503)
      }
    }

    func spokenMessage(for action: String) -> String {
      switch self {
      case .auth: "Open Omi and sign in first."
      case .network:
        action == "complete"
          ? "I couldn't reach Omi, so the task wasn't changed."
          : "I couldn't reach Omi, so nothing was saved."
      case .quota:
        action == "complete"
          ? "Your Omi limit has been reached, so the task wasn't changed."
          : "Your Omi limit has been reached, so nothing was saved."
      case .rateLimited: "Omi is receiving too many requests. Try again shortly."
      case .server:
        action == "complete"
          ? "Omi couldn't change the task right now."
          : "Omi couldn't save that right now."
      }
    }
  }

  private actor DeletionProbe {
    var deletedID: String?
    var deletedIDs: [String] = []
    func delete(_ id: String) { deletedID = id }
    func delete(_ ids: [String]) { deletedIDs = ids }
  }

  func testMemoryInputIsTrimmedWithoutRewritingItsWords() {
    XCTAssertEqual(SiriIntentService.normalizedMemory("  that I like fried rice  "), "I like fried rice")
    XCTAssertEqual(SiriIntentService.normalizedMemory("That Sam promised a call"), "Sam promised a call")
    XCTAssertEqual(SiriIntentService.normalizedMemory("that\twe should meet"), "that\twe should meet")
  }

  func testClassicShortcutsUseTheCorrectExecutionProcess() {
    XCTAssertFalse(RememberIntent.openAppWhenRun)
    XCTAssertTrue(StartListeningIntent.openAppWhenRun)
    XCTAssertTrue(StopListeningIntent.openAppWhenRun)
    XCTAssertEqual(OmiAppShortcuts.appShortcuts.count, 3)
  }

  func testBackendFailuresHaveTypedSpokenOutcomes() {
    let cases: [(Error, SiriFailure, String)] = [
      (APIError.unauthorized, .auth, "Open Omi and sign in first."),
      (APIError.httpError(statusCode: 402), .quota, "Your Omi limit has been reached, so nothing was saved."),
      (APIError.httpError(statusCode: 429), .rateLimited, "Omi is receiving too many requests. Try again shortly."),
      (APIError.httpError(statusCode: 503), .server, "Omi couldn't save that right now."),
      (APIError.invalidResponse, .server, "Omi couldn't save that right now."),
      (URLError(.notConnectedToInternet), .network, "I couldn't reach Omi, so nothing was saved."),
      (CancellationError(), .cancelled, "The action was cancelled."),
    ]
    for (error, expected, message) in cases {
      let result = SiriFailure.classify(error)
      XCTAssertEqual(result, expected)
      XCTAssertEqual(result.message(for: "remember"), message)
    }
    XCTAssertEqual(SiriFailure.network.message(for: "complete"), "I couldn't reach Omi, so the task wasn't changed.")
  }

  func testEmptyMemoryNeverAttemptsBackendWrite() async {
    do {
      _ = try await SiriIntentService.remember(
        "   ",
        create: { _ in
          throw APIError.invalidResponse
        })
      XCTFail("Empty memory must fail")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error, SiriActionFailure(action: "remember", failure: .unsupported))
    } catch {
      XCTFail("Unexpected failure: \(error)")
    }
  }

  func testRememberWriterFailureNeverClaimsSuccess() async {
    do {
      _ = try await SiriIntentService.remember(
        "that I like fried rice",
        create: { _ in
          throw APIError.httpError(statusCode: 503)
        })
      XCTFail("Failed write must throw")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error.action, "remember")
      XCTAssertEqual(error.failure, .server)
      XCTAssertEqual(error.errorDescription, "Omi couldn't save that right now.")
    } catch {
      XCTFail("Unexpected failure: \(error)")
    }
  }

  func testRememberIntentPerformPreservesActionSpecificBackendFailure() async {
    let intent = RememberIntent()
    intent.text = "that a meeting starts at nine"
    do {
      _ = try await SiriIntentService.$memoryWriter.withValue({ _ in
        throw APIError.httpError(statusCode: 503)
      }) {
        try await intent.perform()
      }
      XCTFail("Failed write must not return an intent success")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error, SiriActionFailure(action: "remember", failure: .server))
      XCTAssertEqual(error.errorDescription, "Omi couldn't save that right now.")
    } catch {
      XCTFail("Unexpected failure: \(error)")
    }
  }

  @available(macOS 15.4, *)
  func testMemoryEntityProjectsPersistedContentAndExpiry() {
    let expiry = Date(timeIntervalSince1970: 2_000_000_000)
    let record = MemoryRecord(
      backendId: "memory-synthetic", content: "A long synthetic memory for indexing",
      expiresAt: expiry)
    XCTAssertEqual(record.toServerMemory()?.expiresAt, expiry)
    let entity = MemoryEntity(record)
    XCTAssertEqual(entity.id, "memory-synthetic")
    XCTAssertEqual(entity.content, record.content)
    XCTAssertEqual(entity.name, record.content)
    XCTAssertEqual(entity.eligibilityCutoff, expiry)
  }

  func testLegacyNullLockStateKeepsExistingAppDisplaySemantics() {
    let memory = MemoryRecord(backendId: "legacy-memory", content: "Visible legacy memory", isLocked: nil)
    XCTAssertEqual(memory.toServerMemory()?.isLocked, false)
    let task = ActionItemRecord(backendId: "legacy-task", description: "Visible legacy task", isLocked: nil)
    XCTAssertEqual(task.toTaskActionItem().isLocked, false)
    let conversation = TranscriptionSessionRecord(
      startedAt: Date(), source: "desktop", backendId: "legacy-conversation",
      backendSynced: true, visibility: nil)
    XCTAssertEqual(conversation.toServerConversation(segments: [])?.visibility, "private")
  }

  @available(macOS 27, *)
  func testConversationAndTaskEntitiesProjectPersistedRows() {
    let started = Date(timeIntervalSince1970: 2_000_000_000)
    let conversation = TranscriptionSessionRecord(
      startedAt: started, source: "desktop", backendId: "conversation-synthetic",
      backendSynced: true, title: "Synthetic conversation", overview: "A synthetic overview",
      conversationStatus: .completed)
    let note = ConversationEntity(conversation)
    XCTAssertEqual(note.id, "conversation-synthetic")
    XCTAssertEqual(String(note.name.characters), "Synthetic conversation")
    XCTAssertEqual(note.content.map { String($0.characters) }, "A synthetic overview")
    XCTAssertEqual(note.creationDate, started)
    XCTAssertEqual(note.folder?.id, OmiFolderEntity.conversations.id)

    let completed = started.addingTimeInterval(3_600)
    let task = ActionItemRecord(
      backendId: "task-synthetic", backendSynced: true, description: "Synthetic task",
      completed: true, dueAt: started, completedAt: completed)
    let reminder = TaskEntity(task)
    XCTAssertEqual(reminder.id, "task-synthetic")
    XCTAssertEqual(reminder.title, "Synthetic task")
    XCTAssertTrue(reminder.isCompleted)
    XCTAssertEqual(reminder.dueDate?.year, Calendar.current.component(.year, from: started))
    XCTAssertEqual(reminder.completionDate, completed)
    XCTAssertEqual(reminder.list.id, OmiListEntity.omi.id)
  }

  func testIndexScopeExpiresMemoriesAndBoundsConversationsAndMemories() {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: "archived", deleted: false, dismissed: false,
        tier: MemoryLayer.archive.rawValue, expiresAt: nil, now: now))
    XCTAssertTrue(
      SiriIndexScope.memory(
        backendId: "m", deleted: false, dismissed: false, tier: MemoryLayer.longTerm.rawValue,
        expiresAt: now.addingTimeInterval(1), now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: "m", deleted: false, dismissed: false, tier: MemoryLayer.longTerm.rawValue,
        expiresAt: now, now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: nil, deleted: false, dismissed: false, tier: MemoryLayer.longTerm.rawValue,
        expiresAt: nil, now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: "m", deleted: true, dismissed: false, tier: MemoryLayer.longTerm.rawValue,
        expiresAt: nil, now: now))
    XCTAssertEqual(
      SiriIndexScope.capped(
        Array(0...SiriIndexScope.conversationLimit),
        at: SiriIndexScope.conversationLimit
      ).count, 2_000)
    XCTAssertEqual(
      SiriIndexScope.capped(
        Array(0...SiriIndexScope.memoryLimit),
        at: SiriIndexScope.memoryLimit
      ).count, 5_000)
  }

  func testIndexScopeKeepsOpenAndOnlyRecentCompletedTasks() {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    let cutoff = now.addingTimeInterval(-SiriIndexScope.completedTaskAge)
    XCTAssertTrue(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: false,
        completedAt: nil, now: now))
    XCTAssertFalse(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: true,
        completedAt: cutoff, now: now))
    XCTAssertTrue(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: true,
        completedAt: cutoff.addingTimeInterval(1), now: now))
    XCTAssertFalse(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: true,
        completedAt: cutoff.addingTimeInterval(-1), now: now))
    XCTAssertFalse(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: true,
        completedAt: nil, now: now))
    XCTAssertFalse(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: false,
        completedAt: nil, taskStatus: "cancelled", now: now))
    XCTAssertFalse(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: false,
        completedAt: nil, taskStatus: "superseded", now: now))
  }

  func testSiriEligibilityDecisionTable() {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    let baseConversation = TranscriptionSessionRecord(
      startedAt: now.addingTimeInterval(-100), source: "desktop", backendId: "conversation",
      backendSynced: true, conversationStatus: .completed)
    let conversationCases: [(String, (inout TranscriptionSessionRecord) -> Void, Bool)] = [
      ("eligible", { _ in }, true),
      ("empty id", { $0.backendId = "" }, false),
      ("unsynced", { $0.backendSynced = false }, false),
      ("deleted", { $0.deleted = true }, false),
      ("discarded", { $0.discarded = true }, false),
      ("processing", { $0.conversationStatus = .processing }, false),
      ("locked", { $0.isLocked = true }, false),
      ("hidden", { $0.visibility = "hidden" }, false),
      ("omitted visibility", { $0.visibility = nil }, true),
      ("aged", { $0.startedAt = now.addingTimeInterval(-SiriIndexScope.conversationAge - 1) }, false),
    ]
    for (name, change, expected) in conversationCases {
      var row = baseConversation
      change(&row)
      XCTAssertEqual(SiriIndexScope.conversation(row, now: now), expected, name)
    }

    let baseMemory = MemoryRecord(
      backendId: "memory", backendSynced: true, content: "Visible", tierIsExplicit: true)
    let memoryCases: [(String, (inout MemoryRecord) -> Void, Bool)] = [
      ("eligible", { _ in }, true),
      ("empty id", { $0.backendId = "" }, false),
      ("deleted", { $0.deleted = true }, false),
      ("archived", { $0.tier = MemoryLayer.archive.rawValue }, false),
      ("legacy omitted tier", { $0.tierIsExplicit = false }, true),
      ("short term", { $0.tier = MemoryLayer.shortTerm.rawValue }, true),
      ("long term", { $0.tier = MemoryLayer.longTerm.rawValue }, true),
      ("unknown tier", { $0.tier = "future_tier" }, false),
      ("expired", { $0.expiresAt = now.addingTimeInterval(-1) }, false),
      ("rejected", { $0.userReview = false }, false),
      ("dismissed", { $0.isDismissed = true }, false),
      ("hidden", { $0.visibility = "hidden" }, false),
      ("locked", { $0.isLocked = true }, false),
      ("omitted lock state", { $0.isLocked = nil }, true),
      ("ledger closed", { $0.ledgerMetadataJson = "{\"status\":\"superseded\"}" }, false),
      ("ledger superseded", { $0.ledgerMetadataJson = "{\"superseded_by\":\"new-memory\"}" }, false),
      ("ledger invalidated", { $0.ledgerMetadataJson = "{\"invalid_at\":\"2000-01-01T00:00:00Z\"}" }, false),
    ]
    for (name, change, expected) in memoryCases {
      var row = baseMemory
      change(&row)
      XCTAssertEqual(SiriIndexScope.memory(row, now: now), expected, name)
    }

    let baseTask = ActionItemRecord(backendId: "task", backendSynced: true, description: "Visible")
    let taskCases: [(String, (inout ActionItemRecord) -> Void, Bool)] = [
      ("eligible", { _ in }, true),
      ("empty id", { $0.backendId = "" }, false),
      ("deleted", { $0.deleted = true }, false),
      ("cancelled", { $0.taskStatus = "cancelled" }, false),
      ("unknown status", { $0.taskStatus = "processing" }, false),
      ("superseded", { $0.supersededBy = "replacement" }, false),
      ("locked", { $0.isLocked = true }, false),
      ("omitted lock state", { $0.isLocked = nil }, true),
      (
        "old completion",
        {
          $0.completed = true
          $0.completedAt = now.addingTimeInterval(-SiriIndexScope.completedTaskAge - 1)
        }, false
      ),
    ]
    for (name, change, expected) in taskCases {
      var row = baseTask
      change(&row)
      XCTAssertEqual(SiriIndexScope.task(row, now: now), expected, name)
    }
  }

  func testMemoryInvalidationSchedulesSpotlightRemovalWithoutExpiry() throws {
    guard #available(macOS 15.4, *) else { return }
    let invalidAt = Date(timeIntervalSince1970: 2_000_000_100)
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    let record = MemoryRecord(
      backendId: "future-invalidation", backendSynced: true, content: "Current until invalidation",
      tierIsExplicit: true, ledgerMetadataJson: "{\"invalid_at\":\"\(formatter.string(from: invalidAt))\"}")
    XCTAssertNil(record.expiresAt)
    XCTAssertEqual(MemoryEntity(record).eligibilityCutoff, invalidAt)
  }

  func testMemoryEarlierCompatibilityExpiryWinsOverLedgerInvalidation() throws {
    guard #available(macOS 15.4, *) else { return }
    let expiry = Date(timeIntervalSince1970: 2_000_000_050)
    let invalidAt = Date(timeIntervalSince1970: 2_000_000_100)
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    let record = MemoryRecord(
      backendId: "compat-expiry", backendSynced: true, content: "Expires first",
      expiresAt: expiry,
      ledgerMetadataJson: "{\"invalid_at\":\"\(formatter.string(from: invalidAt))\"}")
    XCTAssertEqual(MemoryEntity(record).eligibilityCutoff, expiry)
    XCTAssertFalse(SiriIndexScope.memory(record, now: expiry))
  }

  func testConversationCapCountsEligibleRowsOnly() {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    let hidden = (0..<SiriIndexScope.conversationLimit).map { index in
      TranscriptionSessionRecord(
        startedAt: now.addingTimeInterval(TimeInterval(-index)), source: "desktop",
        backendId: "hidden-\(index)", backendSynced: true,
        conversationStatus: .completed, visibility: "hidden")
    }
    let visible = TranscriptionSessionRecord(
      startedAt: now.addingTimeInterval(-2_001), source: "desktop",
      backendId: "eligible-after-cap", backendSynced: true,
      conversationStatus: .completed, visibility: "private")
    let rows = SiriIndexScope.eligibleConversations(hidden + [visible], now: now)
    XCTAssertEqual(rows.map(\.backendId), ["eligible-after-cap"])
  }

  func testSiriTemporalCutoffDecisionTable() {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    let cases: [(String, [Date], Date?)] = [
      ("conversation", [now.addingTimeInterval(2)], now.addingTimeInterval(2)),
      ("completed task", [now.addingTimeInterval(3)], now.addingTimeInterval(3)),
      ("memory", [now.addingTimeInterval(4)], now.addingTimeInterval(4)),
      (
        "earliest of all", [now.addingTimeInterval(4), now.addingTimeInterval(2), now.addingTimeInterval(3)],
        now.addingTimeInterval(2)
      ),
    ]
    for (name, dates, expected) in cases {
      XCTAssertEqual(SiriIndexScope.nextCutoff(dates), expected, name)
    }
  }

  func testListeningFailuresUseListeningDialogs() {
    XCTAssertEqual(SiriFailure.server.message(for: "start_listening"), "Omi couldn't start listening right now.")
    XCTAssertEqual(SiriFailure.server.message(for: "stop_listening"), "Omi couldn't stop listening right now.")
    XCTAssertEqual(SiriFailure.recordingOff.message(for: "start_listening"), "Turn on audio recording in Omi first.")
    XCTAssertEqual(SiriFailure.micDenied.message(for: "start_listening"), "Allow microphone access in Omi first.")
    XCTAssertEqual(SiriFailure.nothingToStop.message(for: "stop_listening"), "Omi isn't listening right now.")
  }

  func testOwnerTransitionWipesOldIndexBeforeAdoptingNewOwner() async {
    let probe = DeletionProbe()
    let owner = try? await SiriIndexOwnerFence.transition(from: "previous", to: "current") { id in
      await probe.delete(id)
    }
    XCTAssertEqual(owner, "current")
    let deletedID = await probe.deletedID
    XCTAssertEqual(deletedID, "previous")

    do {
      _ = try await SiriIndexOwnerFence.transition(from: "previous", to: "current") { _ in
        throw URLError(.notConnectedToInternet)
      }
      XCTFail("A failed wipe must prevent owner adoption")
    } catch {
      XCTAssertTrue(error is URLError)
    }
  }

  func testCompleteTaskNetworkFailureSaysTaskWasNotChanged() async {
    do {
      _ = try await SiriIntentService.completeTask(
        id: "fake-backend-id",
        update: { _ in
          throw URLError(.notConnectedToInternet)
        })
      XCTFail("Failed write must throw")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error.action, "complete")
      XCTAssertEqual(error.failure, .network)
      XCTAssertEqual(error.errorDescription, "I couldn't reach Omi, so the task wasn't changed.")
    } catch {
      XCTFail("Unexpected failure: \(error)")
    }
  }

  func testCreateTaskQuotaFailureSaysNothingWasSaved() async {
    do {
      _ = try await SiriIntentService.createTask(
        title: " Dentist ", dueDate: nil,
        create: { _, _ in
          throw APIError.httpError(statusCode: 402)
        })
      XCTFail("Failed write must throw")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error.action, "create")
      XCTAssertEqual(error.failure, .quota)
      XCTAssertEqual(error.errorDescription, "Your Omi limit has been reached, so nothing was saved.")
    } catch {
      XCTFail("Unexpected failure: \(error)")
    }
  }

  @available(macOS 27, *)
  func testCompleteTaskIntentPerformSpeaksEveryBackendFailure() async {
    for stub in BackendStub.allCases {
      let intent = OmiCompleteTaskIntent()
      intent.target = TaskEntity(donationID: "synthetic-task")
      intent.isCompleted = true
      do {
        _ = try await SiriIntentService.$taskCompletionWriter.withValue({ _ in throw stub.error }) {
          try await intent.perform()
        }
        XCTFail("\(stub) must not complete the task")
      } catch let error as SiriActionFailure {
        XCTAssertEqual(error.failure, stub.failure)
        XCTAssertEqual(error.action, "complete")
        XCTAssertEqual(error.errorDescription, stub.spokenMessage(for: "complete"))
      } catch { XCTFail("Unexpected \(stub) failure: \(error)") }
    }
  }

  @available(macOS 27, *)
  func testCreateTaskIntentPerformSpeaksEveryBackendFailure() async {
    for stub in BackendStub.allCases {
      let intent = OmiCreateTaskIntent()
      intent.title = "Synthetic task"
      do {
        _ = try await SiriIntentService.$taskCreationWriter.withValue({ _, _ in throw stub.error }) {
          try await intent.perform()
        }
        XCTFail("\(stub) must not create a task")
      } catch let error as SiriActionFailure {
        XCTAssertEqual(error.failure, stub.failure)
        XCTAssertEqual(error.action, "create")
        XCTAssertEqual(error.errorDescription, stub.spokenMessage(for: "create"))
      } catch { XCTFail("Unexpected \(stub) failure: \(error)") }
    }
  }

  @available(macOS 27, *)
  func testCreateNoteRejectsOtherFolderBeforeWriting() async {
    let intent = OmiCreateNoteIntent()
    intent.name = "Private text"
    intent.folder = .conversations
    do {
      _ = try await SiriIntentService.$memoryWriter.withValue({ _ in
        XCTFail("A note outside Memories must not be written")
        throw APIError.invalidResponse
      }) { try await intent.perform() }
      XCTFail("The folder must be rejected")
    } catch let error as SiriActionFailure {
      XCTAssertEqual(error.errorDescription, "Omi can only save note text to Memories.")
    } catch { XCTFail("Unexpected error: \(error)") }
  }

  @available(macOS 27, *)
  func testCreateTaskRejectsUnsupportedFieldsBeforeWriting() async {
    let variants: [(inout OmiCreateTaskIntent) -> Void] = [
      { $0.note = AttributedString("Keep this note") },
      { $0.tags = ["urgent"] },
      { $0.isFlagged = true },
      { $0.urls = [URL(string: "https://example.invalid")!] },
    ]
    for mutate in variants {
      var intent = OmiCreateTaskIntent()
      intent.title = "Private task"
      mutate(&intent)
      do {
        _ = try await SiriIntentService.$taskCreationWriter.withValue({ _, _ in
          XCTFail("Unsupported task fields must not be written")
          throw APIError.invalidResponse
        }) { try await intent.perform() }
        XCTFail("Unsupported task field must be rejected")
      } catch let error as SiriActionFailure {
        XCTAssertEqual(error.errorDescription, "Omi can only create tasks with a title, due date, and the Omi list.")
      } catch { XCTFail("Unexpected error: \(error)") }
    }
  }

  func testMemoryDeleteAwaitsSpotlightOperation() async {
    let probe = DeletionProbe()
    let succeeded = await SiriIndexHooks.memoryDeleted(
      "fake-backend-id",
      using: { id in
        await probe.delete(id)
      })
    XCTAssertTrue(succeeded)
    let deletedID = await probe.deletedID
    XCTAssertEqual(deletedID, "fake-backend-id")

    let failed = await SiriIndexHooks.memoryDeleted(
      "fake-backend-id",
      using: { _ in
        throw URLError(.notConnectedToInternet)
      })
    XCTAssertFalse(failed)
  }

  func testMemoryExpirySweepDeletesExactlyDueIdsBeforeReturning() async throws {
    let now = Date(timeIntervalSince1970: 2_000_000_000)
    let indexed = [
      "already-expired": now.addingTimeInterval(-1),
      "expires-now": now,
      "later": now.addingTimeInterval(30),
    ]
    XCTAssertEqual(SiriMemoryExpirySweep.nextExpiry(indexed), now.addingTimeInterval(-1))
    let probe = DeletionProbe()
    let deleted = try await SiriMemoryExpirySweep.deleteDue(indexed, now: now) { ids in
      await probe.delete(ids)
    }
    XCTAssertEqual(deleted, ["already-expired", "expires-now"])
    let observed = await probe.deletedIDs
    XCTAssertEqual(observed, deleted)

    do {
      _ = try await SiriMemoryExpirySweep.deleteDue(indexed, now: now) { _ in
        throw URLError(.notConnectedToInternet)
      }
      XCTFail("Failed Spotlight deletion must remain eligible for retry")
    } catch { XCTAssertTrue(error is URLError) }
  }
}
