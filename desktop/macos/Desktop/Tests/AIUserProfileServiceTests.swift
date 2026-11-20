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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: clock.now)

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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: clock.now)

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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)
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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)
    _ = await service.getLatestProfile()

    try await service.deleteProfile()
    let read = await service.getLatestProfile()
    XCTAssertNil(read)
    XCTAssertEqual(backend.deleteCount, 1)
  }

  func testRefreshStoresTheBackendProfileAndMapsFailures() async throws {
    let backend = FakeBackend(profile: nil)
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

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
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

    let saved = await service.appendExploration("works on Swift")
    XCTAssertTrue(saved)
    XCTAssertEqual(backend.updates.map(\.source), [.exploration])
    XCTAssertEqual(
      backend.updates.first?.text, "generated" + AIUserProfileService.explorationSeparator + "works on Swift")
  }

  func testExplorationWithoutAProfileStartsOne() async {
    let backend = FakeBackend(profile: nil)
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

    let saved = await service.appendExploration("works on Swift")
    XCTAssertTrue(saved)
    XCTAssertEqual(backend.updates.first?.text, "works on Swift")
  }

  func testExplorationIsNotSavedWhenTheProfileCannotBeRead() async {
    let backend = FakeBackend(profile: "generated")
    backend.failFetches = true
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

    let saved = await service.appendExploration("works on Swift")
    XCTAssertFalse(saved, "a failed read is not \"no profile\"; writing would replace the profile")
    XCTAssertTrue(backend.updates.isEmpty)
  }

  func testExplorationNeedsAFreshReadEvenWithACachedProfile() async {
    let backend = FakeBackend(profile: "generated")
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)
    _ = await service.getLatestProfile()

    backend.failFetches = true
    let saved = await service.appendExploration("works on Swift")
    XCTAssertFalse(saved)
    XCTAssertTrue(backend.updates.isEmpty)
    let read = await service.getLatestProfile()
    XCTAssertEqual(read?.profileText, "generated", "the cached profile is untouched")
  }

  func testExplorationIsNotSavedWhenTheOwnerChangesDuringTheRead() async {
    let backend = FakeBackend(profile: "owner A")
    let started = Gate()
    let release = Gate()
    backend.beforeFetch = {
      started.open()
      await release.wait()
    }
    let service = AIUserProfileService(client: backend.client, localHistory: .inert, now: TestClock().now)

    let pending = Task { await service.appendExploration("owner A's files") }
    await started.wait()
    await service.invalidateCache()
    release.open()

    let saved = await pending.value
    XCTAssertFalse(saved)
    XCTAssertTrue(backend.updates.isEmpty)
  }

  // MARK: - Retired local history

  func testUnsyncedNewerLocalRowIsUploadedThenTheTableDropped() async {
    let backend = FakeBackend(profile: nil)
    backend.setProfile("cloud", generatedAt: Self.day(1), source: "client")
    let history = FakeLocalHistory(rows: [
      "A": .init(text: "local correction", generatedAt: Self.day(2), backendSynced: false)
    ])
    let service = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)

    _ = await service.getLatestProfile()
    await service.waitForLocalHistorySalvage()

    XCTAssertEqual(history.uploads, [.init(owner: "A", text: "local correction", generatedAt: Self.day(2))])
    XCTAssertEqual(history.tableExists("A"), false)
    let read = await service.getLatestProfile()
    XCTAssertEqual(read?.profileText, "local correction", "the restored profile replaces the cached one")
  }

  func testUnsyncedRowWithNoCloudProfileIsUploaded() async {
    let backend = FakeBackend(profile: nil)
    let history = FakeLocalHistory(rows: ["A": .init(text: "only copy", generatedAt: Self.day(2), backendSynced: false)]
    )
    let service = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)

    _ = await service.getLatestProfile()
    await service.waitForLocalHistorySalvage()

    XCTAssertEqual(history.uploads.map(\.text), ["only copy"])
    XCTAssertEqual(history.tableExists("A"), false)
  }

  func testSyncedOrOlderLocalRowIsDroppedWithoutUpload() async {
    let rows: [LocalProfileHistoryRetirement.Row] = [
      .init(text: "synced newer", generatedAt: Self.day(2), backendSynced: true),
      .init(text: "unsynced older", generatedAt: Self.day(0), backendSynced: false),
    ]
    for row in rows {
      let backend = FakeBackend(profile: nil)
      backend.setProfile("cloud", generatedAt: Self.day(1), source: "backend")
      let history = FakeLocalHistory(rows: ["A": row])
      let service = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)

      _ = await service.getLatestProfile()
      await service.waitForLocalHistorySalvage()

      XCTAssertTrue(history.uploads.isEmpty, row.text)
      XCTAssertEqual(history.tableExists("A"), false, row.text)
      let read = await service.getLatestProfile()
      XCTAssertEqual(read?.profileText, "cloud", row.text)
    }
  }

  func testUploadFailureKeepsTheTableAndTheNextLaunchRetries() async {
    let backend = FakeBackend(profile: nil)
    backend.setProfile("cloud", generatedAt: Self.day(1), source: "client")
    let history = FakeLocalHistory(rows: ["A": .init(text: "local", generatedAt: Self.day(2), backendSynced: false)])
    history.failUploads = true
    let firstLaunch = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)

    _ = await firstLaunch.getLatestProfile()
    await firstLaunch.waitForLocalHistorySalvage()
    XCTAssertEqual(history.uploadAttempts, 1)
    XCTAssertEqual(history.tableExists("A"), true, "the only copy survives a failed upload")
    let cachedAfterFailure = await firstLaunch.fetchProfile()
    await firstLaunch.waitForLocalHistorySalvage()
    XCTAssertEqual(cachedAfterFailure?.profileText, "cloud")
    XCTAssertEqual(history.uploadAttempts, 1, "no retry loop within one launch")

    history.failUploads = false
    let nextLaunch = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)
    _ = await nextLaunch.getLatestProfile()
    await nextLaunch.waitForLocalHistorySalvage()
    XCTAssertEqual(history.uploads.map(\.text), ["local"])
    XCTAssertEqual(history.tableExists("A"), false)
  }

  func testOwnerSwitchMidSalvageNeverUploadsUnderTheNextOwner() async {
    let backend = FakeBackend(profile: nil)
    backend.setProfile("A cloud", generatedAt: Self.day(1), source: "client")
    let history = FakeLocalHistory(rows: ["A": .init(text: "A local", generatedAt: Self.day(2), backendSynced: false)])
    let started = Gate()
    let release = Gate()
    history.afterContentsRead = {
      started.open()
      await release.wait()
    }
    let service = AIUserProfileService(client: backend.client, localHistory: history.store, now: TestClock().now)

    _ = await service.getLatestProfile()
    await started.wait()
    history.signIn("B")
    await service.invalidateCache()
    backend.setProfile("B cloud", generatedAt: Self.day(0), source: "backend")
    release.open()
    await service.waitForLocalHistorySalvage()

    XCTAssertTrue(history.uploads.isEmpty, "owner A's row is never sent once B is signed in")
    XCTAssertEqual(history.tableExists("A"), true, "owner A keeps the table for their next session")
    let read = await service.getLatestProfile()
    await service.waitForLocalHistorySalvage()
    XCTAssertEqual(read?.profileText, "B cloud")
    XCTAssertTrue(history.uploads.isEmpty, "B's own session has nothing to salvage")
  }

  func testCombineTrimsTheOlderProfileToKeepNewInsightsWhole() {
    let existing = String(repeating: "a", count: AIUserProfileService.maxProfileLength)
    let combined = AIUserProfileService.combine(existing: existing, exploration: "new insight")
    XCTAssertEqual(combined.count, AIUserProfileService.maxProfileLength)
    XCTAssertTrue(combined.hasSuffix(AIUserProfileService.explorationSeparator + "new insight"))
  }

  // MARK: - Helpers

  private static func day(_ offset: Int) -> Date {
    Date(timeIntervalSince1970: 1_794_817_800 + Double(offset) * 86_400)
  }

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
  private var profileGeneratedAt: Date?
  private var profileSource: String?
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

  func setProfile(_ text: String?, generatedAt: Date? = nil, source: String? = nil) {
    locked {
      profileText = text
      profileGeneratedAt = generatedAt
      profileSource = source
    }
  }

  var client: AIUserProfileClient {
    AIUserProfileClient(
      fetch: { [self] in
        await self.beforeFetch?()
        return try self.locked {
          self._fetchCount += 1
          if self._failFetches { throw URLError(.notConnectedToInternet) }
          return self.profileText.map {
            AIUserProfileResponse(profileText: $0, generatedAt: self.profileGeneratedAt, source: self.profileSource)
          }
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

/// Per-owner retired tables; `signIn` switches the owner every binding is checked against.
private final class FakeLocalHistory: @unchecked Sendable {
  struct Upload: Equatable {
    let owner: String
    let text: String
    let generatedAt: Date
  }

  private let lock = NSLock()
  private var rows: [String: LocalProfileHistoryRetirement.Row]
  private var dropped: Set<String> = []
  private var currentOwner = "A"
  private var _uploads: [Upload] = []
  private var _uploadAttempts = 0
  private var _failUploads = false
  private var _afterContentsRead: (@Sendable () async -> Void)?

  init(rows: [String: LocalProfileHistoryRetirement.Row]) { self.rows = rows }

  var uploads: [Upload] { locked { _uploads } }
  var uploadAttempts: Int { locked { _uploadAttempts } }
  var failUploads: Bool {
    get { locked { _failUploads } }
    set { locked { _failUploads = newValue } }
  }
  var afterContentsRead: (@Sendable () async -> Void)? {
    get { locked { _afterContentsRead } }
    set { locked { _afterContentsRead = newValue } }
  }

  func signIn(_ owner: String) { locked { currentOwner = owner } }
  func tableExists(_ owner: String) -> Bool { locked { rows[owner] != nil && !dropped.contains(owner) } }

  var store: LocalProfileHistoryRetirement.Store {
    LocalProfileHistoryRetirement.Store(
      bindOwner: { [self] in
        let owner = self.locked { self.currentOwner }
        return LocalProfileHistoryRetirement.Owner(
          snapshot: nil, isCurrent: { self.locked { self.currentOwner == owner } })
      },
      contents: { [self] owner in
        let name = try self.name(of: owner)
        let contents: LocalProfileHistoryRetirement.Contents = self.locked {
          guard let row = self.rows[name], !self.dropped.contains(name) else { return .retired }
          return .history(newest: row)
        }
        // The read has answered for its owner; an account switch can still land before upload.
        await self.afterContentsRead?()
        return contents
      },
      upload: { [self] row, _ in
        // Worst-case transport: whoever is signed in now. Only the salvage's fence stops it.
        let name = self.locked { self.currentOwner }
        return try self.locked {
          self._uploadAttempts += 1
          if self._failUploads { throw URLError(.timedOut) }
          self._uploads.append(Upload(owner: name, text: row.text, generatedAt: row.generatedAt))
          return AIUserProfile(AIUserProfileResponse(profileText: row.text, generatedAt: row.generatedAt))
        }
      },
      drop: { [self] owner in
        let name = try self.name(of: owner)
        self.locked { _ = self.dropped.insert(name) }
      })
  }

  /// The owner's name if it is still signed in, as the live store's checks require.
  private func name(of owner: LocalProfileHistoryRetirement.Owner) throws -> String {
    guard owner.isCurrent() else { throw LocalMutationAuthorizationError.revoked }
    return locked { currentOwner }
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
