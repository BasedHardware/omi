import XCTest

@testable import Omi_Computer

/// ~/.omi/mcp.json changes must reach chat: every write — including the OAuth
/// token path, which shares the same write seam — posts `.omiUserMcpDidChange`,
/// hand-edits are noticed by the source-of-truth check, and the debounced
/// runtime respawn that consumes the notification never lands mid-turn.
final class UserMcpRuntimeRefreshTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-mcp-refresh-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
    LocalMcpStore.resetChangeDetectionForTesting()
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    LocalMcpStore.resetChangeDetectionForTesting()
    try? FileManager.default.removeItem(at: tempRoot)
  }

  /// Thread-safe counters: the respawn closures run on the main actor but the
  /// test reads them after awaits, and mutable locals captured by escaping
  /// closures keep the concurrency checker unhappy.
  private final class Counter: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0
    func increment() {
      lock.lock()
      value += 1
      lock.unlock()
    }
    var current: Int {
      lock.lock()
      defer { lock.unlock() }
      return value
    }
  }

  private final class Box: @unchecked Sendable {
    var value = false
    init(_ value: Bool) { self.value = value }
  }

  // MARK: - Write-path notification

  func testServerWritesPostUserMcpDidChange() throws {
    let posted = Counter()
    let observer = NotificationCenter.default.addObserver(
      forName: .omiUserMcpDidChange, object: nil, queue: .main
    ) { _ in
      posted.increment()
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    try LocalMcpStore.addCommandServer(name: "Playwright", commandLine: "npx @playwright/mcp@latest")
    XCTAssertEqual(posted.current, 1, "a save must notify so the runtime can respawn")

    // `refreshExpiredTokens` and `signIn` write their token block through this
    // same upsert seam; a re-auth therefore notifies like any other change.
    try LocalMcpStore.upsertServer(
      "playwright", entry: ["url": "https://mcp.example.com", "auth": ["access_token": "t"]])
    XCTAssertEqual(posted.current, 2, "the OAuth token path writes the shared file and must notify too")

    LocalMcpStore.removeServer(name: "playwright")
    XCTAssertEqual(posted.current, 3, "a removal must notify so the runtime drops the server")
  }

  func testExternalHandEditIsNoticedOnceAndOwnWritesAreIgnored() throws {
    // No file yet: nothing to notice.
    XCTAssertFalse(LocalMcpStore.checkForExternalChanges())

    let posted = Counter()
    let observer = NotificationCenter.default.addObserver(
      forName: .omiUserMcpDidChange, object: nil, queue: .main
    ) { _ in
      posted.increment()
    }
    defer { NotificationCenter.default.removeObserver(observer) }

    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
    try Data("{\"mcpServers\": {}}".utf8).write(to: LocalMcpStore.fileURL)
    // The first observation adopts the file silently — there is no earlier
    // baseline in this process to diff against.
    XCTAssertFalse(LocalMcpStore.checkForExternalChanges())
    XCTAssertEqual(posted.current, 0)

    // A UI write records its own fingerprint; it notifies through the write
    // path but must not read back as an external edit.
    try LocalMcpStore.addCommandServer(name: "calc", commandLine: "node calc.js")
    XCTAssertEqual(posted.current, 1)
    XCTAssertFalse(LocalMcpStore.checkForExternalChanges(), "our own write is not an external edit")
    XCTAssertEqual(posted.current, 1)

    // A hand-edit (a server added outside the app) is noticed exactly once.
    let handEdited: [String: Any] = [
      "mcpServers": [
        "calc": ["command": "node", "args": ["calc.js"]],
        "deepwiki": ["url": "https://mcp.deepwiki.com/mcp"],
      ]
    ]
    try JSONSerialization.data(withJSONObject: handEdited).write(to: LocalMcpStore.fileURL)
    XCTAssertTrue(LocalMcpStore.checkForExternalChanges())
    XCTAssertEqual(posted.current, 2)
    XCTAssertFalse(
      LocalMcpStore.checkForExternalChanges(),
      "the baseline was adopted; the same edit must not re-notify")
  }

  // MARK: - Runtime respawn decision

  @MainActor
  func testBurstOfChangesRespawnsStartedRuntimeOnce() async throws {
    let respawns = Counter()
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { true },
      respawn: { respawns.increment() })

    refresh.changeDetected()
    refresh.changeDetected()
    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()

    XCTAssertEqual(respawns.current, 1, "a marketplace-install burst is one respawn")
  }

  @MainActor
  func testChangeDuringATurnStaysPendingUntilTurnBoundary() async throws {
    let respawns = Counter()
    let turnActive = Box(true)
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { turnActive.value },
      isRuntimeStarted: { true },
      respawn: { respawns.increment() })

    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 0, "a reply in flight must never be killed by a respawn")

    // The safe point between turns applies the deferred change.
    turnActive.value = false
    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "the next turn boundary applies the pending change")
  }

  @MainActor
  func testChangeWithNoWarmRuntimeAppliesWithoutRespawn() async throws {
    let respawns = Counter()
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { false },
      respawn: { respawns.increment() })

    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()

    XCTAssertEqual(respawns.current, 0, "with nothing warm there is nothing to respawn yet")
  }

  /// A change landing while the runtime is down must not vanish: the real
  /// instance is the unawaited `refreshExpiredTokens()` at spawn, whose write
  /// notifies during the stop → spawn → warmup window, when the warm flag is
  /// still false. It stays pending and the next boundary applies it.
  @MainActor
  func testChangeDuringColdStartSurvivesAndAppliesAtTheNextBoundary() async throws {
    let respawns = Counter()
    let started = Box(false)
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { started.value },
      respawn: { respawns.increment() })

    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 0)

    // The window closed with the runtime warm; the next boundary applies.
    started.value = true
    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "a change that landed mid-startup applies once the runtime is up")
    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "and exactly once")
  }

  /// The runtime's own writes go through the store's write path, which records
  /// their fingerprint — so the post-respawn re-stat must not read them back
  /// as another change and chase a respawn loop.
  @MainActor
  func testRuntimeOwnWriteDuringRespawnDoesNotRepend() async throws {
    let respawns = Counter()
    var wroteTokenRefresh = false
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { true },
      respawn: {
        respawns.increment()
        guard !wroteTokenRefresh else { return }
        wroteTokenRefresh = true
        // What refreshExpiredTokens does mid-spawn: an own write through the
        // shared store seam, which notifies but records its fingerprint.
        try? LocalMcpStore.upsertServer(
          "playwright", entry: ["url": "https://mcp.example.com", "auth": ["access_token": "t2"]])
      })

    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 1)

    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "the runtime's own refresh write must not respawn again")
  }

  /// A hand-edit landing during the respawn window may postdate the new
  /// process's read of the file: the post-respawn re-stat re-pends it, the
  /// next boundary respawns for it, and then it settles.
  @MainActor
  func testExternalEditDuringRespawnWindowAppliesAtTheNextBoundary() async throws {
    // A store write first, so the process has a fingerprint baseline to
    // compare the mid-respawn hand-edit against.
    try LocalMcpStore.addCommandServer(name: "calc", commandLine: "node calc.js")

    let respawns = Counter()
    var handEdited = false
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { true },
      respawn: {
        respawns.increment()
        guard !handEdited else { return }
        handEdited = true
        // A write from outside the app: it bypasses the store's write path,
        // so nothing records its fingerprint.
        let edited: [String: Any] = [
          "mcpServers": [
            "calc": ["command": "node", "args": ["calc.js"]],
            "deepwiki": ["url": "https://mcp.deepwiki.com/mcp"],
          ]
        ]
        try? JSONSerialization.data(withJSONObject: edited).write(to: LocalMcpStore.fileURL)
      })

    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 1)

    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 2, "the mid-respawn hand-edit applies again at the next boundary")
    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 2, "and then it settles — no loop")
  }

  /// Task chat drives the shared runtime directly and never runs
  /// ChatProvider.ensureBridgeStarted, so its own boundary must consume the
  /// deferred change — exactly the seam `TaskChatRuntime.sharedBridge` calls.
  @MainActor
  func testTaskChatBoundaryConsumesDeferredChange() async throws {
    let respawns = Counter()
    let started = Box(false)
    UserMcpRuntimeRefresh.shared.bindRuntime(
      isTurnActive: { false },
      isRuntimeStarted: { started.value },
      respawn: { respawns.increment() })
    defer {
      // Neutral defaults; the app rebinds from ChatProvider.init.
      UserMcpRuntimeRefresh.shared.bindRuntime(
        isTurnActive: { false },
        isRuntimeStarted: { false },
        respawn: { throw BridgeError.stopped })
    }

    // The change is deferred mid-turn, then the debounced idle cycle keeps it
    // pending while nothing is warm.
    UserMcpRuntimeRefresh.shared.changeDetected()
    await UserMcpRuntimeRefresh.shared.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 0)

    started.value = true
    await TaskChatRuntime.applyPendingUserMcpChangeAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "a task-chat run applies the deferred change before runtime work")
  }

  @MainActor
  func testRefusedRespawnRetriesAtTheNextTurnBoundary() async throws {
    enum RespawnRefused: Error { case requestsActive }
    let respawns = Counter()
    let refusing = Box(true)
    let refresh = UserMcpRuntimeRefresh(
      debounce: { _ in },
      isTurnActive: { false },
      isRuntimeStarted: { true },
      respawn: {
        if refusing.value { throw RespawnRefused.requestsActive }
        respawns.increment()
      })

    // The runtime refuses a restart while a background agent's requests are
    // active; the change must stay pending, not vanish.
    refresh.changeDetected()
    await refresh.awaitDebouncedCycleForTesting()
    XCTAssertEqual(respawns.current, 0)

    refusing.value = false
    await refresh.applyAtTurnBoundary()
    XCTAssertEqual(respawns.current, 1, "the change survives a refused restart and applies later")
  }
}
