import AppKit
import XCTest

@testable import Omi_Computer

/// Typing on a page with nothing focused lands in the page's field — the search bar, or Chat's
/// composer — instead of being silently dropped. The router is driven here with a hand-cranked
/// scheduler so every run-loop turn is explicit: the claim happens on the key, the re-send happens
/// on a later turn once a text view holds the caret, keys typed in between queue behind the first,
/// and a key whose caret never arrives is dropped.
@MainActor
final class StrayTypingRouterTests: XCTestCase {
  /// Stands in for the main run loop: each `turn()` runs what one `DispatchQueue.main.async` would have.
  private final class Turns {
    private var queued: [@MainActor () -> Void] = []
    var pendingCount: Int { queued.count }
    func enqueue(_ work: @escaping @MainActor () -> Void) { queued.append(work) }
    @MainActor func turn() {
      let batch = queued
      queued.removeAll()
      for work in batch { work() }
    }
  }

  /// What the router sees of AppKit: the caret, the delivery path, and the key-down monitor.
  private final class Seams {
    var delivered: [NSEvent] = []
    var caretPresent = true
    /// The handler the router installed, while installed. Keys "typed" during the wait go through it.
    var monitor: (@MainActor (NSEvent) -> NSEvent?)?
    var installs = 0
    var removals = 0
  }

  private struct Harness {
    let router: StrayTypingRouter
    let turns: Turns
    let textView: NSTextView
    let seams: Seams
  }

  private func makeHarness(caretPresentInitially: Bool = true) -> Harness {
    let turns = Turns()
    let textView = NSTextView(frame: NSRect(x: 0, y: 0, width: 200, height: 24))
    let seams = Seams()
    seams.caretPresent = caretPresentInitially
    let router = StrayTypingRouter(
      schedule: { turns.enqueue($0) },
      caretHolder: { _ in seams.caretPresent ? textView : nil },
      deliver: { seams.delivered.append($0) },
      installMonitor: { handler in
        seams.monitor = handler
        seams.installs += 1
        return NSObject()
      },
      removeMonitor: { _ in
        seams.monitor = nil
        seams.removals += 1
      })
    return Harness(router: router, turns: turns, textView: textView, seams: seams)
  }

  private func key(
    _ characters: String, ignoringModifiers: String? = nil, flags: NSEvent.ModifierFlags = [],
    keyCode: UInt16 = 0, windowNumber: Int = 0
  ) throws -> NSEvent {
    try XCTUnwrap(
      NSEvent.keyEvent(
        with: .keyDown, location: .zero, modifierFlags: flags, timestamp: 0, windowNumber: windowNumber,
        context: nil, characters: characters, charactersIgnoringModifiers: ignoringModifiers ?? characters,
        isARepeat: false, keyCode: keyCode))
  }

  /// A window that survives `close()` under ARC (plain windows release themselves on close).
  private func makeWindow() -> NSWindow {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 300, height: 200), styleMask: [.titled], backing: .buffered,
      defer: false)
    window.isReleasedWhenClosed = false
    return window
  }

  // MARK: Policy

  func testPrintableCharactersAreTypingAndCommandKeysArrowsAndWhitespaceAreNot() {
    typealias P = StrayTypingPolicy
    XCTAssertTrue(P.isTyping(characters: "a", charactersIgnoringModifiers: "a", modifierFlags: []))
    XCTAssertTrue(P.isTyping(characters: "A", charactersIgnoringModifiers: "a", modifierFlags: .shift))
    XCTAssertTrue(P.isTyping(characters: "é", charactersIgnoringModifiers: "e", modifierFlags: .option))
    XCTAssertTrue(P.isTyping(characters: "7", charactersIgnoringModifiers: "7", modifierFlags: []))
    XCTAssertTrue(P.isTyping(characters: "?", charactersIgnoringModifiers: "/", modifierFlags: .shift))
    XCTAssertTrue(
      P.isTyping(characters: "", charactersIgnoringModifiers: "e", modifierFlags: .option),
      "a dead key arrives with empty characters; the field editor composes it")

    XCTAssertFalse(P.isTyping(characters: "a", charactersIgnoringModifiers: "a", modifierFlags: .command))
    XCTAssertFalse(P.isTyping(characters: "a", charactersIgnoringModifiers: "a", modifierFlags: .control))
    XCTAssertFalse(
      P.isTyping(characters: "\u{F702}", charactersIgnoringModifiers: "\u{F702}", modifierFlags: .function),
      "left arrow")
    XCTAssertFalse(P.isTyping(characters: "\u{1B}", charactersIgnoringModifiers: "\u{1B}", modifierFlags: []), "Escape")
    XCTAssertFalse(P.isTyping(characters: "\t", charactersIgnoringModifiers: "\t", modifierFlags: []), "Tab")
    XCTAssertFalse(P.isTyping(characters: "\r", charactersIgnoringModifiers: "\r", modifierFlags: []), "Return")
    XCTAssertFalse(P.isTyping(characters: "\u{7F}", charactersIgnoringModifiers: "\u{7F}", modifierFlags: []), "Delete")
    XCTAssertFalse(P.isTyping(characters: " ", charactersIgnoringModifiers: " ", modifierFlags: []), "Space")
    XCTAssertFalse(P.isTyping(characters: nil, charactersIgnoringModifiers: nil, modifierFlags: []))
  }

  // MARK: Routing

  func testWithNoFieldRegisteredAKeyIsNotRouted() throws {
    let h = makeHarness()
    XCTAssertFalse(h.router.route(try key("a")))
    h.turns.turn()
    XCTAssertTrue(h.seams.delivered.isEmpty)
    XCTAssertEqual(h.seams.installs, 0, "nothing to wait for, so no keys are held")
  }

  func testAKeyClaimsTheFieldNowAndIsReSentOnceTheCaretIsInIt() throws {
    let h = makeHarness()
    var claims = 0
    h.router.register(window: nil, priority: .secondary) { claims += 1 }
    h.textView.string = "cla"
    h.textView.setSelectedRange(NSRange(location: 0, length: 3))  // what becoming first responder does

    let event = try key("u")
    XCTAssertTrue(h.router.route(event))
    XCTAssertEqual(claims, 1, "the claim runs on the key itself, so the field lights up as you type")
    XCTAssertTrue(h.seams.delivered.isEmpty, "the re-send waits for the focus claim to land")

    h.turns.turn()
    XCTAssertEqual(h.seams.delivered.count, 1)
    XCTAssertTrue(try XCTUnwrap(h.seams.delivered.first) === event, "the same event, so the field editor interprets it")
    XCTAssertEqual(
      h.textView.selectedRange(), NSRange(location: 3, length: 0),
      "the caret continues the existing search rather than replacing it")
    XCTAssertEqual(h.turns.pendingCount, 0)
    XCTAssertEqual(h.seams.removals, 1, "the hold on following keys is lifted once delivered")
  }

  func testKeysTypedWhileTheCaretIsOnItsWayQueueBehindTheFirstInOrder() throws {
    let h = makeHarness(caretPresentInitially: false)
    h.router.register(window: nil, priority: .secondary) {}

    let first = try key("a")
    XCTAssertTrue(h.router.route(first))
    let monitor = try XCTUnwrap(h.seams.monitor, "a monitor holds the keys that follow")

    // Typed before the focus claim landed: these would otherwise race the first key into the field.
    let second = try key("b")
    let third = try key("c")
    XCTAssertNil(monitor(second), "held")
    XCTAssertNil(monitor(third), "held")
    let escape = try key("\u{1B}", keyCode: 53)
    XCTAssertTrue(monitor(escape) === escape, "a key that is not typing passes straight through")

    h.turns.turn()
    XCTAssertTrue(h.seams.delivered.isEmpty)
    h.seams.caretPresent = true
    h.turns.turn()
    XCTAssertEqual(
      h.seams.delivered.map { $0.characters ?? "" }, ["a", "b", "c"], "in the order typed, never transposed")
    XCTAssertNil(h.seams.monitor, "the hold is lifted once delivered")
  }

  func testTheReSendGivesUpWhenTheCaretNeverArrivesAndDropsTheWholeQueue() throws {
    let h = makeHarness(caretPresentInitially: false)
    h.router.register(window: nil, priority: .secondary) {}

    XCTAssertTrue(h.router.route(try key("b")))
    _ = try XCTUnwrap(h.seams.monitor)(try key("c"))
    for _ in 0..<StrayTypingRouter.deliveryAttempts { h.turns.turn() }
    XCTAssertEqual(h.turns.pendingCount, 0, "gave up")
    XCTAssertTrue(h.seams.delivered.isEmpty, "a key whose caret never arrived is dropped, not delivered late")
    XCTAssertNil(h.seams.monitor, "and the hold is lifted so ordinary typing resumes")

    h.seams.caretPresent = true
    XCTAssertTrue(h.router.route(try key("d")), "a dropped key does not jam the router")
    h.turns.turn()
    XCTAssertEqual(h.seams.delivered.count, 1)
  }

  func testTheComposerOutranksTheSearchBarAndTheBarTakesOverWhenTheComposerLeaves() throws {
    let h = makeHarness()
    var claimed: [String] = []
    h.router.register(window: nil, priority: .secondary) { claimed.append("bar") }
    let composer = h.router.register(window: nil, priority: .primary) { claimed.append("composer") }
    h.router.register(window: nil, priority: .secondary) { claimed.append("later-bar") }

    XCTAssertTrue(h.router.route(try key("a")))
    h.turns.turn()
    XCTAssertEqual(claimed, ["composer"], "priority beats registration order")

    h.router.unregister(composer)
    XCTAssertTrue(h.router.route(try key("b")))
    h.turns.turn()
    XCTAssertEqual(claimed, ["composer", "later-bar"], "among equals the most recently mounted wins")
  }

  func testAModalDrawnInsideTheWindowBlocksTypingFromReachingTheBarBehindIt() throws {
    let h = makeHarness()
    var claims = 0
    h.router.register(window: nil, priority: .primary) { claims += 1 }
    let modal = h.router.register(window: nil, priority: .blocking)

    XCTAssertFalse(h.router.route(try key("h")), "swallowed, not aimed at the bar behind the scrim")
    h.turns.turn()
    XCTAssertEqual(claims, 0)
    XCTAssertTrue(h.seams.delivered.isEmpty)

    h.router.unregister(modal)
    XCTAssertTrue(h.router.route(try key("h")), "the modal is gone; the bar is back")
    XCTAssertEqual(claims, 1)
  }

  func testAKeyIsOnlyAimedAtAFieldInTheWindowItWasTypedInto() throws {
    let h = makeHarness()
    let shell = makeWindow()
    let other = makeWindow()
    defer {
      shell.close()
      other.close()
    }
    var claims: [String] = []
    h.router.register(window: shell, priority: .secondary) { claims.append("shell-bar") }

    let inOther = try key("a", windowNumber: other.windowNumber)
    XCTAssertTrue(inOther.window === other, "the synthetic event resolves to its window")
    XCTAssertFalse(h.router.route(inOther), "another window's typing must not light up the shell's bar")
    XCTAssertFalse(h.router.route(try key("a")), "nor does a windowless key match a windowed field")

    let inShell = try key("a", windowNumber: shell.windowNumber)
    XCTAssertTrue(h.router.route(inShell))
    XCTAssertEqual(claims, ["shell-bar"])
  }

  func testAKeyBeingReSentIsRecognisedAndNotRoutedAgain() throws {
    let turns = Turns()
    let textView = NSTextView(frame: .zero)
    final class Box {
      var router: StrayTypingRouter?
      var reentered: [Bool] = []
    }
    let box = Box()
    let router = StrayTypingRouter(
      schedule: { turns.enqueue($0) },
      caretHolder: { _ in textView },
      deliver: { event in
        // The field declined it and the chain brought it back to the sink.
        box.reentered.append(box.router?.route(event) ?? true)
      },
      installMonitor: { _ in nil },
      removeMonitor: { _ in })
    box.router = router
    router.register(window: nil, priority: .secondary) {}

    XCTAssertTrue(router.route(try key("a")))
    turns.turn()
    XCTAssertEqual(box.reentered, [false], "the same event must not start a second claim — that is the loop")
  }

  func testAKeyFromAChildWindowOrSheetIsNotAimedAtTheBarBehindIt() {
    // A sheet cannot be presented headless, so the child-window half of the rule stands in for it:
    // both are windows whose keyboard belongs to their own controls.
    let parent = makeWindow()
    let child = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 200, height: 100), styleMask: [.borderless], backing: .buffered,
      defer: false)
    child.isReleasedWhenClosed = false
    defer {
      parent.removeChildWindow(child)
      child.close()
      parent.close()
    }
    XCTAssertTrue(StrayTypingPolicy.windowAcceptsStrays(nil))
    XCTAssertTrue(StrayTypingPolicy.windowAcceptsStrays(parent))
    parent.addChildWindow(child, ordered: .above)
    XCTAssertFalse(StrayTypingPolicy.windowAcceptsStrays(child))
  }

  // MARK: The anchor

  func testTheAnchorRegistersForItsWindowAndLeavesWhenRemoved() throws {
    // The production registry, because the anchor is what wires views into it. Exercised through the
    // sink so the whole path from key to claim runs; a fresh router cannot be injected into the view.
    let window = makeWindow()
    defer { window.close() }
    let anchor = StrayTypingAnchorView(frame: .zero)
    var claims = 0
    anchor.claim = { claims += 1 }
    try XCTUnwrap(window.contentView).addSubview(anchor)

    let sink = UnhandledKeystrokeSink()
    sink.keyDown(with: try key("a", windowNumber: window.windowNumber))
    XCTAssertEqual(claims, 1, "in the window: the anchor's field is claimed")

    anchor.removeFromSuperview()
    sink.keyDown(with: try key("b", windowNumber: window.windowNumber))
    XCTAssertEqual(claims, 1, "out of the window: no registration is left behind")
  }

  // MARK: Through the sink

  func testTheSinkHandsTypingToTheRouterAndStillForwardsNothing() throws {
    final class NextResponderProbe: NSResponder {
      private(set) var forwardedKeys = 0
      override func keyDown(with event: NSEvent) { forwardedKeys += 1 }
    }
    let h = makeHarness()
    var claims = 0
    h.router.register(window: nil, priority: .secondary) { claims += 1 }
    let sink = UnhandledKeystrokeSink(router: h.router)
    let probe = NextResponderProbe()
    sink.nextResponder = probe

    sink.keyDown(with: try key("a"))
    h.turns.turn()
    XCTAssertEqual(claims, 1)
    XCTAssertEqual(h.seams.delivered.count, 1)

    sink.keyDown(with: try key("\u{F702}", flags: .function))  // an arrow is not typing
    h.turns.turn()
    XCTAssertEqual(claims, 1)
    XCTAssertEqual(probe.forwardedKeys, 0, "routed or swallowed, never forwarded — forwarding beeps")
  }

  func testAPlainWindowsChainIsCappedToo() {
    // A window that is not SwiftUI's never reaches `NSApp`; its chain ends at itself (or its
    // controller) and beeps there. `install(after:)` on the window caps that end.
    let window = makeWindow()
    defer { window.close() }
    XCTAssertNil(window.nextResponder, "a controller-less window's chain ends at the window")
    UnhandledKeystrokeSink.install(after: window)
    XCTAssertTrue(window.nextResponder is UnhandledKeystrokeSink)
    UnhandledKeystrokeSink.install(after: window)
    XCTAssertNil(window.nextResponder?.nextResponder, "idempotent")
  }
}
