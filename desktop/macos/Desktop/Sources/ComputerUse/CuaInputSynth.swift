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

  private static func source() -> CGEventSource? {
    CGEventSource(stateID: .hidSystemState)
  }

  static func moveCursor(to point: CGPoint) {
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
  static func click(at point: CGPoint, button: Button = .left, count: Int = 1, flags: CGEventFlags = []) {
    moveCursor(to: point)
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
    moveCursor(to: start)
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
    Thread.sleep(forTimeInterval: pressInterval)
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
    post(button.upType, end)
  }

  /// Scroll at a point. Positive `y` scrolls the content up (the gesture a user
  /// makes to read further down), matching the direction a wheel reports.
  static func scroll(at point: CGPoint, deltaX: Int, deltaY: Int, flags: CGEventFlags = []) {
    moveCursor(to: point)
    guard
      let event = CGEvent(
        scrollWheelEvent2Source: source(), units: .line, wheelCount: 2,
        wheel1: Int32(clamping: deltaY), wheel2: Int32(clamping: deltaX), wheel3: 0)
    else { return }
    event.flags = flags
    event.post(tap: .cghidEventTap)
  }

  static func key(_ chord: CuaKeyMap.Chord) {
    for isDown in [true, false] {
      guard
        let event = CGEvent(
          keyboardEventSource: source(), virtualKey: chord.keyCode, keyDown: isDown)
      else { continue }
      event.flags = chord.flags
      event.post(tap: .cghidEventTap)
      Thread.sleep(forTimeInterval: pressInterval)
    }
  }

  /// Type literal text.
  ///
  /// The characters ride on the event as a Unicode string rather than being
  /// resolved to key codes, so accents, emoji and every non-US layout type
  /// correctly without a translation table. Newlines are the exception: a
  /// carriage return delivered as text is ignored by most fields, so each line
  /// break is posted as a real Return key.
  static func typeText(_ text: String) {
    for (index, line) in text.components(separatedBy: "\n").enumerated() {
      if index > 0 { key(.init(keyCode: CGKeyCode(kVK_Return), flags: [])) }
      guard !line.isEmpty else { continue }
      // The event's string field is a fixed buffer; long text has to be posted
      // in slices or the tail is dropped without an error.
      for slice in Array(line.utf16).chunked(into: 16) {
        for isDown in [true, false] {
          guard let event = CGEvent(keyboardEventSource: source(), virtualKey: 0, keyDown: isDown)
          else { continue }
          var buffer = slice
          event.keyboardSetUnicodeString(stringLength: buffer.count, unicodeString: &buffer)
          event.post(tap: .cghidEventTap)
        }
        Thread.sleep(forTimeInterval: pressInterval)
      }
    }
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
