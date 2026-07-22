import XCTest

@testable import Omi_Computer

/// Close-semantics alignment for the redesigned Home stage (home-stage S6
/// regression): the automation bridge's `home_close_panel` must follow the same
/// path as Esc / click-outside / the connect × button (collapse to the resting
/// surface), and the deferred ask-field focus must be fenced so a stale focus
/// cannot reopen chat.
///
/// Behavioral coverage: the bridge assertions run the real
/// `DesktopAutomationActionRegistry` (the production seam), and the deferred
/// focus policy itself is unit-tested in `HomeAskFocusPolicyTests`. The
/// `DashboardPage` assertions below are static-contract tripwires over wiring
/// that lives in `@State`/`@FocusState` and so cannot be driven without a
/// booted SwiftUI view — they supplement, not replace, the behavioral coverage.
@MainActor
final class HomeStageCloseSemanticsTests: XCTestCase {
  // MARK: Bridge (production seam — behavioral)

  func testHomeClosePanelIsRegistered() {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let names = Set(registry.descriptors().map(\.name))
    XCTAssertTrue(names.contains("home_close_panel"))
  }

  func testHomeClosePanelSummaryAlignsWithUserCollapse() throws {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let descriptor = try XCTUnwrap(
      registry.descriptors().first { $0.name == "home_close_panel" })

    XCTAssertTrue(descriptor.summary.contains("resting surface"), descriptor.summary)
    XCTAssertFalse(
      descriptor.summary.contains("back to the hub"),
      "The bridge must not claim a hub jump it no longer performs: \(descriptor.summary)")
  }

  func testHomeClosePanelPostsStageCloseNotification() async throws {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let expectation = self.expectation(
      forNotification: .homeStageClose, object: nil)

    _ = try await registry.perform("home_close_panel", params: [:])

    await fulfillment(of: [expectation], timeout: 2.0)
  }

  // MARK: Flow (static contract over DashboardPage wiring)

  /// hub → chat → connect → close must collapse to the resting surface, and a
  /// later `home_ask` must rest in chat — never force-jump to the hub.
  func testAutomationCloseRoutesToUserCollapseNotHubJump() throws {
    let source = try dashboardSource()

    XCTAssertFalse(
      source.contains("closeHomeStagePanel"),
      "The divergent hub-jump close path must stay gone; close routes through collapseHomeStagePanel")

    let closeHandler = try XCTUnwrap(source.range(of: ".homeStageClose"))
    let handlerSlice = source[closeHandler.lowerBound...].prefix(300)
    XCTAssertTrue(
      handlerSlice.contains("collapseHomeStagePanel()"),
      "home_close_panel must call the same collapse the on-screen controls call")
  }

  /// The deferred focus must fence itself: capture a generation token, drop on
  /// invalidate, and never land off the chat stage. Collapse and connect must
  /// both invalidate it.
  func testDeferredFocusFenceIsWired() throws {
    let source = try dashboardSource()

    XCTAssertTrue(
      source.contains("guard homeAskFocusPolicy.isCurrent(token), homeMode == .chat else { return }"),
      "A deferred focus must drop itself if invalidated and never land on a non-chat stage")

    let invalidateCount = source.components(separatedBy: "homeAskFocusPolicy.invalidate()").count - 1
    XCTAssertEqual(
      invalidateCount, 2,
      "Both collapseHomeStagePanel and toggleHomeConnectPanel must invalidate deferred focus")
  }

  /// Asking (via the ask bar) opens chat and rests there; the resting surface
  /// is chat, not the greeting hub.
  func testHomeRestingModeIsChatSoAskingRestsInChat() throws {
    let source = try dashboardSource()

    let resting = try computedPropertyBody(named: "homeRestingMode", in: source)
    XCTAssertEqual(resting.trimmingCharacters(in: .whitespacesAndNewlines), ".chat")

    let ask = try methodBody(named: "sendFromHomeAskBar", in: source)
    XCTAssertTrue(
      ask.contains("openHomeChat(focusInput: false)"),
      "Sending from the ask bar must open the chat surface, where it rests")
  }

  // MARK: Helpers

  private func dashboardSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let dashboardURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
    // omi-test-quality: source-inspection -- static contract: DashboardPage stage-close and deferred-focus wiring lives in SwiftUI @State/@FocusState and cannot be driven without a booted view
    return try String(contentsOf: dashboardURL, encoding: .utf8)
  }

  private func methodBody(named name: String, in source: String) throws -> String {
    let pattern = #"private func \#(name)\([^\)]*\)[^{]*\{([\s\S]*?)\n\s+\}"#
    let regex = try NSRegularExpression(pattern: pattern)
    let range = NSRange(source.startIndex..<source.endIndex, in: source)
    let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
    let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
    return String(source[bodyRange])
  }

  private func computedPropertyBody(named name: String, in source: String) throws -> String {
    let pattern = #"private var \#(name): [^{]+\{([\s\S]*?)\n\s+\}"#
    let regex = try NSRegularExpression(pattern: pattern)
    let range = NSRange(source.startIndex..<source.endIndex, in: source)
    let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
    let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
    return String(source[bodyRange])
  }
}
