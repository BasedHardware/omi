import Combine
import XCTest

@testable import Omi_Computer

@MainActor
final class OfflinePTTQuestionRecoveryTests: XCTestCase {
  func testRecoveryIsUnsentAndHandsOffOnce() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "test", expectedOwnerID: "test"))
    let recovery = OfflinePTTQuestionRecovery(isAuthorized: { authority.isCurrent($0, ownerID: "test") })
    XCTAssertTrue(recovery.capture("What is next?", authorization: snapshot))
    var presented: String?
    XCTAssertTrue(
      recovery.review { text, _ in
        presented = text
        return true
      })
    XCTAssertEqual(presented, "What is next?")
    XCTAssertFalse(recovery.isAvailable)
    XCTAssertFalse(
      recovery.review { _, _ in
        XCTFail("already consumed")
        return true
      })
  }

  func testCopyKeepsQuestionAvailableAndFailedPresentationDoesNotLoseIt() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "test", expectedOwnerID: "test"))
    let recovery = OfflinePTTQuestionRecovery(isAuthorized: { authority.isCurrent($0, ownerID: "test") })
    recovery.capture("  hello  ", authorization: snapshot)
    XCTAssertFalse(recovery.review { _, _ in false })
    var copied: String?
    XCTAssertTrue(recovery.copy { copied = $0 })
    XCTAssertEqual(copied, "hello")
    XCTAssertTrue(recovery.isAvailable)
  }

  func testSameUserReauthenticationRevokesRecoveredText() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "test", expectedOwnerID: "test"))
    let recovery = OfflinePTTQuestionRecovery(isAuthorized: { authority.isCurrent($0, ownerID: "test") })
    recovery.capture("private question", authorization: snapshot)
    authority.beginTransition()
    authority.endTransition(ownerID: "test")
    XCTAssertFalse(recovery.copy { _ in XCTFail("revoked text") })
    XCTAssertFalse(recovery.isAvailable)
  }

  func testExpiredQuestionAndExplicitClearCannotBeRecovered() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "test", expectedOwnerID: "test"))
    var now = Date(timeIntervalSince1970: 0)
    let recovery = OfflinePTTQuestionRecovery(now: { now }, isAuthorized: { _ in true })
    recovery.capture("hello", authorization: snapshot)
    now = now.addingTimeInterval(300)
    XCTAssertFalse(
      recovery.review { _, _ in
        XCTFail("expired text")
        return true
      })
    recovery.capture("next question", authorization: snapshot)
    recovery.clear()
    XCTAssertFalse(recovery.isAvailable)
  }

  func testInjectedExpiryPublishesAndAnOldTimerCannotClearANewQuestion() async throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "test", expectedOwnerID: "test"))
    let gate = ExpirySleepGate()
    let recovery = OfflinePTTQuestionRecovery(
      isAuthorized: { _ in true },
      sleep: { seconds in try await gate.sleep(seconds) })

    XCTAssertTrue(recovery.capture("old question", authorization: snapshot))
    await gate.waitUntilStarted(0)
    XCTAssertTrue(recovery.hasQuestion)

    XCTAssertTrue(recovery.capture("new question", authorization: snapshot))
    await gate.waitUntilStarted(1)

    let currentQuestionExpired = expectation(description: "current question expiry is published")
    var currentExpiryReleased = false
    var staleExpiryPublished = false
    let expiryObservation = recovery.$hasQuestion.dropFirst().sink { hasQuestion in
      guard !hasQuestion else { return }
      if currentExpiryReleased {
        currentQuestionExpired.fulfill()
      } else {
        staleExpiryPublished = true
      }
    }

    // The first task was cancelled by the replacement, but the injected clock
    // deliberately ignores cancellation so its late wake-up exercises the
    // question-id fence instead of disappearing from the test.
    await gate.release(0)
    await gate.waitUntilReturned(0)
    XCTAssertTrue(recovery.hasQuestion)
    var copied: String?
    XCTAssertTrue(recovery.copy { copied = $0 })
    XCTAssertEqual(copied, "new question")

    currentExpiryReleased = true
    await gate.release(1)
    await gate.waitUntilReturned(1)
    await fulfillment(of: [currentQuestionExpired])
    withExtendedLifetime(expiryObservation) {}
    XCTAssertFalse(staleExpiryPublished, "the old timer must not publish expiry for the replacement")
    XCTAssertFalse(recovery.hasQuestion, "the current question must publish expiry")
    XCTAssertFalse(recovery.isAvailable)
  }

  private actor ExpirySleepGate {
    private var nextID = 0
    private var pending: [Int: CheckedContinuation<Void, Never>] = [:]
    private var started: Set<Int> = []
    private var returned: Set<Int> = []
    private var startWaiters: [Int: [CheckedContinuation<Void, Never>]] = [:]
    private var returnWaiters: [Int: [CheckedContinuation<Void, Never>]] = [:]

    func sleep(_ seconds: TimeInterval) async throws {
      let id = nextID
      nextID += 1
      started.insert(id)
      for waiter in startWaiters.removeValue(forKey: id) ?? [] {
        waiter.resume()
      }
      await withCheckedContinuation { continuation in
        pending[id] = continuation
      }
      returned.insert(id)
      for waiter in returnWaiters.removeValue(forKey: id) ?? [] {
        waiter.resume()
      }
    }

    func waitUntilStarted(_ id: Int) async {
      if started.contains(id) { return }
      await withCheckedContinuation { continuation in
        startWaiters[id, default: []].append(continuation)
      }
    }

    func release(_ id: Int) {
      pending.removeValue(forKey: id)?.resume()
    }

    func waitUntilReturned(_ id: Int) async {
      if returned.contains(id) { return }
      await withCheckedContinuation { continuation in
        returnWaiters[id, default: []].append(continuation)
      }
    }
  }
}
