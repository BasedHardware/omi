import XCTest

@testable import Omi_Computer

/// A bundle that shipped without `Contents/Resources/pi-mono-extension` accepted
/// every chat turn and failed every one of them four seconds later: pi-mono could
/// not resolve the `omi` provider the extension registers and exited 1. node and
/// the bridge script were both present, so every startup check the runtime had
/// passed. These tests drive the real payload check against real directory trees.
final class AgentRuntimePayloadTests: XCTestCase {

  private var root: URL = URL(fileURLWithPath: NSTemporaryDirectory())

  override func setUpWithError() throws {
    try super.setUpWithError()
    root = URL(fileURLWithPath: NSTemporaryDirectory())
      .appendingPathComponent("omi-agent-runtime-payload-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    try installCompleteRuntime()
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(at: root)
    try super.tearDownWithError()
  }

  // MARK: - Fixtures

  private var bridgeScriptPath: String {
    root.appendingPathComponent("agent/dist/index.js").path
  }

  private func write(_ relativePath: String, contents: String = "payload") throws {
    let url = root.appendingPathComponent(relativePath)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try contents.write(to: url, atomically: true, encoding: .utf8)
  }

  /// Mirrors what `run.sh` packages into `Contents/Resources`.
  private func installCompleteRuntime() throws {
    try write("agent/dist/index.js")
    try write("agent/dist/runtime/omi-tool-manifest.js")
    try write("agent/package.json")
    try write("agent/node_modules/@omi/placeholder/package.json")
    try write("pi-mono-extension/index.ts")
    try write("pi-mono-extension/package.json")
    try write("pi-mono-extension/node_modules/@omi/placeholder/package.json")
  }

  private func remove(_ relativePath: String) throws {
    try FileManager.default.removeItem(at: root.appendingPathComponent(relativePath))
  }

  // MARK: - Payload check

  func testACompleteRuntimeReportsNothingMissing() {
    XCTAssertEqual(AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath), [])
  }

  func testTheRuntimeRootIsTheDirectoryHoldingBothPackages() {
    XCTAssertEqual(
      AgentRuntimePayload.runtimeRoot(
        forBridgeScriptPath: "/Applications/omi.app/Contents/Resources/agent/dist/index.js"),
      "/Applications/omi.app/Contents/Resources",
      "must resolve exactly where the pi-mono adapter resolves its extension from")
  }

  /// The shipped failure: the directory the `omi` provider lives in is gone.
  func testADeletedPiMonoExtensionIsReportedBeforeAnySpawn() throws {
    try remove("pi-mono-extension")
    let missing = AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath)
    XCTAssertTrue(missing.contains("pi-mono-extension/index.ts"), "\(missing)")
    XCTAssertTrue(missing.contains("pi-mono-extension/node_modules"), "\(missing)")
  }

  func testAMissingAgentDependencyTreeIsReported() throws {
    try remove("agent/node_modules")
    XCTAssertEqual(
      AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath),
      ["agent/node_modules"])
  }

  func testAMissingCompiledToolManifestIsReportedBeforeAnySpawn() throws {
    try remove("agent/dist/runtime/omi-tool-manifest.js")
    XCTAssertEqual(
      AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath),
      ["agent/dist/runtime/omi-tool-manifest.js"])
  }

  /// A partially-copied bundle leaves the directory behind with nothing in it.
  func testAnEmptyDependencyTreeIsAsUnusableAsAMissingOne() throws {
    try remove("pi-mono-extension/node_modules/@omi/placeholder/package.json")
    try remove("pi-mono-extension/node_modules/@omi/placeholder")
    try remove("pi-mono-extension/node_modules/@omi")
    XCTAssertEqual(
      AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath),
      ["pi-mono-extension/node_modules"])
  }

  func testATruncatedExtensionEntryPointIsReported() throws {
    try write("pi-mono-extension/index.ts", contents: "")
    XCTAssertEqual(
      AgentRuntimePayload.missingComponents(bridgeScriptPath: bridgeScriptPath),
      ["pi-mono-extension/index.ts"])
  }

  // MARK: - What the person holding the keyboard is told

  func testTheIncompletePayloadErrorNamesTheRepairAndNeverAProcessName() {
    let error = BridgeError.agentRuntimePayloadIncomplete(missing: ["pi-mono-extension/index.ts"])
    let message = error.localizedDescription

    XCTAssertTrue(message.lowercased().contains("local ai runtime"), message)
    XCTAssertFalse(message.lowercased().contains("pi-mono process"), message)
    XCTAssertFalse(message.contains("exit"), message)

    let classified = AgentErrorClassifier.classify(message)
    XCTAssertEqual(
      classified.code, .runtimeInstallIncomplete,
      "the surfaces re-classify this description, so it must stay on its own code")
    XCTAssertFalse(classified.retryable, "no number of retries repairs a broken install")
    XCTAssertFalse(
      classified.userMessage.lowercased().contains("try again"),
      "copy must not prescribe retries for a failure retrying cannot fix")
  }

  /// `.runtimeMissing` already routes the card's primary CTA to the runtime
  /// install/repair flow — an incomplete payload is the same recovery.
  func testAnIncompletePayloadOffersTheRepairRecovery() {
    let state = ChatErrorState.from(.agentRuntimePayloadIncomplete(missing: ["agent/node_modules"]))
    XCTAssertEqual(state, .bridgeUnavailable(reason: .runtimeMissing))
    XCTAssertEqual(state?.primaryRecovery, .installRuntime)
  }

  /// The one-line surfaces (floating bar / notch) get the same instruction as
  /// the card. "AI isn't available right now" reads as transient; this is not.
  func testTheCompactSummaryStillNamesAnInstallProblem() {
    let state = ChatErrorState.from(.agentRuntimePayloadIncomplete(missing: ["pi-mono-extension/index.ts"]))
    XCTAssertEqual(state?.userFacingSummary, "AI components aren't installed.")
    XCTAssertNotEqual(state?.userFacingSummary, "AI isn't available right now.")
  }

  func testTelemetryCarriesTheBoundedCodeAndNoPaths() {
    let detail = ChatQueryErrorDetail.from(
      BridgeError.agentRuntimePayloadIncomplete(missing: ["pi-mono-extension/index.ts"]))
    XCTAssertEqual(detail?.errorCode, "runtime_install_incomplete")
    XCTAssertEqual(detail?.retryable, false)
    XCTAssertNil(detail?.failureCode)
  }
}
