import AppKit
import XCTest

@testable import Omi_Computer

/// Exercises the production presenter, including its text-input focus path.
/// The window spy records AppKit focus requests without changing the test runner's focus.
@MainActor
final class FloatingBarPassiveFocusTests: XCTestCase {
  private final class FocusWindow: FloatingControlBarWindow {
    var keyRequests = 0
    var inputRequests = 0
    var passiveOrders = 0

    override func makeKeyAndOrderFront(_ sender: Any?) { keyRequests += 1 }
    override func orderFrontRegardless() { passiveOrders += 1 }
    override func focusInputField() -> Bool {
      inputRequests += 1
      return true
    }
  }

  func testBackgroundRevealNeverFocusesAnOpenInput() {
    withWindow { manager, window in
      window.state.showingAIConversation = true
      window.state.showingAIResponse = false
      manager.present(.background, preferenceMutation: .preserve)
      XCTAssertEqual(window.passiveOrders, 1)
      XCTAssertEqual(window.keyRequests, 0)
      XCTAssertEqual(window.inputRequests, 0, "the input helper itself makes the panel key")
    }
  }

  func testExplicitRevealStillFocusesTheOpenInput() {
    withWindow { manager, window in
      window.state.showingAIConversation = true
      window.state.showingAIResponse = false
      manager.present(.explicitUserAction, preferenceMutation: .preserve)
      XCTAssertEqual(window.keyRequests, 1)
      XCTAssertEqual(window.inputRequests, 1)
    }
  }

  func testSnoozeExpiryAndTemporaryRevealDoNotAcquireFocus() {
    withWindow { manager, window in
      manager.snoozedUntil = Date().addingTimeInterval(3600)
      manager.endSnooze()
      manager.showTemporarily()
      XCTAssertNil(manager.snoozedUntil)
      XCTAssertEqual(window.passiveOrders, 2)
      XCTAssertEqual(window.keyRequests, 0)
      XCTAssertEqual(window.inputRequests, 0)
    }
  }

  private func withWindow(_ body: (FloatingControlBarManager, FocusWindow) -> Void) {
    let manager = FloatingControlBarManager.shared
    let previousWindow = manager.window
    let previousEnabled = manager.isEnabled
    let previousSnooze = manager.snoozedUntil
    let previousRevealed = manager.hasRevealedNotchThisSession
    let window = FocusWindow(
      contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    manager.window = window
    manager.isEnabled = true
    manager.snoozedUntil = nil
    defer {
      manager.window = previousWindow
      manager.isEnabled = previousEnabled
      manager.snoozedUntil = previousSnooze
      manager.hasRevealedNotchThisSession = previousRevealed
      window.close()
    }
    body(manager, window)
  }
}
