import AppKit
import ApplicationServices
import Foundation

/// The accessibility tree of another app, as a list a model can act on.
///
/// This is the cheap lane. A screenshot costs a couple of thousand visual tokens
/// and answers "where is the button" with a guess at a coordinate; a snapshot
/// costs a few hundred and answers with the button itself, which can then be
/// pressed by reference. Pixels stay the fallback for apps that publish nothing.
///
/// Two hard rules, both learned from crashes rather than from documentation:
///
///   * **Never walk our own process.** Against a foreign process an accessibility
///     read is IPC and safe from any thread. Against ourselves it materialises
///     our own SwiftUI graph on whatever thread asked, which traps under Swift 6
///     isolation checking. `AccessibilityProcessBoundary` states the rule; this
///     is one of its callers.
///   * **Bound everything.** An unresponsive app can hold an accessibility reply
///     for as long as the messaging timeout allows, and a deep tree has no
///     natural end. Depth, node count and timeout are all capped.
enum CuaAxReader {
  struct Node: Equatable, Sendable {
    let ref: String
    let role: String
    let subrole: String
    let label: String
    let value: String
    /// Global points, top-left origin — the same space a click takes.
    let frame: CGRect
    let enabled: Bool
    let focused: Bool
    let actions: [String]
    let depth: Int
  }

  struct Snapshot: Sendable {
    let id: String
    let appName: String
    let nodes: [Node]
    /// True when the walk stopped at a cap rather than at the end of the tree.
    let truncated: Bool
  }

  /// Seconds an app gets to answer one accessibility read. The system default is
  /// six, which is long enough for one hung app to stall a whole turn.
  private static let messagingTimeout: Float = 1.5

  /// Every accessibility call in this module runs here, in order. Shared with
  /// `CuaAppControl` so a window move cannot interleave with a tree walk.
  static let queue = DispatchQueue(label: "com.omi.cua.ax")

  /// Attributes worth reading for every node. Anything else is noise in a list
  /// the model has to read in full.
  private static let interestingActions: Set<String> = [
    kAXPressAction, kAXIncrementAction, kAXDecrementAction, kAXConfirmAction, kAXCancelAction,
    kAXShowMenuAction, kAXPickAction, kAXRaiseAction,
  ]

  /// Snapshot an app's accessibility tree. `pid` is the app to read; passing our
  /// own is refused rather than survived.
  static func snapshot(pid: pid_t, maxDepth: Int = 12, maxNodes: Int = 250) async -> Snapshot? {
    guard AccessibilityProcessBoundary.isForeignProcess(pid) else { return nil }
    let appName = NSRunningApplication(processIdentifier: pid)?.localizedName ?? "pid \(pid)"
    return await withCheckedContinuation { continuation in
      queue.async {
        let root = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(root, messagingTimeout)
        var nodes: [Node] = []
        var elements: [String: AXElementBox] = [:]
        var truncated = false
        walk(
          element: root, depth: 0, maxDepth: maxDepth, maxNodes: maxNodes, nodes: &nodes,
          elements: &elements, truncated: &truncated)
        let id = "ax-\(UInt32.random(in: 0..<UInt32.max))"
        CuaAxRegistry.shared.store(snapshot: id, elements: elements)
        continuation.resume(
          returning: Snapshot(id: id, appName: appName, nodes: nodes, truncated: truncated))
      }
    }
  }

  /// The frontmost app, which is what "look at the screen" means when nothing
  /// names an app.
  ///
  /// `@MainActor`, with `processID(forAppNamed:)`, because AppKit's shared
  /// workspace is not a background-thread API and this module has already lost
  /// the app once to a main-queue assertion (see `CuaKeyMap.KeyboardLayout`).
  @MainActor
  static func frontmostProcessID() -> pid_t? {
    guard let pid = NSWorkspace.shared.frontmostApplication?.processIdentifier,
      AccessibilityProcessBoundary.isForeignProcess(pid)
    else { return nil }
    return pid
  }

  @MainActor
  static func processID(forAppNamed name: String) -> pid_t? {
    let needle = name.lowercased()
    return NSWorkspace.shared.runningApplications.first { app in
      guard app.activationPolicy == .regular else { return false }
      return app.localizedName?.lowercased() == needle
        || app.bundleIdentifier?.lowercased() == needle
    }?.processIdentifier
  }

  enum ActionOutcome: Equatable {
    case performed
    case unknownReference
    case failed(String)
  }

  /// Perform an accessibility action on a snapshotted element.
  static func perform(action: String, ref: String, snapshot: String) async -> ActionOutcome {
    guard let box = CuaAxRegistry.shared.element(ref: ref, snapshot: snapshot) else {
      return .unknownReference
    }
    return await withCheckedContinuation { continuation in
      queue.async {
        let status = AXUIElementPerformAction(box.element, action as CFString)
        continuation.resume(returning: status == .success ? .performed : .failed("\(status.rawValue)"))
      }
    }
  }

  /// Give a snapshotted element keyboard focus, without changing what it holds.
  static func focus(ref: String, snapshot: String) async -> ActionOutcome {
    guard let box = CuaAxRegistry.shared.element(ref: ref, snapshot: snapshot) else {
      return .unknownReference
    }
    return await withCheckedContinuation { continuation in
      queue.async {
        let status = AXUIElementSetAttributeValue(
          box.element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        continuation.resume(returning: status == .success ? .performed : .failed("\(status.rawValue)"))
      }
    }
  }

  /// Set a snapshotted element's value — how a text field is filled without
  /// clicking it, focusing it, and hoping the keystrokes land in the right place.
  static func setValue(_ value: String, ref: String, snapshot: String) async -> ActionOutcome {
    guard let box = CuaAxRegistry.shared.element(ref: ref, snapshot: snapshot) else {
      return .unknownReference
    }
    return await withCheckedContinuation { continuation in
      queue.async {
        AXUIElementSetAttributeValue(box.element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        let status = AXUIElementSetAttributeValue(
          box.element, kAXValueAttribute as CFString, value as CFTypeRef)
        continuation.resume(returning: status == .success ? .performed : .failed("\(status.rawValue)"))
      }
    }
  }

  // MARK: - Walk

  private static func walk(
    element: AXUIElement, depth: Int, maxDepth: Int, maxNodes: Int, nodes: inout [Node],
    elements: inout [String: AXElementBox], truncated: inout Bool
  ) {
    guard depth <= maxDepth else {
      truncated = true
      return
    }
    guard nodes.count < maxNodes else {
      truncated = true
      return
    }

    let role = string(element, kAXRoleAttribute)
    if depth > 0, !role.isEmpty {
      let ref = "e\(nodes.count + 1)"
      elements[ref] = AXElementBox(element)
      nodes.append(
        Node(
          ref: ref,
          role: role,
          subrole: string(element, kAXSubroleAttribute),
          label: label(element),
          value: string(element, kAXValueAttribute),
          frame: frame(element),
          enabled: bool(element, kAXEnabledAttribute) ?? true,
          focused: bool(element, kAXFocusedAttribute) ?? false,
          actions: actions(element),
          depth: depth))
    }

    var rawChildren: CFTypeRef?
    guard
      AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &rawChildren)
        == .success,
      let children = rawChildren as? [AXUIElement]
    else { return }
    for child in children {
      walk(
        element: child, depth: depth + 1, maxDepth: maxDepth, maxNodes: maxNodes, nodes: &nodes,
        elements: &elements, truncated: &truncated)
    }
  }

  /// What a person would call this element. Title first, then the description an
  /// icon-only control carries, then its help text; an unlabelled control is
  /// listed anyway, because its role and position may be all the model needs.
  private static func label(_ element: AXUIElement) -> String {
    for attribute in [kAXTitleAttribute, kAXDescriptionAttribute, kAXHelpAttribute] {
      let text = string(element, attribute)
      if !text.isEmpty { return text }
    }
    return ""
  }

  private static func actions(_ element: AXUIElement) -> [String] {
    var raw: CFArray?
    guard AXUIElementCopyActionNames(element, &raw) == .success,
      let names = raw as? [String]
    else { return [] }
    return names.filter { interestingActions.contains($0) }
  }

  private static func string(_ element: AXUIElement, _ attribute: String) -> String {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success else {
      return ""
    }
    if let text = raw as? String { return text }
    if let attributed = raw as? NSAttributedString { return attributed.string }
    if let number = raw as? NSNumber { return number.stringValue }
    return ""
  }

  private static func bool(_ element: AXUIElement, _ attribute: String) -> Bool? {
    var raw: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &raw) == .success,
      let number = raw as? NSNumber
    else { return nil }
    return number.boolValue
  }

  private static func frame(_ element: AXUIElement) -> CGRect {
    var origin = CGPoint.zero
    var size = CGSize.zero
    var rawPosition: CFTypeRef?
    var rawSize: CFTypeRef?
    if AXUIElementCopyAttributeValue(element, kAXPositionAttribute as CFString, &rawPosition)
      == .success, let value = rawPosition, CFGetTypeID(value) == AXValueGetTypeID()
    {
      AXValueGetValue(unsafeDowncast(value as AnyObject, to: AXValue.self), .cgPoint, &origin)
    }
    if AXUIElementCopyAttributeValue(element, kAXSizeAttribute as CFString, &rawSize) == .success,
      let value = rawSize, CFGetTypeID(value) == AXValueGetTypeID()
    {
      AXValueGetValue(unsafeDowncast(value as AnyObject, to: AXValue.self), .cgSize, &size)
    }
    return CGRect(origin: origin, size: size)
  }
}

/// `AXUIElement` is a CoreFoundation type with no `Sendable` conformance and no
/// thread affinity of its own; the affinity that matters is the one this module
/// imposes, which is that every read happens on `CuaAxReader.queue`.
struct AXElementBox: @unchecked Sendable {
  let element: AXUIElement

  init(_ element: AXUIElement) {
    self.element = element
  }
}

/// Elements from recent snapshots, so a reference the model just read still
/// resolves when it acts on it.
///
/// Two snapshots are kept. One is not enough — a model routinely snapshots, looks
/// at a screenshot, then acts on the earlier refs — and an unbounded registry
/// pins every element of every app the session ever looked at.
final class CuaAxRegistry: @unchecked Sendable {
  static let shared = CuaAxRegistry()

  private let lock = NSLock()
  private var snapshots: [(id: String, elements: [String: AXElementBox])] = []

  func store(snapshot id: String, elements: [String: AXElementBox]) {
    lock.lock()
    snapshots.append((id, elements))
    if snapshots.count > 2 { snapshots.removeFirst(snapshots.count - 2) }
    lock.unlock()
  }

  func element(ref: String, snapshot id: String) -> AXElementBox? {
    lock.lock()
    defer { lock.unlock() }
    return snapshots.first { $0.id == id }?.elements[ref]
  }

  func latestSnapshotID() -> String? {
    lock.lock()
    defer { lock.unlock() }
    return snapshots.last?.id
  }
}
