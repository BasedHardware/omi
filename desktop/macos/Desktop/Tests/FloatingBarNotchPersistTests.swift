import AppKit
import XCTest

@testable import Omi_Computer

/// Behavioral coverage for the notch vanishing until Push-to-Talk: cancelled
/// retract/reveal must not leave the island scaled into the camera housing,
/// Space switches must re-show an enabled bar AppKit ordered out, and demo
/// teardown must restore the user's durable presentation.
@MainActor
final class FloatingBarNotchPersistTests: XCTestCase {
  func testCancelledRetractWhileStillVisibleRestoresRevealProgress() {
    withForcedNotch {
      let window = makeBarWindow()
      defer { window.close() }
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      window.makeKeyAndOrderFront(nil)

      var staleCompletionCount = 0
      window.beginNotchRetraction { staleCompletionCount += 1 }
      XCTAssertEqual(window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.retractedProgress)
      window.notchRetractionGeneration &+= 1
      window.notchRetractionCancellation = nil

      XCTAssertTrue(scheduler.fireNext())
      XCTAssertEqual(staleCompletionCount, 0, "a cancelled retract must not order the panel out")
      XCTAssertEqual(window.state.notchRevealProgress, 1, accuracy: 0.001)
      XCTAssertTrue(window.isVisible, "the island must remain on-screen at full scale")
      window.orderOut(nil)
    }
  }

  func testInterruptedRevealForcesProgressBackToFullScale() {
    withForcedNotch {
      let window = makeBarWindow()
      defer { window.close() }
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      window.makeKeyAndOrderFront(nil)

      window.playNotchRevealAnimation()
      window.state.notchRevealProgress = FloatingBarNotchRevealPolicy.retractedProgress
      XCTAssertTrue(scheduler.fireNext())
      XCTAssertEqual(
        window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.revealedProgress, accuracy: 0.001,
        "reveal completion must force full scale if the SwiftUI animation never landed")

      window.playNotchRevealAnimation()
      window.state.notchRevealProgress = FloatingBarNotchRevealPolicy.retractedProgress
      window.notchRevealGeneration &+= 1
      window.notchRevealCancellation = nil
      XCTAssertTrue(scheduler.fireNext())
      XCTAssertEqual(
        window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.revealedProgress, accuracy: 0.001,
        "an interrupted reveal must not leave the island scaled into the camera housing")
      window.orderOut(nil)
    }
  }

  func testStaleRevealCompletionDoesNotSnapAnInFlightRevealToFullScale() {
    withForcedNotch {
      let window = makeBarWindow()
      defer { window.close() }
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      window.makeKeyAndOrderFront(nil)

      window.playNotchRevealAnimation()
      window.playNotchRevealAnimation()
      window.state.notchRevealProgress = FloatingBarNotchRevealPolicy.retractedProgress
      XCTAssertTrue(scheduler.fireNextIgnoringCancellation())
      XCTAssertEqual(
        window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.retractedProgress, accuracy: 0.001,
        "a stale reveal completion must not cut off the replacement grow-in")
      XCTAssertTrue(scheduler.fireNext())
      XCTAssertEqual(
        window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.revealedProgress, accuracy: 0.001)
      window.orderOut(nil)
    }
  }

  func testNoOpFrameAssertionDoesNotCancelAnInFlightRetract() {
    withForcedNotch {
      let window = makeBarWindow()
      defer { window.close() }
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      window.makeKeyAndOrderFront(nil)

      var completionCount = 0
      window.beginNotchRetraction { completionCount += 1 }
      let token = window.frameAnimationToken
      let generation = window.notchRetractionGeneration
      window.normalizeForTemporaryShow()

      XCTAssertEqual(
        window.frameAnimationToken, token,
        "a no-op resize must not share a cancellation token with retract/reveal")
      XCTAssertEqual(window.notchRetractionGeneration, generation)
      XCTAssertTrue(scheduler.fireNext())
      XCTAssertEqual(completionCount, 1, "the retract still finishes; hover did not abort it")
    }
  }

  func testSpaceChangeReShowsAnEnabledBarAppKitOrderedOut() {
    withForcedNotch {
      let manager = FloatingControlBarManager.shared
      let previousEnabled = manager.isEnabled
      let previousSnooze = manager.snoozedUntil
      let previousRevealed = manager.hasRevealedNotchThisSession
      manager.isEnabled = true
      manager.snoozedUntil = nil
      manager.hasRevealedNotchThisSession = true
      defer {
        manager.isEnabled = previousEnabled
        manager.snoozedUntil = previousSnooze
        manager.hasRevealedNotchThisSession = previousRevealed
      }

      let window = makeBarWindow()
      defer { window.close() }
      window.orderOut(nil)
      XCTAssertFalse(window.isVisible)

      window.performSpacesTransitionGrowIn()

      XCTAssertTrue(window.isVisible, "an enabled bar ordered out by a Space switch must come back")
      XCTAssertEqual(window.state.notchRevealProgress, 1, accuracy: 0.001)
      window.orderOut(nil)
    }
  }

  func testSpaceChangeDoesNotShowADisabledOrSnoozedBar() {
    withForcedNotch {
      let manager = FloatingControlBarManager.shared
      let previousEnabled = manager.isEnabled
      let previousSnooze = manager.snoozedUntil
      let previousRevealed = manager.hasRevealedNotchThisSession
      manager.hasRevealedNotchThisSession = true
      defer {
        manager.isEnabled = previousEnabled
        manager.snoozedUntil = previousSnooze
        manager.hasRevealedNotchThisSession = previousRevealed
      }

      let window = makeBarWindow()
      defer { window.close() }

      manager.isEnabled = false
      manager.snoozedUntil = nil
      window.orderOut(nil)
      window.performSpacesTransitionGrowIn()
      XCTAssertFalse(window.isVisible, "a settings-hidden bar must stay hidden after a Space switch")

      manager.isEnabled = true
      manager.snoozedUntil = Date().addingTimeInterval(3_600)
      window.orderOut(nil)
      window.performSpacesTransitionGrowIn()
      XCTAssertFalse(window.isVisible, "a snoozed bar must stay hidden after a Space switch")

      manager.snoozedUntil = nil
      manager.hasRevealedNotchThisSession = false
      window.orderOut(nil)
      window.performSpacesTransitionGrowIn()
      XCTAssertFalse(
        window.isVisible,
        "deferred-until-PTT launch must not show the notch just because the Space changed")
    }
  }

  func testOnboardingDemoTeardownRestoresAnEnabledBarWithoutPersistingAHide() {
    withForcedNotch {
      let manager = FloatingControlBarManager.shared
      let previousWindow = manager.window
      let previousEnabled = manager.isEnabled
      let previousSnooze = manager.snoozedUntil
      let previousRevealed = manager.hasRevealedNotchThisSession
      let window = makeBarWindow()
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      manager.window = window
      manager.isEnabled = true
      manager.snoozedUntil = nil
      manager.hasRevealedNotchThisSession = true
      defer {
        manager.window = previousWindow
        manager.isEnabled = previousEnabled
        manager.snoozedUntil = previousSnooze
        manager.hasRevealedNotchThisSession = previousRevealed
        window.close()
      }

      window.makeKeyAndOrderFront(nil)
      manager.hideForOnboardingDemo()
      XCTAssertTrue(manager.isEnabled, "demo teardown must not persist a hide")
      if scheduler.activeCount > 0 {
        XCTAssertTrue(scheduler.fireNext())
      }
      XCTAssertTrue(window.isVisible, "the durable enabled bar must come back after the demo retracts")
      window.orderOut(nil)
    }
  }

  func testCancelPendingDismissDoesNotLeaveRevealProgressCollapsed() {
    withForcedNotch {
      let window = makeBarWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)
      window.state.notchRevealProgress = FloatingBarNotchRevealPolicy.retractedProgress
      window.cancelPendingDismiss()
      XCTAssertEqual(
        window.state.notchRevealProgress, FloatingBarNotchRevealPolicy.revealedProgress, accuracy: 0.001,
        "opening a PTT query must not leave the island scaled into the camera housing")
      window.orderOut(nil)
    }
  }

  func testOnboardingDemoTeardownLeavesADisabledBarHidden() {
    withForcedNotch {
      let manager = FloatingControlBarManager.shared
      let previousWindow = manager.window
      let previousEnabled = manager.isEnabled
      let previousSnooze = manager.snoozedUntil
      let window = makeBarWindow()
      let scheduler = ManualDelayedActionScheduler()
      window.notchRetractionScheduler = scheduler
      manager.window = window
      manager.isEnabled = false
      manager.snoozedUntil = nil
      defer {
        manager.window = previousWindow
        manager.isEnabled = previousEnabled
        manager.snoozedUntil = previousSnooze
        window.close()
      }

      window.makeKeyAndOrderFront(nil)
      manager.hideForOnboardingDemo()
      XCTAssertFalse(manager.isEnabled)
      if scheduler.activeCount > 0 {
        XCTAssertTrue(scheduler.fireNext())
      }
      XCTAssertFalse(window.isVisible, "a disabled bar must stay hidden after demo teardown")
    }
  }

  func testOnboardingDemoTeardownWithoutAWindowDoesNotMarkTheNotchRevealed() {
    let manager = FloatingControlBarManager.shared
    let previousWindow = manager.window
    let previousEnabled = manager.isEnabled
    let previousSnooze = manager.snoozedUntil
    let previousRevealed = manager.hasRevealedNotchThisSession
    manager.window = nil
    manager.isEnabled = true
    manager.snoozedUntil = nil
    manager.hasRevealedNotchThisSession = false
    defer {
      manager.window = previousWindow
      manager.isEnabled = previousEnabled
      manager.snoozedUntil = previousSnooze
      manager.hasRevealedNotchThisSession = previousRevealed
    }

    manager.hideForOnboardingDemo()
    XCTAssertFalse(
      manager.hasRevealedNotchThisSession,
      "teardown with no panel must not skip a later deferred notched launch")
  }

  private func makeBarWindow() -> FloatingControlBarWindow {
    FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
  }

  private func withForcedNotch(_ body: () -> Void) {
    let previousForceNoNotch = getenv("OMI_FORCE_NO_NOTCH").map { String(cString: $0) }
    let previousForceNotch = getenv("OMI_FORCE_NOTCH").map { String(cString: $0) }
    let previousDraggableBarEnabled = ShortcutSettings.shared.draggableBarEnabled
    ShortcutSettings.shared.draggableBarEnabled = false
    unsetenv("OMI_FORCE_NO_NOTCH")
    setenv("OMI_FORCE_NOTCH", "1", 1)
    defer {
      ShortcutSettings.shared.draggableBarEnabled = previousDraggableBarEnabled
      if let previousForceNoNotch {
        setenv("OMI_FORCE_NO_NOTCH", previousForceNoNotch, 1)
      } else {
        unsetenv("OMI_FORCE_NO_NOTCH")
      }
      if let previousForceNotch {
        setenv("OMI_FORCE_NOTCH", previousForceNotch, 1)
      } else {
        unsetenv("OMI_FORCE_NOTCH")
      }
    }
    body()
  }
}
