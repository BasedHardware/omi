import Carbon.HIToolbox
import CoreGraphics
import Foundation

/// Synthetic mouse and keyboard input.
///
/// Every gesture is posted as a whole: a click is a move, a down and an up, with
/// the short pauses that make an app treat it as a click rather than three
/// unrelated events. Callers hand in global points that `CuaFrameGeometry` has
/// already resolved — nothing here converts coordinates.
///
/// Events go to `.cghidEventTap`, the same place the hardware posts to, so they
/// pass through every tap the system and other apps have installed. That is what
/// makes them work in apps that ignore events injected further down the stack,
/// and it is also why this is gated: it is indistinguishable from the user.
enum CuaInputSynth {
  /// Gap between the halves of a press. A down and an up delivered in the same
  /// run loop turn read as a glitch to some apps rather than as a click, so the
  /// pair is spaced; anything longer than this starts to feel like lag when a
  /// gesture is a dozen events.
  private static let pressInterval: TimeInterval = 0.02

  /// How long a drag holds the button still at each end. Long enough for a drop
  /// target to begin tracking, short enough that a drag is not perceptibly slow.
  private static let dragHoldInterval: TimeInterval = 0.12

  private static func source() -> CGEventSource? {
    CGEventSource(stateID: .hidSystemState)
  }

  /// Move the pointer, and move the *cursor*.
  ///
  /// A `.mouseMoved` event alone tells apps the pointer moved but does not move
  /// the hardware cursor the window server tracks. Anything that reads
  /// `NSEvent.mouseLocation` — hover states, menu tracking, drag targets, and
  /// every app that samples the position rather than listening for the event —
  /// keeps seeing the old point, so the click that follows lands somewhere the
  /// app was not expecting. Warping first is what makes the two agree.
  static func moveCursor(to point: CGPoint) {
    CGWarpMouseCursorPosition(point)
    // The warp suppresses hardware mouse deltas for a quarter second unless the
    // association is restored, which would otherwise freeze the user's own mouse
    // for a moment after every synthetic move.
    CGAssociateMouseAndMouseCursorPosition(1)
    let event = CGEvent(
      mouseEventSource: source(), mouseType: .mouseMoved, mouseCursorPosition: point,
      mouseButton: .left)
    event?.post(tap: .cghidEventTap)
  }

  enum Button: String, CaseIterable {
    case left, right, middle

    var cgButton: CGMouseButton {
      switch self {
      case .left: return .left
      case .right: return .right
      case .middle: return .center
      }
    }

    var downType: CGEventType {
      switch self {
      case .left: return .leftMouseDown
      case .right: return .rightMouseDown
      case .middle: return .otherMouseDown
      }
    }

    var upType: CGEventType {
      switch self {
      case .left: return .leftMouseUp
      case .right: return .rightMouseUp
      case .middle: return .otherMouseUp
      }
    }

    var dragType: CGEventType {
      switch self {
      case .left: return .leftMouseDragged
      case .right: return .rightMouseDragged
      case .middle: return .otherMouseDragged
      }
    }
  }

  /// A click, or a double or triple click.
  ///
  /// The repeat count rides on the events as `mouseEventClickState` rather than
  /// being expressed as separate clicks: that field is what AppKit reads to tell
  /// a double click from two clicks, and two plain clicks 20ms apart are two
  /// plain clicks no matter how close together they are.
  /// Hold real modifier keys around a gesture.
  ///
  /// Setting `flags` on a mouse event is enough for AppKit, and not enough for
  /// Chromium — every Electron app, VS Code and Slack included — which tracks
  /// modifier state from the key events themselves. A flags-only cmd+click
  /// arrives there as a plain click, which is how a "open in new tab" becomes a
  /// navigation. `key` already presses them for exactly this reason; a click,
  /// a drag and a scroll need the same treatment.
  private static func holdingModifiers(_ flags: CGEventFlags, _ body: () -> Void) {
    let held = modifierKeyCodes.filter { flags.contains($0.0) }
    guard !held.isEmpty else { return body() }
    var pressed: CGEventFlags = []
    for (flag, keyCode) in held {
      pressed.insert(flag)
      postKey(keyCode, down: true, flags: pressed)
    }
    body()
    for (flag, keyCode) in held.reversed() {
      pressed.remove(flag)
      postKey(keyCode, down: false, flags: pressed)
    }
  }

  static func click(at point: CGPoint, button: Button = .left, count: Int = 1, flags: CGEventFlags = []) {
    holdingModifiers(flags) { postClick(at: point, button: button, count: count, flags: flags) }
  }

  private static func postClick(at point: CGPoint, button: Button, count: Int, flags: CGEventFlags) {
    moveCursor(to: point)
    // Let the move be seen before the press. Tracking areas, hover states and
    // menu highlighting all update on the move, and an app that has not yet
    // processed it treats the press as landing on whatever was under the old
    // point.
    Thread.sleep(forTimeInterval: pressInterval)
    let repeats = min(max(count, 1), 3)
    for click in 1...repeats {
      for type in [button.downType, button.upType] {
        guard
          let event = CGEvent(
            mouseEventSource: source(), mouseType: type, mouseCursorPosition: point,
            mouseButton: button.cgButton)
        else { continue }
        event.setIntegerValueField(.mouseEventClickState, value: Int64(click))
        event.flags = flags
        event.post(tap: .cghidEventTap)
        Thread.sleep(forTimeInterval: pressInterval)
      }
    }
  }

  /// Press at one point, move, release at another.
  ///
  /// The intermediate `mouseDragged` events are not decoration: a drop target
  /// that never saw the pointer travel over it does not light up, and list
  /// reordering and canvas apps ignore a down-then-up with no motion between.
  static func drag(
    from start: CGPoint, to end: CGPoint, button: Button = .left, steps: Int = 12,
    flags: CGEventFlags = []
  ) {
    holdingModifiers(flags) {
      postDrag(from: start, to: end, button: button, steps: steps, flags: flags)
    }
  }

  private static func postDrag(
    from start: CGPoint, to end: CGPoint, button: Button, steps: Int, flags: CGEventFlags
  ) {
    moveCursor(to: start)
    Thread.sleep(forTimeInterval: pressInterval)
    let post = { (type: CGEventType, point: CGPoint) in
      guard
        let event = CGEvent(
          mouseEventSource: source(), mouseType: type, mouseCursorPosition: point,
          mouseButton: button.cgButton)
      else { return }
      event.flags = flags
      event.post(tap: .cghidEventTap)
    }
    post(button.downType, start)
    // A press released or moved too quickly is a click, not the start of a drag.
    // Finder, list reordering and every drag-and-drop target wait for the press
    // to settle before they begin tracking, so a 20ms hold loses the gesture.
    Thread.sleep(forTimeInterval: dragHoldInterval)
    let stepCount = min(max(steps, 1), 60)
    for step in 1...stepCount {
      let progress = CGFloat(step) / CGFloat(stepCount)
      post(
        button.dragType,
        CGPoint(
          x: start.x + (end.x - start.x) * progress,
          y: start.y + (end.y - start.y) * progress))
      Thread.sleep(forTimeInterval: pressInterval / 2)
    }
    // The drop target highlights on the last move; releasing in the same turn
    // drops on whatever it had tracked before.
    Thread.sleep(forTimeInterval: dragHoldInterval)
    post(button.upType, end)
  }

  /// Scroll at a point. Positive `y` scrolls the content up (the gesture a user
  /// makes to read further down), matching the direction a wheel reports.
  ///
  /// Sent as a run of small line events rather than one large one. A single
  /// event with a big delta is clamped by some views and ignored by others that
  /// only animate continuous scrolls, so "scroll down 10" moved a page by
  /// nothing in exactly the apps a model is most likely to be reading.
  static func scroll(at point: CGPoint, deltaX: Int, deltaY: Int, flags: CGEventFlags = []) {
    holdingModifiers(flags) { postScroll(at: point, deltaX: deltaX, deltaY: deltaY, flags: flags) }
  }

  private static func postScroll(at point: CGPoint, deltaX: Int, deltaY: Int, flags: CGEventFlags) {
    moveCursor(to: point)
    // Same reason a click waits: a scroll is delivered to the view under the
    // pointer as the app understands it, so scrolling before the move has been
    // processed scrolls whatever was under the old point.
    Thread.sleep(forTimeInterval: pressInterval)
    let steps = max(abs(deltaX), abs(deltaY))
    guard steps > 0 else { return }
    let stepX = deltaX == 0 ? 0 : (deltaX > 0 ? 1 : -1)
    let stepY = deltaY == 0 ? 0 : (deltaY > 0 ? 1 : -1)
    for step in 0..<min(steps, 200) {
      guard
        let event = CGEvent(
          scrollWheelEvent2Source: source(), units: .line, wheelCount: 2,
          wheel1: Int32(step < abs(deltaY) ? stepY : 0),
          wheel2: Int32(step < abs(deltaX) ? stepX : 0),
          wheel3: 0)
      else { return }
      event.flags = flags
      event.post(tap: .cghidEventTap)
      Thread.sleep(forTimeInterval: pressInterval / 2)
    }
  }

  /// Virtual key codes for the modifiers, so a chord can hold real keys down
  /// rather than only claiming to.
  private static let modifierKeyCodes: [(CGEventFlags, CGKeyCode)] = [
    (.maskCommand, CGKeyCode(kVK_Command)),
    (.maskShift, CGKeyCode(kVK_Shift)),
    (.maskAlternate, CGKeyCode(kVK_Option)),
    (.maskControl, CGKeyCode(kVK_Control)),
  ]

  /// Press a chord.
  ///
  /// The modifiers are pressed as real keys around the keystroke, not just set
  /// as flags on it. AppKit reads the flags, but Chromium — and so every Electron
  /// app, VS Code and Slack included — tracks modifier state from the key events
  /// themselves, and a flags-only cmd+S arrives there as a plain S typed into the
  /// document. The flags are still set, because that is what everything else
  /// reads.
  static func key(_ chord: CuaKeyMap.Chord) {
    let held = modifierKeyCodes.filter { chord.flags.contains($0.0) }
    var flags: CGEventFlags = []
    for (flag, keyCode) in held {
      flags.insert(flag)
      postKey(keyCode, down: true, flags: flags)
    }
    postKey(chord.keyCode, down: true, flags: chord.flags)
    postKey(chord.keyCode, down: false, flags: chord.flags)
    for (flag, keyCode) in held.reversed() {
      flags.remove(flag)
      postKey(keyCode, down: false, flags: flags)
    }
  }

  private static func postKey(_ keyCode: CGKeyCode, down: Bool, flags: CGEventFlags) {
    guard let event = CGEvent(keyboardEventSource: source(), virtualKey: keyCode, keyDown: down)
    else { return }
    event.flags = flags
    event.post(tap: .cghidEventTap)
    Thread.sleep(forTimeInterval: pressInterval)
  }

  /// Type literal text.
  ///
  /// Every character the keyboard can actually produce is typed as that key,
  /// with shift where the layout needs it. A synthetic event carrying only a
  /// Unicode string and no key code is ignored by a whole class of apps —
  /// terminals, Chromium and anything reading the key code rather than the
  /// characters — so a "typed" password or command silently arrives empty. The
  /// Unicode path is kept for what no key produces: emoji, and characters
  /// outside the current layout.
  ///
  /// Newlines are always a real Return: a carriage return delivered as text is
  /// dropped by most fields.
  static func typeText(_ text: String, layout: CuaKeyMap.KeyboardLayout) {
    for (index, line) in text.components(separatedBy: "\n").enumerated() {
      if index > 0 { key(.init(keyCode: CGKeyCode(kVK_Return), flags: [])) }
      var unicodeRun: [UniChar] = []
      let flushUnicode = {
        for slice in unicodeRun.chunked(into: 16) { postUnicode(slice) }
        unicodeRun.removeAll()
      }
      for character in line {
        if let stroke = layout.stroke(for: character) {
          flushUnicode()
          key(.init(keyCode: stroke.keyCode, flags: stroke.needsShift ? .maskShift : []))
        } else {
          unicodeRun.append(contentsOf: Array(String(character).utf16))
        }
      }
      flushUnicode()
    }
  }

  /// One keystroke carrying characters instead of a key. The event's string
  /// field is a fixed buffer, so a long run has to be posted in slices or the
  /// tail is dropped with no error.
  private static func postUnicode(_ characters: [UniChar]) {
    for isDown in [true, false] {
      guard let event = CGEvent(keyboardEventSource: source(), virtualKey: 0, keyDown: isDown)
      else { continue }
      var buffer = characters
      event.keyboardSetUnicodeString(stringLength: buffer.count, unicodeString: &buffer)
      event.post(tap: .cghidEventTap)
    }
    Thread.sleep(forTimeInterval: pressInterval)
  }

  static func cursorPosition() -> CGPoint {
    CGEvent(source: nil)?.location ?? .zero
  }
}

extension Array {
  fileprivate func chunked(into size: Int) -> [[Element]] {
    guard size > 0 else { return [self] }
    return stride(from: 0, to: count, by: size).map { Array(self[$0..<Swift.min($0 + size, count)]) }
  }
}
