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

  // MARK: Connect toggle refuses a shell with no stage (production seam — behavioral)

  /// **A bridge action that answers "ok" and does nothing makes every verification that uses it a
  /// lie.** `home_connect_toggle` did exactly that on the query-shell Home from the moment that
  /// surface landed: it posted a notification only `DashboardPage` observes, and `DashboardPage` is
  /// not mounted there. The four sibling `home_*` actions were re-hosted in `QueryShellHome` because
  /// that surface still owns what they act on; this one has no Connect tray to toggle, so it refuses
  /// and names the page that does own connectors.
  ///
  /// The guard reads `homeMode`, which only the view that renders the stage writes — so the action's
  /// refusal and the state a flow asserts on can never disagree.
  func testConnectToggleRefusesAndPostsNothingWhenNoStageIsMounted() async throws {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let restore = DesktopAutomationStateStore.shared.current()
    defer { DesktopAutomationStateStore.shared.update(restore) }
    _ = DesktopAutomationStateStore.shared.updateLiveFields { $0.homeMode = nil }

    let notPosted = expectation(forNotification: .homeStageToggleConnect, object: nil)
    notPosted.isInverted = true

    let detail = try await registry.perform("home_connect_toggle", params: [:])

    let error = try XCTUnwrap(detail?["error"], "a shell with no stage must not report success")
    XCTAssertTrue(
      error.contains("Apps page"),
      "the refusal must name the surface that does own connectors: \(error)")
    await fulfillment(of: [notPosted], timeout: 0.5)
  }

  /// …and it still drives the real stage where one exists, through the same notification the ask
  /// bar's Connect button posts. The guard gates the action; it does not retire it.
  func testConnectToggleStillDrivesTheStageWhenOneIsMounted() async throws {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let restore = DesktopAutomationStateStore.shared.current()
    defer { DesktopAutomationStateStore.shared.update(restore) }
    _ = DesktopAutomationStateStore.shared.updateLiveFields { $0.homeMode = "hub" }

    let posted = expectation(forNotification: .homeStageToggleConnect, object: nil)

    let detail = try await registry.perform("home_connect_toggle", params: [:])

    XCTAssertNil(detail?["error"], "a mounted stage must not be refused")
    await fulfillment(of: [posted], timeout: 2.0)
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

  /// Asking (via the ask bar) opens chat. After history restoration, the
  /// resting surface follows the shared history-presentation policy.
  func testHomeRestingModeFollowsLoadedHistoryPolicy() throws {
    let source = try dashboardSource()

    let resting = try computedPropertyBody(named: "homeRestingMode", in: source)
    XCTAssertTrue(resting.contains("HomeHistoryPresentationPolicy.restingMode("))
    XCTAssertTrue(resting.contains("isLoading: chatProvider.isLoading"))
    XCTAssertTrue(resting.contains("messageCount: chatProvider.messages.count"))

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
    guard let declaration = source.range(of: "private func \(name)(") else {
      throw NSError(domain: "HomeStageCloseSemanticsTests", code: 1)
    }
    guard let openingBrace = source[declaration.upperBound...].firstIndex(of: "{") else {
      throw NSError(domain: "HomeStageCloseSemanticsTests", code: 2)
    }

    var depth = 0
    var cursor = openingBrace
    while cursor < source.endIndex {
      switch source[cursor] {
      case "{": depth += 1
      case "}":
        depth -= 1
        if depth == 0 {
          return String(source[source.index(after: openingBrace)..<cursor])
        }
      default: break
      }
      cursor = source.index(after: cursor)
    }
    throw NSError(domain: "HomeStageCloseSemanticsTests", code: 3)
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
