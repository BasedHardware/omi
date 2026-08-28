import XCTest

@testable import Omi_Computer

/// A browser keeps one window and one window id across every tab, so the window alone
/// cannot say what a panel is about. These are the comparisons that decide whether a
/// panel stays on screen.
final class PanelContextTests: XCTestCase {
  private func context(
    app: String = "Safari",
    windowID: CGWindowID? = 42,
    title: String = "Job Application",
    url: String = "https://example.com/apply"
  ) -> PanelContext {
    PanelContext(appName: app, windowID: windowID, windowTitle: title, pageURL: url)
  }

  func testTheSameTabMatches() {
    XCTAssertTrue(context().matches(context(), grain: .context))
  }

  func testASwitchedTabDoesNotMatch() {
    let other = context(title: "Inbox", url: "https://mail.example.com/inbox")
    XCTAssertFalse(context().matches(other, grain: .context))
  }

  /// Two tabs can share a title. The URL is what separates them, and it is the reason
  /// the sweep pays for a tree walk the raw event channel does not.
  func testTabsSharingATitleAreSeparatedByURL() {
    let other = context(url: "https://example.com/apply?step=2")
    XCTAssertFalse(context().matches(other, grain: .context))
    XCTAssertTrue(context().matches(other, grain: .context, comparingPageURL: false))
  }

  /// Navigating inside a single-page app changes the URL and nothing else. That is a
  /// different page, so it is a different context.
  func testInPageNavigationIsADifferentContext() {
    let thread = context(app: "Safari", title: "Inbox", url: "https://mail.google.com/#inbox/a1")
    let other = context(app: "Safari", title: "Inbox", url: "https://mail.google.com/#inbox/b2")
    XCTAssertFalse(thread.matches(other, grain: .context))
  }

  /// A panel about the user rather than the screen only cares which app it is over.
  func testAppGrainIgnoresTabsAndWindows() {
    let other = context(windowID: 99, title: "Something else", url: "https://other.example")
    XCTAssertTrue(context().matches(other, grain: .app))
    XCTAssertFalse(context().matches(context(app: "Mail"), grain: .app))
  }

  /// A conversation is the window title in apps that rename themselves per thread, and
  /// changing conversation has to take a draft panel with it.
  func testANativeAppRenamingItselfPerThreadIsADifferentContext() {
    let david = context(app: "Telegram", title: "David Zhang", url: "")
    let sarah = context(app: "Telegram", title: "Sarah Lin", url: "")
    XCTAssertFalse(david.matches(sarah, grain: .context))
  }

  /// Accessibility can withhold the URL. The title still changes per tab, so the panel
  /// keeps working rather than treating every event as a context change.
  func testAMissingURLFallsBackToTheTitle() {
    let known = context(url: "https://example.com/apply")
    let unread = context(url: "")
    XCTAssertTrue(known.matches(unread, grain: .context))
    XCTAssertFalse(known.matches(context(title: "Other", url: ""), grain: .context))
  }
}

/// The panel opens in the same corner every time until the user moves it, and their
/// choice outlives the launch that produced it.
@MainActor
final class PanelPlacementStoreTests: XCTestCase {
  private let visible = CGRect(x: 0, y: 0, width: 1_512, height: 950)

  override func setUp() async throws {
    try await super.setUp()
    PanelPlacementStore.offset = nil
  }

  override func tearDown() async throws {
    PanelPlacementStore.offset = nil
    try await super.tearDown()
  }

  func testNothingIsRememberedUntilAPanelMoves() {
    XCTAssertNil(PanelPlacementStore.offset)
  }

  func testADragIsRememberedAsAnOffsetFromTheCorner() throws {
    let dragged = CGRect(x: 200, y: 300, width: 460, height: 216)
    PanelPlacementStore.record(panelFrame: dragged, visibleFrame: visible)
    let offset = try XCTUnwrap(PanelPlacementStore.offset)
    XCTAssertEqual(offset.width, dragged.maxX - (visible.maxX - FormAssistCardPlacement.margin))
    XCTAssertEqual(offset.height, dragged.maxY - (visible.maxY - FormAssistCardPlacement.margin))
  }

  /// Nudging a panel a few points is not choosing a place for it, and dragging one back
  /// to the corner is choosing the default rather than pinning it twice over.
  func testAMoveBackToTheCornerClearsTheMemory() {
    PanelPlacementStore.record(
      panelFrame: CGRect(x: 200, y: 300, width: 460, height: 216), visibleFrame: visible)
    XCTAssertNotNil(PanelPlacementStore.offset)

    let corner = FormAssistCardPlacement.frame(
      cardSize: CGSize(width: 460, height: 216), visibleFrame: visible)
    PanelPlacementStore.record(panelFrame: corner, visibleFrame: visible)
    XCTAssertNil(PanelPlacementStore.offset)
  }

  /// What is recorded is what the next panel opens at.
  func testARecordedPositionIsWhereTheNextPanelOpens() {
    let size = CGSize(width: 460, height: 216)
    let dragged = CGRect(x: 300, y: 400, width: size.width, height: size.height)
    PanelPlacementStore.record(panelFrame: dragged, visibleFrame: visible)
    XCTAssertEqual(
      FormAssistCardPlacement.frame(
        cardSize: size, visibleFrame: visible, offset: PanelPlacementStore.offset),
      dragged)
  }
}
