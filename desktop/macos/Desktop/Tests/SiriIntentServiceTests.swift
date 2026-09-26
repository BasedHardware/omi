import Foundation
import XCTest

@testable import Omi_Computer

final class SiriIntentServiceTests: XCTestCase {
  private actor DeletionProbe {
    var deletedID: String?
    func delete(_ id: String) { deletedID = id }
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
}
