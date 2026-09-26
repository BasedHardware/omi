import Foundation
import XCTest

@testable import Omi_Computer

final class SiriIntentServiceTests: XCTestCase {
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
    XCTAssertEqual(entity.expiresAt, expiry)
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
    XCTAssertTrue(
      SiriIndexScope.memory(
        backendId: "m", deleted: false, dismissed: false,
        expiresAt: now.addingTimeInterval(1), now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: "m", deleted: false, dismissed: false,
        expiresAt: now, now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: nil, deleted: false, dismissed: false,
        expiresAt: nil, now: now))
    XCTAssertFalse(
      SiriIndexScope.memory(
        backendId: "m", deleted: true, dismissed: false,
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
    XCTAssertTrue(
      SiriIndexScope.task(
        backendId: "t", deleted: false, completed: true,
        completedAt: cutoff, now: now))
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
