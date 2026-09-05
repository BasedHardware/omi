import XCTest

@testable import Omi_Computer

/// The store behind the built-in server's card and sheet: the warning chip's
/// arithmetic, the humanized status line, and the switch's off direction. The
/// on direction mints a Keychain token and is exercised on a named bundle, not
/// here.
final class CuaControlStatusStoreTests: XCTestCase {
  private var defaults = UserDefaults.standard
  private var suiteName = ""
  private var tempRoot = FileManager.default.temporaryDirectory
  /// Set by `makeStore`, which every test calls first.
  private var gate: CuaControlGate?

  override func setUpWithError() throws {
    suiteName = "cua-control-status-\(UUID().uuidString)"
    defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-cua-status-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    defaults.removePersistentDomain(forName: suiteName)
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  @MainActor
  private func makeStore(
    granted: [CuaPermission], gateEnabled: Bool = true, screenNeedsRelaunch: Bool = false
  ) -> CuaControlStatusStore {
    let gate = CuaControlGate(
      defaults: defaults,
      missingPermission: { _ in nil },
      ownerID: { "owner-1" })
    // Both directions, not just the on one: the suite is shared across the
    // stores a single test makes, so an unwritten `false` inherits the previous
    // store's `true` and the case never runs.
    gate.setEnabled(gateEnabled)
    self.gate = gate
    return CuaControlStatusStore(
      gate: gate,
      isGranted: { granted.contains($0) },
      needsRelaunch: { screenNeedsRelaunch })
  }

  /// The card reads like every other server card — one status word, colored
  /// active only when the tools can actually run — with gate state outranking
  /// grants the way the gate itself outranks them.
  @MainActor
  func testCardStatusSpeaksTheUniformVocabulary() {
    XCTAssertEqual(makeStore(granted: [], gateEnabled: false).cardStatusText, "Off")

    let missing = makeStore(granted: [])
    XCTAssertEqual(missing.cardStatusText, "Needs 3 grants")
    XCTAssertFalse(missing.cardStatusActive)
    XCTAssertEqual(makeStore(granted: [.screenRecording, .postEvents]).cardStatusText, "Needs 1 grant")

    let ready = makeStore(granted: [.postEvents, .accessibility, .screenRecording])
    XCTAssertEqual(ready.cardStatusText, "Ready")
    XCTAssertTrue(ready.cardStatusActive)

    ready.stopNow()
    XCTAssertEqual(ready.cardStatusText, "Stopped")
    XCTAssertFalse(ready.cardStatusActive)
  }

  /// A Screen Recording grant given after launch reads as granted to every
  /// preflight and is dead to ScreenCaptureKit until Omi restarts. Reporting it
  /// as "Ready" sends the user back to System Settings to redo what they just
  /// did, so the card carries the one instruction that helps.
  @MainActor
  func testAGrantThatOnlyAFreshLaunchCanUseIsNotReady() {
    let stale = makeStore(
      granted: [.postEvents, .accessibility, .screenRecording], screenNeedsRelaunch: true)

    XCTAssertEqual(stale.missingGrantCount, 0, "macOS has given every grant")
    XCTAssertEqual(stale.cardStatusText, "Restart to apply")
    XCTAssertFalse(stale.cardStatusActive, "the tools cannot run until the next launch")

    // Gate state still outranks it: an off server has no restart worth offering.
    XCTAssertEqual(
      makeStore(
        granted: [.postEvents, .accessibility, .screenRecording], gateEnabled: false,
        screenNeedsRelaunch: true
      ).cardStatusText, "Off")

    // And a missing grant is the more actionable of the two.
    XCTAssertEqual(
      makeStore(granted: [.screenRecording], screenNeedsRelaunch: true).cardStatusText,
      "Needs 2 grants")
  }

  /// The switch is the whole setup in both directions: turning it off closes the
  /// gate and removes the mcp.json entry Omi's own agent reads.
  @MainActor
  func testTurningTheSwitchOffClosesTheGateAndUnregistersTheEntry() throws {
    try CuaMcpRegistration.register(token: "tok-123")
    let store = makeStore(granted: [])

    store.isEnabled = false

    let gate = try XCTUnwrap(self.gate)
    XCTAssertFalse(store.isEnabled)
    XCTAssertFalse(gate.isEnabled)
    XCTAssertNil(LocalMcpStore.readAllServers()[CuaMcpRegistration.serverName])
  }

  /// The status line stays honest at both ends: sub-perceptual latency is
  /// "now", and anything older is spoken in human units rather than seconds.
  @MainActor
  func testStatusTextHumanizesTheLastAction() throws {
    let store = makeStore(granted: [])
    let gate = try XCTUnwrap(self.gate)

    store.stopNow()
    XCTAssertEqual(store.statusText(), "Stopped — stopped from Settings")
    store.rearm()
    XCTAssertEqual(store.statusText(), "Ready. Nothing has used it yet.")

    let result = gate.perform(needs: []) { 1 }
    guard case .success = result else { return XCTFail("expected the effect to run") }
    let last = try XCTUnwrap(gate.lastActivity)

    XCTAssertEqual(store.statusText(at: last.addingTimeInterval(2)), "Active now")
    XCTAssertTrue(store.statusText(at: last.addingTimeInterval(70)).hasPrefix("Ready. Last action"))
  }
}
