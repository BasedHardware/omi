import AppKit
import XCTest

@testable import Omi_Computer

/// "Which display is the user on?" — asserted as arithmetic, because the answer only ever goes wrong
/// on a second display and a CI runner has one screen.
///
/// The bug these exist for: the onboarding cinematic is a full-screen scrim that hands straight off
/// to the onboarding window, and it used to choose its display by asking where the *pointer* was
/// while the window that follows it chose by asking where the key window was. On a desk with a
/// laptop and an external monitor those disagree whenever the pointer is parked on the idle screen,
/// so the 8.6-second intro played in full — the log said so — to a monitor nobody was looking at.
final class ActiveDisplayTests: XCTestCase {

  // Two displays, indices as they would arrive in `NSScreen.screens`.
  private let onboardingDisplay = 0
  private let idleDisplay = 1

  // MARK: - The regression

  /// **The bug.** The onboarding window is headed for display A because that is where the key window
  /// is; the pointer happens to be resting on display B. The intro must open on A.
  func testAPointerOnAnotherDisplayDoesNotWinOverTheWindowTheUserIsTyping() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: onboardingDisplay,
      mainWindowScreen: onboardingDisplay,
      focusedScreen: onboardingDisplay,
      pointerScreen: idleDisplay)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: onboardingDisplay, source: .keyWindow))
  }

  /// The same claim with the pointer as the only *other* signal: even when AppKit has no opinion
  /// about focus, a window on screen still beats a parked cursor.
  func testAWindowOnScreenBeatsTheCursorEvenWithNoFocusedDisplay() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: nil,
      mainWindowScreen: onboardingDisplay,
      focusedScreen: nil,
      pointerScreen: idleDisplay)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: onboardingDisplay, source: .mainWindow))
  }

  /// And with only AppKit's focused display left: still not the cursor.
  func testTheFocusedDisplayBeatsTheCursor() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: nil,
      mainWindowScreen: nil,
      focusedScreen: onboardingDisplay,
      pointerScreen: idleDisplay)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: onboardingDisplay, source: .focused))
  }

  // MARK: - Ordering

  /// The key window outranks the frontmost window. They differ exactly when a panel or a second
  /// window has the keystrokes, and the keystrokes are the user.
  func testTheKeyWindowOutranksTheFrontmostWindow() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: idleDisplay,
      mainWindowScreen: onboardingDisplay,
      focusedScreen: onboardingDisplay,
      pointerScreen: onboardingDisplay)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: idleDisplay, source: .keyWindow))
  }

  /// The pointer's one job: the app has no window anywhere, so the cursor is the only evidence of
  /// the user there is. It still has to beat picking a display by array index.
  func testTheCursorIsUsedOnlyWhenTheAppHasNoWindowAtAll() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: nil,
      mainWindowScreen: nil,
      focusedScreen: nil,
      pointerScreen: idleDisplay)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: idleDisplay, source: .pointer))
  }

  /// Nothing to go on — off-screen pointer, no windows, displays asleep. Something still has to be
  /// chosen, or the caller has no surface to draw on.
  func testWithNoSignalAtAllTheFirstAttachedDisplayIsChosen() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: nil,
      mainWindowScreen: nil,
      focusedScreen: nil,
      pointerScreen: nil)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: 0, source: .firstAttached))
  }

  // MARK: - Displays that moved under us

  /// A display can be unplugged between reading a window's screen and reading the screen list. An
  /// index past the end is dropped and the next signal answers, rather than indexing off the array.
  func testAnIndexPastTheEndOfTheScreenListFallsThroughToTheNextSignal() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 1,
      keyWindowScreen: 7,
      mainWindowScreen: nil,
      focusedScreen: 0,
      pointerScreen: nil)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: 0, source: .focused))
  }

  func testANegativeIndexIsIgnored() {
    let choice = ActiveDisplayPolicy.choose(
      screenCount: 2,
      keyWindowScreen: -1,
      mainWindowScreen: idleDisplay,
      focusedScreen: nil,
      pointerScreen: nil)

    XCTAssertEqual(choice, ActiveDisplayPolicy.Choice(index: idleDisplay, source: .mainWindow))
  }

  /// No displays: there is no honest answer, and the cinematic's contract is to hand straight off to
  /// onboarding rather than invent one.
  func testNoDisplaysMeansNoChoice() {
    XCTAssertNil(
      ActiveDisplayPolicy.choose(
        screenCount: 0,
        keyWindowScreen: 0,
        mainWindowScreen: 0,
        focusedScreen: 0,
        pointerScreen: 0))
  }
}
