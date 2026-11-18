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

  static func string(_ raw: CFTypeRef?) -> String? {
    guard let raw, CFGetTypeID(raw) == CFStringGetTypeID() else { return nil }
    return unsafeDowncast(raw, to: CFString.self) as String
  }

  static func bool(_ raw: CFTypeRef?) -> Bool? {
    guard let raw else { return nil }
    if CFGetTypeID(raw) == CFBooleanGetTypeID() {
      return CFBooleanGetValue(unsafeDowncast(raw, to: CFBoolean.self))
    }
    return number(raw).map { $0 != 0 }
  }

  /// Booleans are not numbers here: a checkbox answers `AXValue` with a
  /// CFNumber, while `kCFBooleanTrue` is only ever an on/off flag.
  static func number(_ raw: CFTypeRef?) -> Double? {
    guard let raw, CFGetTypeID(raw) == CFNumberGetTypeID() else { return nil }
    var result = 0.0
    guard CFNumberGetValue(unsafeDowncast(raw, to: CFNumber.self), .doubleType, &result) else { return nil }
    return result
  }

  static func point(_ raw: CFTypeRef?) -> CGPoint? {
    guard let value = value(raw), AXValueGetType(value) == .cgPoint else { return nil }
    var point = CGPoint.zero
    return AXValueGetValue(value, .cgPoint, &point) ? point : nil
  }

  static func size(_ raw: CFTypeRef?) -> CGSize? {
    guard let value = value(raw), AXValueGetType(value) == .cgSize else { return nil }
    var size = CGSize.zero
    return AXValueGetValue(value, .cgSize, &size) ? size : nil
  }

  /// `AXUIElementCopyMultipleAttributeValues` answers a failed attribute with
  /// an `AXValue` of type `.axError` in that slot instead of failing the call.
  static func axError(_ raw: CFTypeRef?) -> AXError? {
    guard let value = value(raw), AXValueGetType(value) == .axError else { return nil }
    var error = AXError.success
    return AXValueGetValue(value, .axError, &error) ? error : nil
  }
}
