import CoreGraphics
import Foundation

/// Why one accessibility read did not answer.
enum AccessibilitySourceError: Error, Equatable, Sendable {
  /// The app did not answer within the messaging timeout (`kAXErrorCannotComplete`).
  case timedOut
  /// Accessibility is not granted to Omi (`kAXErrorAPIDisabled`).
  case apiDisabled
  /// The element went away between finding it and reading it.
  case invalidElement
}

/// A decoded attribute. Anything the snapshot does not use (ranges, rects,
/// URLs, nested elements) is never decoded, so it can never reach the model.
enum AccessibilityAttributeValue: Equatable, Sendable {
  case string(String)
  case bool(Bool)
  case number(Double)
  case point(CGPoint)
  case size(CGSize)

  var string: String? {
    if case .string(let value) = self { return value }
    return nil
  }

  var bool: Bool? {
    switch self {
    case .bool(let value): return value
    case .number(let value): return value != 0
    default: return nil
    }
  }
}

/// Attribute and action names the snapshot reads, spelled once.
enum AXName {
  static let role = "AXRole"
  static let subrole = "AXSubrole"
  static let title = "AXTitle"
  static let description = "AXDescription"
  static let value = "AXValue"
  static let identifier = "AXIdentifier"
  static let placeholder = "AXPlaceholderValue"
  static let enabled = "AXEnabled"
  static let focused = "AXFocused"
  static let position = "AXPosition"
  static let size = "AXSize"
  /// A text element's length, read before its value so a long document is
  /// never copied out of the other app just to be left out.
  static let numberOfCharacters = "AXNumberOfCharacters"
  /// Electron's documented switch for assistive clients.
  static let manualAccessibility = "AXManualAccessibility"
  /// Chromium builds its accessibility tree only for an assistive client.
  static let enhancedUserInterface = "AXEnhancedUserInterface"
}

/// The accessibility reads `ui_snapshot` makes against one app.
///
/// The protocol is read-only by construction: it has no method that presses,
/// focuses, raises, selects or types, so no conforming source can move the
/// person's cursor or change another app's state. Its single write is
/// `setAppFlag`, which turns on the assistive tree of an Electron or Chromium
/// app the person has already approved reading; nothing else may call it.
protocol AccessibilityElementSource {
  associatedtype Element: Equatable

  /// The application element of the process this source was made for.
  var application: Element { get }

  func windows() throws(AccessibilitySourceError) -> [Element]
  func focusedWindow() throws(AccessibilitySourceError) -> Element?
  func mainWindow() throws(AccessibilitySourceError) -> Element?
  /// The window number, when the window server exposes one.
  func windowID(of window: Element) -> CGWindowID?

  /// One round trip for several attributes. Absent or failed attributes are
  /// simply missing from the result; a timeout or a disabled API throws.
  func attributes(_ names: [String], of element: Element) throws(AccessibilitySourceError)
    -> [String: AccessibilityAttributeValue]
  func actionNames(of element: Element) throws(AccessibilitySourceError) -> [String]
  func isValueSettable(_ element: Element) throws(AccessibilitySourceError) -> Bool

  /// The first `head` and the last `tail` children, each with its index,
  /// or all of them when there are no more than `head + tail`. With
  /// `preferVisible`, lists, tables and outlines answer only their on-screen
  /// rows when they expose them, so a 10,000-row list costs only what is
  /// visible. `total` is how many exist.
  func children(of element: Element, preferVisible: Bool, head: Int, tail: Int) throws(AccessibilitySourceError)
    -> AccessibilityChildren<Element>

  /// The selected rows of a list, table or outline.
  func selectedRows(of element: Element) throws(AccessibilitySourceError) -> [Element]

  func appFlag(_ name: String) -> Bool?
  /// Returns whether the app accepted the write.
  @discardableResult func setAppFlag(_ name: String, _ value: Bool) -> Bool
}

struct AccessibilityChildren<Element> {
  struct Child {
    let index: Int
    let element: Element
  }

  var elements: [Child]
  /// How many children exist, fetched or not.
  var total: Int
  /// The elements are the container's visible rows, not its raw children.
  var visibleOnly: Bool

  /// The index ranges to fetch from `total` children: everything, or a head and a tail.
  static func ranges(total: Int, head: Int, tail: Int) -> [Range<Int>] {
    let head = max(0, head)
    let tail = max(0, tail)
    guard total > head + tail else { return total > 0 ? [0..<total] : [] }
    return [0..<head, (total - tail)..<total].filter { !$0.isEmpty }
  }
}
