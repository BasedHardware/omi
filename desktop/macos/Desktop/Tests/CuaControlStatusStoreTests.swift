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
  private func makeStore(granted: [CuaPermission]) -> CuaControlStatusStore {
    let gate = CuaControlGate(
      defaults: defaults,
      missingPermission: { _ in nil },
      ownerID: { "owner-1" })
    gate.setEnabled(true)
    self.gate = gate
    return CuaControlStatusStore(
      gate: gate,
      isGranted: { granted.contains($0) })
  }

  /// The chip counts the same three rows the sheet lists, so its number is one
  /// the user can check against System Settings.
  @MainActor
  func testMissingGrantCountCountsTheListedRows() {
    XCTAssertEqual(makeStore(granted: []).missingGrantCount, 3)
    XCTAssertEqual(
      makeStore(granted: [.postEvents, .accessibility, .screenRecording]).missingGrantCount, 0)
    XCTAssertEqual(makeStore(granted: [.screenRecording]).missingGrantCount, 2)
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
