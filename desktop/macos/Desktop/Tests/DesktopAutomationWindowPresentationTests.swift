import AppKit
import XCTest

@testable import Omi_Computer

final class DesktopAutomationWindowPresentationTests: XCTestCase {
  private let display = NSRect(x: 0, y: 25, width: 1512, height: 875)

  @MainActor
  func testNonintrusiveTestWindowsStayRealWithoutOccupyingTheDesktop() {
    let window = NSWindow(
      contentRect: NSRect(x: 120, y: 120, width: 900, height: 600),
      styleMask: [.titled],
      backing: .buffered,
      defer: false)
    NonintrusiveTestWindow.orderIn(window)
    defer { window.orderOut(nil) }

    XCTAssertTrue(window.isVisible)
    XCTAssertTrue(window.ignoresMouseEvents)
    XCTAssertEqual(window.alphaValue, NonintrusiveTestWindow.alpha, accuracy: 0.0001)
    XCTAssertEqual(window.level, .normal)
    if let screen = window.screen ?? NSScreen.main {
      let visible = window.frame.intersection(screen.visibleFrame)
      XCTAssertLessThanOrEqual(visible.width, NonintrusiveTestWindow.peekSize.width)
      XCTAssertLessThanOrEqual(
        visible.height, 32,
        "AppKit may retain one title-bar-height column while constraining an ordered titled window")
    }
  }

  func testQuietPlacementLeavesOnlyTheBottomRightPeekOnScreen() {
    let frame = DesktopAutomationWindowPlacement.quietFrame(
      windowSize: NSSize(width: 960, height: 700),
      visibleFrame: display)
    let visible = frame.intersection(display)

    XCTAssertEqual(visible.size, DesktopAutomationWindowPlacement.quietPeekSize)
    XCTAssertEqual(visible.maxX, display.maxX)
    XCTAssertEqual(visible.minY, display.minY)
  }

  func testInteractivePlacementFitsOversizedWindowIntoBottomRightCorner() {
    let frame = DesktopAutomationWindowPlacement.interactiveFrame(
      windowSize: NSSize(width: 1800, height: 1200),
      visibleFrame: display)
    let available = display.insetBy(
      dx: DesktopAutomationWindowPlacement.interactiveMargin,
      dy: DesktopAutomationWindowPlacement.interactiveMargin)

    XCTAssertTrue(available.contains(frame))
    XCTAssertEqual(frame.maxX, available.maxX)
    XCTAssertEqual(frame.minY, available.minY)
  }

  func testAutomationUIPresentationIsExplicitAndFailsClosedForPublishedBundles() {
    XCTAssertEqual(
      DesktopAutomationLaunchOptions.uiPresentationMode(
        allowsLocalAutomation: true,
        arguments: ["omi", "--automation-ui=quiet"],
        environment: [DesktopAutomationLaunchOptions.uiPresentationEnvironmentKey: "interactive"]),
      .quiet,
      "argv must win over inherited launch environment")
    XCTAssertEqual(
      DesktopAutomationLaunchOptions.uiPresentationMode(
        allowsLocalAutomation: true,
        arguments: ["omi"],
        environment: [DesktopAutomationLaunchOptions.uiPresentationEnvironmentKey: "interactive"]),
      .interactive)
    XCTAssertEqual(
      DesktopAutomationLaunchOptions.uiPresentationMode(
        allowsLocalAutomation: false,
        arguments: ["omi", "--automation-ui=quiet"],
        environment: [:]),
      .normal,
      "published bundles must ignore local automation presentation flags")
    XCTAssertEqual(
      DesktopAutomationLaunchOptions.uiPresentationMode(
        allowsLocalAutomation: true,
        arguments: ["omi", "--automation-ui=unexpected"],
        environment: [:]),
      .normal,
      "an unknown presentation must never quietly alter a window")
  }

  @MainActor
  func testQuietInteractiveNormalRoundTripPreservesTheRealVisibleWindow() {
    let window = NSWindow(
      contentRect: NSRect(x: 120, y: 120, width: 960, height: 700),
      styleMask: [.titled, .closable, .resizable],
      backing: .buffered,
      defer: true)
    NonintrusiveTestWindow.prepareForOrdering(window, lockPosition: false)
    window.orderFrontRegardless()
    window.alphaValue = 1
    window.ignoresMouseEvents = false
    window.hasShadow = true
    let originalFrame = window.frame
    let originalLevel = window.level
    defer {
      DesktopAutomationWindowPresentation.setMode(.normal)
      window.orderOut(nil)
    }

    DesktopAutomationWindowPresentation.setMode(.quiet)

    XCTAssertTrue(window.isVisible, "quiet automation must preserve mounted/visible app semantics")
    XCTAssertTrue(window.ignoresMouseEvents)
    XCTAssertEqual(window.alphaValue, 0.04, accuracy: 0.001)
    XCTAssertEqual(window.level, .normal)

    DesktopAutomationWindowPresentation.setMode(.interactive)

    XCTAssertTrue(window.isVisible)
    XCTAssertFalse(window.ignoresMouseEvents)
    XCTAssertEqual(window.alphaValue, 1, accuracy: 0.001)
    if let screen = window.screen ?? NSScreen.main {
      XCTAssertTrue(screen.visibleFrame.contains(window.frame))
      XCTAssertEqual(
        window.frame.maxX,
        screen.visibleFrame.maxX - DesktopAutomationWindowPlacement.interactiveMargin,
        accuracy: 1)
    }

    XCTAssertTrue(DesktopAutomationWindowPresentation.revealForUser())

    XCTAssertEqual(window.frame, originalFrame)
    XCTAssertEqual(window.level, originalLevel)
    XCTAssertFalse(window.ignoresMouseEvents)
    XCTAssertEqual(DesktopAutomationWindowPresentation.currentMode, .normal)
  }

  @MainActor
  func testQuietPresentationAlsoParksNonactivatingOverlayPanels() {
    let panel = NSPanel(
      contentRect: NSRect(x: 180, y: 180, width: 420, height: 240),
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: true)
    panel.level = .screenSaver
    NonintrusiveTestWindow.prepareForOrdering(panel, lockPosition: false)
    panel.orderFrontRegardless()
    panel.alphaValue = 1
    panel.ignoresMouseEvents = false
    panel.hasShadow = true
    defer {
      DesktopAutomationWindowPresentation.setMode(.normal)
      panel.orderOut(nil)
    }

    DesktopAutomationWindowPresentation.setMode(.quiet)

    XCTAssertTrue(panel.isVisible)
    XCTAssertTrue(panel.ignoresMouseEvents)
    XCTAssertEqual(panel.level, .normal)
    XCTAssertEqual(panel.alphaValue, 0.04, accuracy: 0.001)
    if let screen = panel.screen ?? NSScreen.main {
      XCTAssertEqual(
        panel.frame.intersection(screen.visibleFrame).size,
        DesktopAutomationWindowPlacement.quietPeekSize)
    }
  }

  @MainActor
  func testAutomationActionReportsAndChangesPresentationMode() async throws {
    DesktopAutomationActionRegistry.shared.registerBuiltins()
    defer { DesktopAutomationWindowPresentation.setMode(.normal) }

    let quiet = try await DesktopAutomationActionRegistry.shared.perform(
      "set_automation_ui_presentation",
      params: ["mode": "quiet"])
    XCTAssertEqual(quiet?["mode"], "quiet")

    let snapshot = try await DesktopAutomationActionRegistry.shared.perform(
      "set_automation_ui_presentation",
      params: [:])
    XCTAssertEqual(snapshot?["mode"], "quiet")
    XCTAssertEqual(snapshot?["available_modes"], "normal,quiet,interactive")

    do {
      _ = try await DesktopAutomationActionRegistry.shared.perform(
        "set_automation_ui_presentation",
        params: ["mode": "unexpected"])
      XCTFail("unknown presentation modes must fail loudly")
    } catch let error as DesktopAutomationActionError {
      guard case .invalidParams = error else {
        return XCTFail("expected invalid params, got \(error)")
      }
    }
  }
}
