import XCTest

@testable import Omi_Computer

/// Regression coverage for the global Open-Omi shortcut (⌃⌘O) failing to bring the
/// app to the foreground.
///
/// Root cause: the summon call sites resolved the delegate with
/// `NSApp.delegate as? AppDelegate`. Under SwiftUI's `@NSApplicationDelegateAdaptor`,
/// `NSApp.delegate` is an internal forwarding delegate (`Optional<NSApplicationDelegate>`),
/// so that cast is `nil` — the `?.openMainAppWindow()` call silently no-oped and the
/// app never activated. (Only the sibling `.navigateToChat` post ran, which is why the
/// window's screen changed but the app stayed in the background.)
///
/// The fix routes every summon through `AppDelegate.summonWindowTarget()`, which
/// returns the published `AppDelegate.shared` instance. These tests lock that in: if
/// anyone reverts the resolver to the `NSApp.delegate` cast, it resolves to `nil` (the
/// test host has no `AppDelegate` on `NSApp.delegate`) and the assertions fail.
@MainActor
final class OpenOmiShortcutSummonRoutingTests: XCTestCase {
  func testSummonWindowTargetResolvesViaSharedReference() {
    let previous = AppDelegate.shared
    defer { AppDelegate.shared = previous }

    let delegate = AppDelegate()
    AppDelegate.shared = delegate

    XCTAssertTrue(
      AppDelegate.summonWindowTarget() === delegate,
      "The Open-Omi shortcut / floating bar summon must resolve the delegate through AppDelegate.shared. "
        + "Using `NSApp.delegate as? AppDelegate` (nil under SwiftUI's delegate adaptor) silently no-ops the summon."
    )
  }

  func testSummonWindowTargetIsNilWhenNoSharedDelegatePublished() {
    let previous = AppDelegate.shared
    defer { AppDelegate.shared = previous }

    AppDelegate.shared = nil
    XCTAssertNil(
      AppDelegate.summonWindowTarget(),
      "With no published delegate there is nothing to summon; the resolver must reflect that rather than crash."
    )
  }

  func testPublishedSharedDelegateIsIndependentOfNSAppDelegate() {
    // The whole point of AppDelegate.shared is that it does NOT depend on
    // NSApp.delegate. Setting it must take effect immediately, regardless of whatever
    // (if anything) AppKit has installed as the application delegate.
    let previous = AppDelegate.shared
    defer { AppDelegate.shared = previous }

    let a = AppDelegate()
    let b = AppDelegate()
    AppDelegate.shared = a
    XCTAssertTrue(AppDelegate.summonWindowTarget() === a)
    AppDelegate.shared = b
    XCTAssertTrue(AppDelegate.summonWindowTarget() === b)
  }
}
