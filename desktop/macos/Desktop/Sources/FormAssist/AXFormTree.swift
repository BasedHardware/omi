import ApplicationServices
import Foundation

/// One accessibility element, flattened out of a window's AX tree.
///
/// Not `Sendable`: `AXUIElement` is a live handle into another process's UI, and the
/// accessibility API is only safe to touch from the main thread. Read the tree on the
/// main actor and hand the rest of the app value types derived from it.
struct AXFormNode {
  let element: AXUIElement
  let role: String
  let title: String
  let value: String
  let placeholder: String
  let description: String
  let help: String
  let frame: CGRect

  var searchableText: String {
    [role, title, value, placeholder, description, help]
      .filter { !$0.isEmpty }
      .joined(separator: " ")
      .lowercased()
  }
}

/// Reads a window's accessibility tree. Shared by the assisted cloud-connector
/// automation and by form assist, which need the same flattened view of a window.
enum AXFormTree {
  static func collectNodes(from root: AXUIElement, maxDepth: Int, maxNodes: Int) -> [AXFormNode] {
    var output: [AXFormNode] = []
    var seen = Set<ObjectIdentifier>()

    func walk(_ element: AXUIElement, depth: Int) {
      guard depth <= maxDepth, output.count < maxNodes else { return }
      let id = ObjectIdentifier(element)
      guard !seen.contains(id) else { return }
      seen.insert(id)

      output.append(node(from: element))
      for child in elementArrayAttribute(element, "AXChildren") {
        walk(child, depth: depth + 1)
      }
      for child in elementArrayAttribute(element, "AXVisibleChildren") {
        walk(child, depth: depth + 1)
      }
    }

    walk(root, depth: 0)
    return output
  }

  static func node(from element: AXUIElement) -> AXFormNode {
    AXFormNode(
      element: element,
      role: stringAttribute(element, "AXRole"),
      title: stringAttribute(element, "AXTitle"),
      value: stringAttribute(element, "AXValue"),
      placeholder: stringAttribute(element, "AXPlaceholderValue"),
      description: stringAttribute(element, "AXDescription"),
      help: stringAttribute(element, "AXHelp"),
      frame: frameAttribute(element)
    )
  }

  static func stringAttribute(_ element: AXUIElement, _ attribute: String) -> String {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return ""
    }
    if let string = raw as? String { return string }
    if let attributed = raw as? NSAttributedString { return attributed.string }
    return ""
  }

  static func elementAttribute(_ element: AXUIElement, _ attribute: String) -> AXUIElement? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return nil
    }
    return ((raw as AnyObject) as! AXUIElement)
  }

  static func elementArrayAttribute(_ element: AXUIElement, _ attribute: String) -> [AXUIElement] {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return []
    }
    return (raw as? [AnyObject])?.map { $0 as! AXUIElement } ?? []
  }

  static func frameAttribute(_ element: AXUIElement) -> CGRect {
    var point = CGPoint.zero
    var size = CGSize.zero
    if let pointValue = rawAttribute(element, "AXPosition") {
      let pointValue = pointValue as! AXValue
      AXValueGetValue(pointValue, .cgPoint, &point)
    }
    if let sizeValue = rawAttribute(element, "AXSize") {
      let sizeValue = sizeValue as! AXValue
      AXValueGetValue(sizeValue, .cgSize, &size)
    }
    return CGRect(origin: point, size: size)
  }

  /// The URL of the web page an element lives in, from its nearest AXWebArea ancestor.
  /// Bounded parent walk; empty when the element is not web content or AX withholds it.
  /// The URL of the web area inside a window, found by walking down from the window
  /// itself. `pageURL(of:)` walks up from whatever has focus, which answers nothing after
  /// a tab click: switching tabs leaves no focused element to start from. Bounded on both
  /// depth and breadth — a web area sits a few containers below the window, and this runs
  /// on every sweep while a panel is up.
  static func pageURL(inWindow window: AXUIElement) -> String {
    var frontier = [window]
    for _ in 0..<maxWebAreaDepth {
      var next: [AXUIElement] = []
      for element in frontier {
        if stringAttribute(element, "AXRole") == "AXWebArea" {
          guard let raw = rawAttribute(element, "AXURL") else { continue }
          if let url = (raw as? URL)?.absoluteString, !url.isEmpty { return url }
          continue
        }
        next += elementArrayAttribute(element, "AXChildren").prefix(maxWebAreaBreadth)
        if next.count >= maxWebAreaNodes { break }
      }
      guard !next.isEmpty else { return "" }
      frontier = Array(next.prefix(maxWebAreaNodes))
    }
    return ""
  }

  private static let maxWebAreaDepth = 8
  private static let maxWebAreaBreadth = 24
  private static let maxWebAreaNodes = 96

  static func pageURL(of element: AXUIElement) -> String {
    var current: AXUIElement? = element
    for _ in 0..<15 {
      guard let el = current else { return "" }
      if stringAttribute(el, "AXRole") == "AXWebArea" {
        guard let raw = rawAttribute(el, "AXURL") else { return "" }
        return (raw as? URL)?.absoluteString ?? ""
      }
      current = elementAttribute(el, "AXParent")
    }
    return ""
  }

  static func rawAttribute(_ element: AXUIElement, _ attribute: String) -> CFTypeRef? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return nil
    }
    return raw
  }
}
