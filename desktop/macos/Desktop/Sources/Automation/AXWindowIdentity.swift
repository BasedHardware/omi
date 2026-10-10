import ApplicationServices
import CoreGraphics

/// The window number behind an accessibility window element.
///
/// `_AXUIElementGetWindow` is private API, but it is the only direct link
/// from an `AXUIElement` window to its `CGWindowID`; matching by position and
/// size is fragile. Every caller keeps a fallback for when it fails.
enum AXWindowIdentity {
  @_silgen_name("_AXUIElementGetWindow")
  private static func _AXUIElementGetWindow(_ element: AXUIElement, _ windowID: UnsafeMutablePointer<CGWindowID>)
    -> AXError

  static func windowID(of element: AXUIElement) -> CGWindowID? {
    var windowID: CGWindowID = 0
    guard _AXUIElementGetWindow(element, &windowID) == .success, windowID != 0 else { return nil }
    return windowID
  }
}
