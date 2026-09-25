import CoreGraphics
import Foundation

/// Seconds since the last HID (keyboard/mouse) input event, for presence-gated
/// hub warming. Same `kCGAnyInputEventType` sentinel ProactiveAssistantsPlugin
/// uses: the C header defines it as `((CGEventType)(~0))` and it is not bridged
/// to a Swift `CGEventType` case. Querying a concrete case (e.g. `.null`) would
/// measure time since that one event type and report the user as always idle.
enum UserInputPresence {
  private static let anyInputEventType: CGEventType = {
    guard let type = CGEventType(rawValue: ~0) else {
      assertionFailure("kCGAnyInputEventType (~0) must be representable as CGEventType")
      return .null
    }
    return type
  }()

  /// `nil` when the sentinel could not be represented (callers fail open).
  static func secondsSinceLastInput() -> TimeInterval? {
    guard anyInputEventType != .null else { return nil }
    return TimeInterval(
      CGEventSource.secondsSinceLastEventType(.hidSystemState, eventType: anyInputEventType))
  }
}
