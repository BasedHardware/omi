import AppKit
import XCTest

@testable import Omi_Computer

/// Typing with no field focused used to produce the system alert sound: the keystroke fell off the
/// end of the responder chain and AppKit's `noResponderFor(keyDown:)` beeped. Both chains the app
/// owns — the application chain SwiftUI windows drain into (capped by `UnhandledKeystrokeSink`) and
/// the floating panel (which has no window controller and ends at itself) — must absorb an
/// unhandled key instead of forwarding it.
@MainActor
final class UnhandledKeystrokeSilenceTests: XCTestCase {
  /// Sits after the responder under test; if it hears the key, the key fell through.
  private final class NextResponderProbe: NSResponder {
    private(set) var forwardedKeys = 0
    override func keyDown(with event: NSEvent) { forwardedKeys += 1 }
  }

  private func plainKey(_ character: String, keyCode: UInt16 = 0) throws -> NSEvent {
    try XCTUnwrap(
      NSEvent.keyEvent(
        with: .keyDown, location: .zero, modifierFlags: [], timestamp: 0, windowNumber: 0,
        context: nil, characters: character, charactersIgnoringModifiers: character,
        isARepeat: false, keyCode: keyCode))
  }

  func testAProbeAfterAPlainResponderHearsTheKeyItForwards() throws {
    // The control: proves the probe measures forwarding at all, so a silent delegate below is a
    // result and not a broken probe.
    let plain = NSResponder()
    let probe = NextResponderProbe()
    plain.nextResponder = probe
    plain.keyDown(with: try plainKey("a"))
    XCTAssertEqual(probe.forwardedKeys, 1)
  }

  func testTheSinkAbsorbsAKeyNothingElseHandled() throws {
    let sink = UnhandledKeystrokeSink()
    let probe = NextResponderProbe()
    sink.nextResponder = probe
    sink.keyDown(with: try plainKey("a"))
    XCTAssertEqual(probe.forwardedKeys, 0, "an unhandled keystroke must end at the sink; forwarding it is what beeps")
  }

  func testInstallCapsTheEndOfTheChainExactlyOnce() throws {
    let root = NSResponder()
    let middle = NSResponder()
    root.nextResponder = middle

    UnhandledKeystrokeSink.install(after: root)
    XCTAssertTrue(
      middle.nextResponder is UnhandledKeystrokeSink, "the sink goes after the last responder, not after the root")

    UnhandledKeystrokeSink.install(after: root)
    XCTAssertNil(middle.nextResponder?.nextResponder, "a second install must not stack a second sink")
  }

  func testTheFloatingPanelAbsorbsUnhandledKeysButStillActsOnEscape() throws {
    let window = FloatingControlBarWindow(
      contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    defer { window.close() }
    let probe = NextResponderProbe()
    window.nextResponder = probe

    window.keyDown(with: try plainKey("a"))
    XCTAssertEqual(probe.forwardedKeys, 0, "a plain key with no field focused must not leave the panel")

    window.state.showingAIConversation = true
    window.state.aiInputText = "draft"
    window.keyDown(with: try plainKey("\u{1B}", keyCode: 53))
    XCTAssertEqual(window.state.aiInputText, "", "Escape is still the panel's own key")
    XCTAssertEqual(probe.forwardedKeys, 0)

    // Tab is answered by the window itself (key-view navigation) rather than forwarded.
    window.keyDown(with: try plainKey("\t", keyCode: 48))
    XCTAssertEqual(probe.forwardedKeys, 0)
  }
}
