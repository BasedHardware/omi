import CoreGraphics
import XCTest

@testable import Omi_Computer

/// Counts calls from `@Sendable` closures.
private final class CallCounter: @unchecked Sendable {
  private let lock = NSLock()
  private var calls: [(pid: pid_t, checksSettingsPane: Bool, cancelled: Bool)] = []

  func record(_ pid: pid_t, _ checksSettingsPane: Bool, cancelled: Bool) {
    lock.withLock { calls.append((pid, checksSettingsPane, cancelled)) }
  }

  var recorded: [(pid: pid_t, checksSettingsPane: Bool, cancelled: Bool)] { lock.withLock { calls } }
}

/// `ui_snapshot` as the chat tool executor runs it, against a fake system.
final class ChatToolExecutorUISnapshotTests: XCTestCase {
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = await RuntimeOwnerAuthorityTestFixture()
    await fixture.establish(authOwnerID: "ui-snapshot-owner")
    ownerFixture = fixture
  }

  override func tearDown() async throws {
    await MainActor.run { ChatToolExecutor.uiSnapshotEnvironment = .live }
    await ownerFixture?.restore()
    ownerFixture = nil
    try await super.tearDown()
  }

  private static let textEdit = UIAutomationRunningApp(
    pid: 812, bundleID: "com.apple.TextEdit", localizedName: "TextEdit",
    bundleURL: URL(fileURLWithPath: "/System/Applications/TextEdit.app"), isActive: false)

  nonisolated private static func fixtureWindows() -> [FixtureAXNode] {
    [
      axNode(
        "AXWindow", "Untitled", subrole: "AXStandardWindow", frame: CGRect(x: 100, y: 100, width: 800, height: 600),
        children: [
          axNode("AXButton", "Save", actions: ["AXPress"]),
          axNode("AXButton", "Bold", actions: ["AXPress"]),
          axNode("AXTextArea", description: "Document", value: .string("hello snapshot test"), settable: true),
          axNode("AXStaticText", value: .string("Ready")),
          axNode("AXCheckBox", "Ruler", value: .number(1), actions: ["AXPress"]),
        ]),
      axNode(
        "AXWindow", "Untitled 2", subrole: "AXStandardWindow", frame: CGRect(x: 100, y: 100, width: 800, height: 600)),
    ]
  }

  @MainActor
  private func install(
    trusted: Bool = true, running: [UIAutomationRunningApp] = [textEdit], excluded: Set<String> = [],
    counter: CallCounter = CallCounter(), processNowBelongsTo: String? = nil
  ) {
    ChatToolExecutor.uiSnapshotEnvironment = UISnapshotEnvironment(
      isAccessibilityTrusted: { trusted },
      runningApps: { running },
      isExcludedFromCapture: { excluded.contains($0) },
      isSecureInputActive: { false },
      ownPID: 1,
      assistiveTreeMode: { _ in .none },
      bundleIDOfProcess: { pid in processNowBelongsTo ?? running.first { $0.pid == pid }?.bundleID },
      snapshot: { target, request, isCancelled in
        counter.record(target.pid, target.checksSettingsPane, cancelled: isCancelled())
        let source = FixtureAccessibilitySource(windows: Self.fixtureWindows())
        return WindowSnapshotWalker(source: source, now: { 0 }, pause: { _ in }).snapshot(request)
      })
  }

  @MainActor
  private func run(_ arguments: [String: Any]) async throws -> [String: Any] {
    let json = await ChatToolExecutor.executeUISnapshot(arguments)
    return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any], json)
  }

  @MainActor
  func testAMissingPermissionAsksForAccessibility() async throws {
    install(trusted: false)

    let result = try await run(["bundle_id": "com.apple.TextEdit"])

    XCTAssertEqual(result["reason"] as? String, "accessibility_not_granted")
    XCTAssertEqual(result["next_tool"] as? String, "request_permission")
    XCTAssertEqual((result["next_tool_arguments"] as? [String: String])?["type"], "accessibility")
  }

  @MainActor
  func testAnApprovedAppReadsAsAWindowHeaderThenOneStringPerElement() async throws {
    let counter = CallCounter()
    install(counter: counter)

    let result = try await run(["bundle_id": "com.apple.textedit", "window_title": "Untitled"])

    XCTAssertEqual(result["ok"] as? Bool, true)
    let sections = try XCTUnwrap(result["sections"] as? [[String: Any]])
    XCTAssertEqual(sections.map { $0["name"] as? String }, ["window", "elements"])
    let window = try XCTUnwrap(sections[0]["items"] as? [String])
    XCTAssertTrue(window[0].hasPrefix("window bundle_id=com.apple.TextEdit pid=812 "), window[0])
    XCTAssertTrue(window[0].hasSuffix(#"app="TextEdit" window_title="Untitled""#), window[0])
    XCTAssertEqual(window.dropFirst().first, #"other_window window_id=4401 window_title="Untitled 2""#)
    let elements = try XCTUnwrap(sections[1]["items"] as? [String])
    XCTAssertTrue(elements.contains { $0.contains("value=\"hello snapshot test\" [set]") }, "\(elements)")
    XCTAssertTrue(elements.contains { $0.contains("\"Ruler\" value=on [press]") }, "\(elements)")
    XCTAssertEqual(counter.recorded.map(\.pid), [812])
    XCTAssertEqual(counter.recorded.map(\.checksSettingsPane), [false])
  }

  @MainActor
  func testRefusedAndExcludedAppsAreNeverRead() async throws {
    let counter = CallCounter()
    let terminal = UIAutomationRunningApp(
      pid: 900, bundleID: "com.apple.Terminal", localizedName: "Terminal",
      bundleURL: URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app"), isActive: false)
    install(running: [Self.textEdit, terminal], excluded: ["TextEdit"], counter: counter)

    let refused = try await run(["bundle_id": "com.apple.Terminal"])
    let excluded = try await run(["bundle_id": "com.apple.TextEdit"])

    XCTAssertEqual(refused["reason"] as? String, "refused_app")
    XCTAssertNil(refused["next_tool"], "a refusal is not something to retry")
    XCTAssertEqual(excluded["reason"] as? String, "refused_excluded_app")
    XCTAssertTrue(counter.recorded.isEmpty)
  }

  @MainActor
  func testTheTargetMustBeOneRunningCopyOfTheApprovedApp() async throws {
    let second = UIAutomationRunningApp(
      pid: 813, bundleID: "com.apple.TextEdit", localizedName: "TextEdit",
      bundleURL: URL(fileURLWithPath: "/System/Applications/TextEdit.app"), isActive: false)
    install(running: [Self.textEdit, second])

    let cases: [([String: Any], String)] = [
      (["bundle_id": "com.apple.TextEdit"], "ambiguous_app"),
      (["bundle_id": "com.apple.TextEdit", "pid": 900], "target_mismatch"),
      (["bundle_id": "com.apple.Notes"], "app_not_running"),
      (["bundle_id": "TextEdit"], "invalid_arguments"),
      (["bundle_id": "com.apple.TextEdit", "pid": Double.nan], "invalid_arguments"),
    ]
    for (arguments, reason) in cases {
      let result = try await run(arguments)
      XCTAssertEqual(result["reason"] as? String, reason, "\(arguments)")
    }
    let chosen = try await run(["bundle_id": "com.apple.TextEdit", "pid": 813])
    XCTAssertEqual(chosen["ok"] as? Bool, true)
  }

  @MainActor
  func testAnAmbiguousWindowListsTheWindowsToChooseFrom() async throws {
    install()

    let result = try await run(["bundle_id": "com.apple.TextEdit", "window_title": "untitl"])

    XCTAssertEqual(result["reason"] as? String, "window_ambiguous")
    XCTAssertEqual(
      result["windows"] as? [String],
      [#"window_id=4400 window_title="Untitled""#, #"window_id=4401 window_title="Untitled 2""#])
  }

  @MainActor
  func testSystemSettingsGetsItsPaneChecked() async throws {
    let counter = CallCounter()
    let settings = UIAutomationRunningApp(
      pid: 700, bundleID: "com.apple.systempreferences", localizedName: "System Settings",
      bundleURL: URL(fileURLWithPath: "/System/Applications/System Settings.app"),
      isActive: false)
    install(running: [settings], counter: counter)

    _ = try await run(["bundle_id": "com.apple.systempreferences"])

    XCTAssertEqual(counter.recorded.map(\.checksSettingsPane), [true])
  }

  @MainActor
  func testUnusableNumbersAreClampedNotTrusted() {
    let huge = ChatToolExecutor.uiSnapshotRequest(
      ["max_nodes": 1e100, "window_id": Double.nan, "window_title": String(repeating: "x", count: 1_000)],
      assistiveTree: .none)
    XCTAssertEqual(huge.limits.maxNodes, 400)
    XCTAssertNil(huge.windowID)
    XCTAssertEqual(huge.windowTitle?.count, 256)

    XCTAssertEqual(ChatToolExecutor.uiSnapshotRequest(["max_nodes": 0], assistiveTree: .none).limits.maxNodes, 1)
    XCTAssertEqual(ChatToolExecutor.uiSnapshotRequest(["max_nodes": 5_000], assistiveTree: .none).limits.maxNodes, 400)
    XCTAssertEqual(ChatToolExecutor.uiSnapshotRequest(["max_nodes": 50.0], assistiveTree: .none).limits.maxNodes, 50)
    XCTAssertEqual(ChatToolExecutor.uiSnapshotRequest(["window_id": 4_401], assistiveTree: .none).windowID, 4_401)
  }

  @MainActor
  func testWindowTitlesAndTheAppAreLoggedByShapeOnly() {
    let summary = ChatToolExecutor.redactedArgumentSummary(
      for: ToolCall(
        name: "ui_snapshot", arguments: ["bundle_id": "com.apple.TextEdit", "window_title": "Chat with Ria"],
        thoughtSignature: nil))

    XCTAssertFalse(summary.contains("Ria"))
    XCTAssertFalse(summary.contains("com.apple.TextEdit"))
    XCTAssertTrue(summary.contains("window_title=<13 chars>"))
  }

  @MainActor
  func testTheChatDispatchRunsTheExecutorBehindTheOwnerBind() async throws {
    let counter = CallCounter()
    install(trusted: false, counter: counter)
    let call = ToolCall(name: "ui_snapshot", arguments: ["bundle_id": "com.apple.TextEdit"], thoughtSignature: nil)

    let dispatched = await ChatToolExecutor.execute(call)
    let otherOwner = await ChatToolExecutor.execute(call, expectedOwnerID: "a-different-owner")

    XCTAssertTrue(dispatched.contains("accessibility_not_granted"), dispatched)
    XCTAssertTrue(otherOwner.contains("authorized_execution_owner_changed"), otherOwner)
    XCTAssertTrue(counter.recorded.isEmpty)
  }

  @MainActor
  func testAProcessThatNoLongerBelongsToTheApprovedAppIsNotReported() async throws {
    install(processNowBelongsTo: "com.example.other")

    let result = try await run(["bundle_id": "com.apple.TextEdit"])

    XCTAssertEqual(result["reason"] as? String, "target_changed")
  }

  @MainActor
  func testCancellingTheCallReachesTheDetachedRead() async throws {
    let counter = CallCounter()
    install(counter: counter)

    let task = Task { @MainActor in await ChatToolExecutor.executeUISnapshot(["bundle_id": "com.apple.TextEdit"]) }
    task.cancel()
    _ = await task.value

    XCTAssertEqual(counter.recorded.map(\.cancelled), [true])
  }
}
