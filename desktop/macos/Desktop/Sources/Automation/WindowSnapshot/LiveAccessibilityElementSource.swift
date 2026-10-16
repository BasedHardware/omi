import ApplicationServices
import Foundation

/// An `AXUIElement` compared the way the accessibility server compares them.
struct LiveAXElement: Equatable {
  let raw: AXUIElement

  static func == (lhs: LiveAXElement, rhs: LiveAXElement) -> Bool {
    CFEqual(lhs.raw, rhs.raw)
  }
}

/// `AccessibilityElementSource` over the real accessibility server, for one
/// foreign process.
///
/// Every read is IPC to the other app, so every element gets a short
/// messaging timeout before it is read: a hung app answers
/// `kAXErrorCannotComplete` after a quarter second instead of after the
/// system default of several seconds, and the walker stops at the first one.
/// Every value goes through `AXAttributeCasting`, because a buggy app can
/// answer with any CF type. Create it on the thread that walks; it is not
/// shared across threads.
struct LiveAccessibilityElementSource: AccessibilityElementSource {
  static let messagingTimeout: Float = 0.25

  let application: LiveAXElement

  init(pid: pid_t) {
    let app = AXUIElementCreateApplication(pid)
    AXUIElementSetMessagingTimeout(app, Self.messagingTimeout)
    application = LiveAXElement(raw: app)
  }

  func windows() throws(AccessibilitySourceError) -> [LiveAXElement] {
    try elements(kAXWindowsAttribute, of: application.raw)
  }

  func focusedWindow() throws(AccessibilitySourceError) -> LiveAXElement? {
    try element(kAXFocusedWindowAttribute, of: application.raw)
  }

  func mainWindow() throws(AccessibilitySourceError) -> LiveAXElement? {
    try element(kAXMainWindowAttribute, of: application.raw)
  }

  func windowID(of window: LiveAXElement) -> CGWindowID? {
    AXWindowIdentity.windowID(of: window.raw)
  }

  func attributes(_ names: [String], of element: LiveAXElement) throws(AccessibilitySourceError)
    -> [String: AccessibilityAttributeValue]
  {
    guard !names.isEmpty else { return [:] }
    prepare(element.raw)
    var raw: CFArray?
    let status = AXUIElementCopyMultipleAttributeValues(
      element.raw, names as CFArray, AXCopyMultipleAttributeOptions(rawValue: 0), &raw)
    try Self.check(status)
    guard let values = raw as? [AnyObject] else { return [:] }
    var decoded: [String: AccessibilityAttributeValue] = [:]
    for (name, value) in zip(names, values) {
      if let error = AXAttributeCasting.axError(value) {
        // A per-attribute timeout means the app stopped answering mid-batch.
        if error == .cannotComplete { throw .timedOut }
        continue
      }
      if let decodedValue = Self.decode(value) { decoded[name] = decodedValue }
    }
    return decoded
  }

  func actionNames(of element: LiveAXElement) throws(AccessibilitySourceError) -> [String] {
    prepare(element.raw)
    var raw: CFArray?
    let status = AXUIElementCopyActionNames(element.raw, &raw)
    if status == .noValue || status == .attributeUnsupported || status == .actionUnsupported { return [] }
    try Self.check(status)
    return (raw as? [AnyObject])?.compactMap { AXAttributeCasting.string($0) } ?? []
  }

  func isValueSettable(_ element: LiveAXElement) throws(AccessibilitySourceError) -> Bool {
    prepare(element.raw)
    var settable = DarwinBoolean(false)
    let status = AXUIElementIsAttributeSettable(element.raw, kAXValueAttribute as CFString, &settable)
    if status == .attributeUnsupported || status == .noValue { return false }
    try Self.check(status)
    return settable.boolValue
  }

  func children(of element: LiveAXElement, preferVisible: Bool, head: Int, tail: Int)
    throws(AccessibilitySourceError) -> AccessibilityChildren<LiveAXElement>
  {
    if preferVisible {
      for attribute in [kAXVisibleRowsAttribute, kAXVisibleChildrenAttribute] {
        let total = try count(attribute, of: element.raw)
        guard total > 0 else { continue }
        return AccessibilityChildren(
          elements: try slices(attribute, of: element.raw, total: total, head: head, tail: tail),
          total: total, visibleOnly: true)
      }
    }
    let total = try count(kAXChildrenAttribute, of: element.raw)
    return AccessibilityChildren(
      elements: try slices(kAXChildrenAttribute, of: element.raw, total: total, head: head, tail: tail),
      total: total, visibleOnly: false)
  }

  func selectedRows(of element: LiveAXElement) throws(AccessibilitySourceError) -> [LiveAXElement] {
    let rows = try elements(kAXSelectedRowsAttribute, of: element.raw)
    return rows.isEmpty ? try elements(kAXSelectedChildrenAttribute, of: element.raw) : rows
  }

  func appFlag(_ name: String) -> Bool? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(application.raw, name as CFString, &raw) == .success else { return nil }
    return AXAttributeCasting.bool(raw)
  }

  @discardableResult func setAppFlag(_ name: String, _ value: Bool) -> Bool {
    let flag: CFBoolean = value ? kCFBooleanTrue : kCFBooleanFalse
    return AXUIElementSetAttributeValue(application.raw, name as CFString, flag) == .success
  }

  // MARK: - Helpers

  private func prepare(_ element: AXUIElement) {
    AXUIElementSetMessagingTimeout(element, Self.messagingTimeout)
  }

  private func element(_ attribute: String, of element: AXUIElement) throws(AccessibilitySourceError)
    -> LiveAXElement?
  {
    prepare(element)
    var raw: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, attribute as CFString, &raw)
    if Self.isAbsent(status) { return nil }
    try Self.check(status)
    return AXAttributeCasting.element(raw).map(LiveAXElement.init)
  }

  private func elements(_ attribute: String, of element: AXUIElement) throws(AccessibilitySourceError)
    -> [LiveAXElement]
  {
    prepare(element)
    var raw: CFTypeRef?
    let status = AXUIElementCopyAttributeValue(element, attribute as CFString, &raw)
    if Self.isAbsent(status) { return [] }
    try Self.check(status)
    return AXAttributeCasting.elements(raw).map(LiveAXElement.init)
  }

  private func count(_ attribute: String, of element: AXUIElement) throws(AccessibilitySourceError) -> Int {
    prepare(element)
    var total: CFIndex = 0
    let status = AXUIElementGetAttributeValueCount(element, attribute as CFString, &total)
    if Self.isAbsent(status) { return 0 }
    try Self.check(status)
    return max(0, total)
  }

  private func slices(_ attribute: String, of element: AXUIElement, total: Int, head: Int, tail: Int)
    throws(AccessibilitySourceError) -> [AccessibilityChildren<LiveAXElement>.Child]
  {
    var children: [AccessibilityChildren<LiveAXElement>.Child] = []
    for range in AccessibilityChildren<LiveAXElement>.ranges(total: total, head: head, tail: tail) {
      var raw: CFArray?
      let status = AXUIElementCopyAttributeValues(element, attribute as CFString, range.lowerBound, range.count, &raw)
      if Self.isAbsent(status) { continue }
      try Self.check(status)
      for (offset, child) in AXAttributeCasting.elements(raw).enumerated() {
        children.append(.init(index: range.lowerBound + offset, element: LiveAXElement(raw: child)))
      }
    }
    return children
  }

  private static func isAbsent(_ status: AXError) -> Bool {
    status == .noValue || status == .attributeUnsupported || status == .parameterizedAttributeUnsupported
  }

  private static func check(_ status: AXError) throws(AccessibilitySourceError) {
    switch status {
    case .success: return
    case .cannotComplete: throw .timedOut
    case .apiDisabled: throw .apiDisabled
    default: throw .invalidElement
    }
  }

  private static func decode(_ value: AnyObject) -> AccessibilityAttributeValue? {
    if let string = AXAttributeCasting.string(value) { return .string(string) }
    if CFGetTypeID(value) == CFBooleanGetTypeID(), let flag = AXAttributeCasting.bool(value) { return .bool(flag) }
    if let number = AXAttributeCasting.number(value) { return .number(number) }
    if let point = AXAttributeCasting.point(value) { return .point(point) }
    if let size = AXAttributeCasting.size(value) { return .size(size) }
    return nil
  }
}
