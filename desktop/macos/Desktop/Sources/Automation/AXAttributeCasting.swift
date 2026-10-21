import ApplicationServices
import Foundation

/// Typed reads of `AXUIElementCopyAttributeValue` results.
///
/// The copy call is IPC against a foreign process: `.success` asserts the
/// attribute was answered, not the value's type. A buggy AX server can answer
/// `AXFocusedWindow` with a string or `AXPosition` with a non-AXValue, and the
/// unconditional `as!` casts these replace turned that into a trap inside a
/// pipeline that walks arbitrary apps' accessibility trees all day.
///
/// `as?` does not help here: Swift's conditional cast to a CoreFoundation type
/// always succeeds without checking the CF type ID, so the only honest gate is
/// `CFGetTypeID` before the cast.
enum AXAttributeCasting {
  static func element(_ raw: CFTypeRef?) -> AXUIElement? {
    guard let raw, CFGetTypeID(raw) == AXUIElementGetTypeID() else { return nil }
    return unsafeDowncast(raw, to: AXUIElement.self)
  }

  /// Elements that fail the type check are dropped rather than trapping or
  /// failing the whole array — a partial list still names real windows.
  static func elements(_ raw: CFTypeRef?) -> [AXUIElement] {
    (raw as? [AnyObject])?.compactMap {
      CFGetTypeID($0) == AXUIElementGetTypeID() ? unsafeDowncast($0, to: AXUIElement.self) : nil
    } ?? []
  }

  static func value(_ raw: CFTypeRef?) -> AXValue? {
    guard let raw, CFGetTypeID(raw) == AXValueGetTypeID() else { return nil }
    return unsafeDowncast(raw, to: AXValue.self)
  }
}
