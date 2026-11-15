import Foundation
import XCTest

@testable import Omi_Computer

/// The backend owns the AI user profile; the desktop service is a cached reader that
/// routes Settings and file-exploration mutations to `/v1/users/ai-profile`.
final class AIUserProfileServiceTests: XCTestCase {

  // MARK: - Wire contract

  func testDecodesCloudOwnedProfileFields() throws {
    let response = try decode(
      """
      {"profile_text": "- Engineer", "generated_at": "2026-11-16T08:30:00.123456+00:00",
       "data_sources_used": 42, "source": "backend", "refreshed_at": "2026-11-16T08:30:00Z"}
      """)
    let profile = try XCTUnwrap(AIUserProfile(response))
    XCTAssertEqual(profile.profileText, "- Engineer")
    XCTAssertEqual(profile.dataSourcesUsed, 42)
    XCTAssertEqual(profile.source, "backend")
    XCTAssertEqual(profile.refreshedAt, Date(timeIntervalSince1970: 1_794_817_800))
    XCTAssertEqual(try XCTUnwrap(profile.generatedAt).timeIntervalSince1970, 1_794_817_800.123, accuracy: 0.001)
  }

  func testDecodesLegacyPayloadAndZonelessDates() throws {
    let response = try decode(
      """
      {"profile_text": "- Runner", "generated_at": "2026-11-16T08:30:00", "data_sources_used": null}
      """)
    let profile = try XCTUnwrap(AIUserProfile(response))
    XCTAssertEqual(profile.generatedAt, Date(timeIntervalSince1970: 1_794_817_800))
    XCTAssertEqual(profile.dataSourcesUsed, 0)
    XCTAssertNil(profile.source)
  }

  func testMalformedDateKeepsTheProfileText() throws {
    let response = try decode(#"{"profile_text": "- Writer", "generated_at": "yesterday"}"#)
    XCTAssertEqual(AIUserProfile(response)?.profileText, "- Writer")
    XCTAssertNil(AIUserProfile(response)?.generatedAt)
  }

  func testNullOrBlankProfileIsNoProfile() throws {
    let null = try OmiHTTPTransport.makeDecoder().decode(
      AIUserProfileResponse?.self, from: Data("null".utf8))
    XCTAssertNil(AIUserProfile(null))
    XCTAssertNil(AIUserProfile(try decode(#"{"profile_text": "  \n"}"#)))
    XCTAssertNil(AIUserProfile(try decode(#"{"profile_text": null}"#)))
  }

  func testRefreshErrorsMapToSettingsMessages() {
    let cases: [(Int, AIUserProfileRefreshError)] = [
      (402, .usageBudgetExhausted), (409, .alreadyRefreshing), (422, .insufficientData),
      (429, .rateLimited), (502, .synthesisFailed), (500, .unavailable),
    ]
    for (status, expected) in cases {
      let mapped = AIUserProfileRefreshError(APIError.httpError(statusCode: status, detail: "detail"))
      XCTAssertEqual(mapped, expected, "HTTP \(status)")
      XCTAssertFalse(mapped.errorDescription?.isEmpty ?? true)
    }
    XCTAssertEqual(AIUserProfileRefreshError(URLError(.notConnectedToInternet)), .unavailable)
  }

  // MARK: - Cache

  func testPromptReadsAreServedFromMemoryUntilTheCacheAgesOut() async {
    let backend = FakeBackend(profile: "first")
    let clock = TestClock()
    let service = AIUserProfileService(client: backend.client, now: clock.now)

    let initial = await service.getLatestProfile()
    let cachedRead = await service.getLatestProfile()
    XCTAssertEqual(initial?.profileText, "first")
    XCTAssertEqual(cachedRead?.profileText, "first")
    XCTAssertEqual(backend.fetchCount, 1)

    backend.setProfile("second")
    clock.advance(AIUserProfileService.cacheTTL + 1)
    // A stale cache answers immediately and revalidates in the background.
    let staleRead = await service.getLatestProfile()
    XCTAssertEqual(staleRead?.profileText, "first")
    let revalidated = await service.fetchProfile()
    XCTAssertEqual(revalidated?.profileText, "second")
    let afterRevalidation = await service.getLatestProfile()
    XCTAssertEqual(afterRevalidation?.profileText, "second")
  }

  func testFailedReadBacksOffInsteadOfRetryingEveryPrompt() async {
    let backend = FakeBackend(profile: nil)
    backend.failFetches = true
    let clock = TestClock()
    let service = AIUserProfileService(client: backend.client, now: clock.now)

    let failed = await service.getLatestProfile()
    let backedOff = await service.getLatestProfile()
    XCTAssertNil(failed)
    XCTAssertNil(backedOff)
    XCTAssertEqual(backend.fetchCount, 1)

    backend.failFetches = false
    backend.setProfile("recovered")
    clock.advance(AIUserProfileService.failureBackoff + 1)
    let recovered = await service.getLatestProfile()
    XCTAssertEqual(recovered?.profileText, "recovered")
  }

  func testOwnerSwitchDropsTheCacheAndALateReadForThePreviousOwner() async {
    let backend = FakeBackend(profile: "owner A")
    let started = Gate()
    let release = Gate()
    backend.beforeFetch = {
      started.open()
      await release.wait()
    }
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)

    let pending = Task { await service.getLatestProfile() }
    await started.wait()
    await service.invalidateCache()
    backend.setProfile("owner B")
    release.open()

    let late = await pending.value
    XCTAssertNil(late, "a read started for the previous owner must not answer for the next")
    let next = await service.getLatestProfile()
    XCTAssertEqual(next?.profileText, "owner B")
  }

  // MARK: - Mutations

  func testEditSendsUserEditSourceAndUpdatesTheCache() async throws {
    let backend = FakeBackend(profile: "generated")
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)
    _ = await service.getLatestProfile()

    let saved = try await service.updateProfileText("corrected", source: .userEdit)
    XCTAssertEqual(saved?.profileText, "corrected")
    XCTAssertEqual(backend.updates.map(\.source), [.userEdit])
    let read = await service.getLatestProfile()
    XCTAssertEqual(read?.profileText, "corrected")
    XCTAssertEqual(backend.fetchCount, 1, "a mutation refreshes the cache without another read")
  }

  func testAReadThatStartedBeforeAnEditCannotOverwriteIt() async throws {
    let backend = FakeBackend(profile: "old")
    let started = Gate()
    let release = Gate()
    backend.beforeFetch = {
      started.open()
      await release.wait()
    }
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)

    let pending = Task { await service.fetchProfile() }
    await started.wait()
    _ = try await service.updateProfileText("edited", source: .userEdit)
    release.open()
    _ = await pending.value

    let read = await service.getLatestProfile()
    XCTAssertEqual(read?.profileText, "edited")
  }

  func testDeleteClearsTheCache() async throws {
    let backend = FakeBackend(profile: "generated")
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)
    _ = await service.getLatestProfile()

    try await service.deleteProfile()
    let read = await service.getLatestProfile()
    XCTAssertNil(read)
    XCTAssertEqual(backend.deleteCount, 1)
  }

  func testRefreshStoresTheBackendProfileAndMapsFailures() async throws {
    let backend = FakeBackend(profile: nil)
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)

    backend.refreshResult = .success(AIUserProfileResponse(profileText: "fresh", source: "backend"))
    let refreshed = try await service.refresh()
    XCTAssertEqual(refreshed?.profileText, "fresh")
    let read = await service.getLatestProfile()
    XCTAssertEqual(read?.profileText, "fresh")

    backend.refreshResult = .failure(APIError.httpError(statusCode: 422, detail: "ai_profile_insufficient_data"))
    do {
      _ = try await service.refresh()
      XCTFail("expected insufficient data")
    } catch {
      XCTAssertEqual(error as? AIUserProfileRefreshError, .insufficientData)
    }
    let unchanged = await service.getLatestProfile()
    XCTAssertEqual(unchanged?.profileText, "fresh")
  }

  func testExplorationAppendsToTheCurrentProfileWithExplorationSource() async {
    let backend = FakeBackend(profile: "generated")
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)

    let saved = await service.appendExploration("works on Swift")
    XCTAssertTrue(saved)
    XCTAssertEqual(backend.updates.map(\.source), [.exploration])
    XCTAssertEqual(
      backend.updates.first?.text, "generated" + AIUserProfileService.explorationSeparator + "works on Swift")
  }

  func testExplorationWithoutAProfileStartsOne() async {
    let backend = FakeBackend(profile: nil)
    let service = AIUserProfileService(client: backend.client, now: TestClock().now)

    let saved = await service.appendExploration("works on Swift")
    XCTAssertTrue(saved)
    XCTAssertEqual(backend.updates.first?.text, "works on Swift")
  }

  func testCombineTrimsTheOlderProfileToKeepNewInsightsWhole() {
    let existing = String(repeating: "a", count: AIUserProfileService.maxProfileLength)
    let combined = AIUserProfileService.combine(existing: existing, exploration: "new insight")
    XCTAssertEqual(combined.count, AIUserProfileService.maxProfileLength)
    XCTAssertTrue(combined.hasSuffix(AIUserProfileService.explorationSeparator + "new insight"))
  }

  // MARK: - Helpers

  private func decode(_ json: String) throws -> AIUserProfileResponse {
    try OmiHTTPTransport.makeDecoder().decode(AIUserProfileResponse.self, from: Data(json.utf8))
  }
}

// MARK: - Fakes

private final class FakeBackend: @unchecked Sendable {
  struct Update: Sendable {
    let text: String
    let source: AIUserProfileEditSource
  }

  private let lock = NSLock()
  private var profileText: String?
  private var _fetchCount = 0
  private var _failFetches = false
  private var _updates: [Update] = []
  private var _deleteCount = 0
  private var _refreshResult: Result<AIUserProfileResponse, Error> = .failure(APIError.invalidResponse)
  private var _beforeFetch: (@Sendable () async -> Void)?

  init(profile: String?) { profileText = profile }

  var fetchCount: Int { locked { _fetchCount } }
  var updates: [Update] { locked { _updates } }
  var deleteCount: Int { locked { _deleteCount } }
  var failFetches: Bool {
    get { locked { _failFetches } }
    set { locked { _failFetches = newValue } }
  }
  var refreshResult: Result<AIUserProfileResponse, Error> {
    get { locked { _refreshResult } }
    set { locked { _refreshResult = newValue } }
  }
  var beforeFetch: (@Sendable () async -> Void)? {
    get { locked { _beforeFetch } }
    set { locked { _beforeFetch = newValue } }
  }

  func setProfile(_ text: String?) { locked { profileText = text } }

  var client: AIUserProfileClient {
    AIUserProfileClient(
      fetch: { [self] in
        await self.beforeFetch?()
        return try self.locked {
          self._fetchCount += 1
          if self._failFetches { throw URLError(.notConnectedToInternet) }
          return self.profileText.map { AIUserProfileResponse(profileText: $0) }
        }
      },
      refresh: { [self] in
        try self.refreshResult.get()
      },
      update: { [self] text, source in
        self.locked {
          self._updates.append(Update(text: text, source: source))
          self.profileText = text
          return AIUserProfileResponse(profileText: text, source: source.rawValue)
        }
      },
      delete: { [self] in
        self.locked {
          self._deleteCount += 1
          self.profileText = nil
        }
      })
  }

  private func locked<T>(_ body: () throws -> T) rethrows -> T {
    lock.lock()
    defer { lock.unlock() }
    return try body()
  }
}

private final class TestClock: @unchecked Sendable {
  private let lock = NSLock()
  private var current = Date(timeIntervalSince1970: 1_794_817_800)

  var now: @Sendable () -> Date {
    { [self] in
      self.lock.lock()
      defer { self.lock.unlock() }
      return self.current
    }
  }

  func advance(_ seconds: TimeInterval) {
    lock.lock()
    current += seconds
    lock.unlock()
  }
}

/// One-shot latch: `wait()` suspends until `open()`; waits after opening return at once.
private final class Gate: @unchecked Sendable {
  private let lock = NSLock()
  private var opened = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
      lock.lock()
      if opened {
        lock.unlock()
        continuation.resume()
      } else {
        waiters.append(continuation)
        lock.unlock()
      }
    }
  }

  func open() {
    lock.lock()
    opened = true
    let pending = waiters
    waiters = []
    lock.unlock()
    for continuation in pending { continuation.resume() }
  }
}
