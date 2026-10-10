import CoreGraphics
import Foundation

@testable import Omi_Computer

/// One element of a fixture accessibility tree.
struct FixtureAXNode {
  var attributes: [String: AccessibilityAttributeValue]
  var actions: [String] = []
  var settable = false
  var children: [FixtureAXNode] = []
  /// When set, the first N children are the container's visible rows.
  var visibleRowCount: Int?
  /// Selected within its list, table or outline.
  var isSelected = false
  /// Every read of this element times out, as a hung app does.
  var timesOut = false
  /// Hidden until an assistive-tree flag is switched on and a moment has
  /// passed, as Electron and Chromium do.
  var assistiveOnly = false
}

/// Builds a fixture element. `frame` is in screen coordinates; the default
/// sits inside the default fixture window.
func axNode(
  _ role: String,
  _ title: String? = nil,
  subrole: String? = nil,
  description: String? = nil,
  value: AccessibilityAttributeValue? = nil,
  identifier: String? = nil,
  placeholder: String? = nil,
  actions: [String] = [],
  settable: Bool = false,
  focused: Bool = false,
  enabled: Bool = true,
  frame: CGRect = CGRect(x: 120, y: 120, width: 80, height: 20),
  selected: Bool = false,
  visibleRowCount: Int? = nil,
  timesOut: Bool = false,
  assistiveOnly: Bool = false,
  children: [FixtureAXNode] = []
) -> FixtureAXNode {
  var attributes: [String: AccessibilityAttributeValue] = [
    AXName.role: .string(role),
    AXName.enabled: .bool(enabled),
    AXName.focused: .bool(focused),
    AXName.position: .point(frame.origin),
    AXName.size: .size(frame.size),
  ]
  if let title { attributes[AXName.title] = .string(title) }
  if let subrole { attributes[AXName.subrole] = .string(subrole) }
  if let description { attributes[AXName.description] = .string(description) }
  if let value { attributes[AXName.value] = value }
  if let identifier { attributes[AXName.identifier] = .string(identifier) }
  if let placeholder { attributes[AXName.placeholder] = .string(placeholder) }
  return FixtureAXNode(
    attributes: attributes, actions: actions, settable: settable, children: children,
    visibleRowCount: visibleRowCount, isSelected: selected, timesOut: timesOut, assistiveOnly: assistiveOnly)
}

/// Records every read and write so tests can prove what was asked of the app.
final class FixtureAXRecorder {
  var attributeReads: [(element: Int, names: [String])] = []
  var flagWrites: [(name: String, value: Bool)] = []
  var visitedElements: Set<Int> = []
}

/// A fake app: windows of fixture trees, flattened to integer element ids.
/// `0` is the application element.
struct FixtureAccessibilitySource: AccessibilityElementSource {
  typealias Element = Int

  let application = 0
  private(set) var nodes: [Int: FixtureAXNode] = [:]
  private(set) var childIDs: [Int: [Int]] = [:]
  let windowIDs: [Int]
  let focusedWindowID: Int?
  let recorder: FixtureAXRecorder
  let clock: FixtureClock?
  var appFlags: [String: Bool]
  let secondsPerRead: TimeInterval
  var apiDisabled = false

  init(
    windows: [FixtureAXNode], focusedIndex: Int? = 0, recorder: FixtureAXRecorder = FixtureAXRecorder(),
    clock: FixtureClock? = nil, secondsPerRead: TimeInterval = 0, appFlags: [String: Bool] = [:]
  ) {
    self.recorder = recorder
    self.clock = clock
    self.secondsPerRead = secondsPerRead
    self.appFlags = appFlags
    var nextID = 1
    var nodes: [Int: FixtureAXNode] = [:]
    var childIDs: [Int: [Int]] = [:]
    func flatten(_ node: FixtureAXNode) -> Int {
      let id = nextID
      nextID += 1
      nodes[id] = node
      childIDs[id] = node.children.map(flatten)
      return id
    }
    let roots = windows.map(flatten)
    self.nodes = nodes
    self.childIDs = childIDs
    windowIDs = roots
    focusedWindowID = focusedIndex.map { roots[$0] }
  }

  private func touch(_ element: Int) throws(AccessibilitySourceError) -> FixtureAXNode {
    if apiDisabled { throw .apiDisabled }
    clock?.advance(secondsPerRead)
    guard let node = nodes[element] else { throw .invalidElement }
    if node.timesOut { throw .timedOut }
    recorder.visitedElements.insert(element)
    return node
  }

  func windows() throws(AccessibilitySourceError) -> [Int] {
    if apiDisabled { throw .apiDisabled }
    return windowIDs
  }

  func focusedWindow() throws(AccessibilitySourceError) -> Int? { focusedWindowID }
  func mainWindow() throws(AccessibilitySourceError) -> Int? { nil }

  func windowID(of window: Int) -> CGWindowID? {
    windowIDs.firstIndex(of: window).map { CGWindowID(4_400 + $0) }
  }

  func attributes(_ names: [String], of element: Int) throws(AccessibilitySourceError)
    -> [String: AccessibilityAttributeValue]
  {
    let node = try touch(element)
    recorder.attributeReads.append((element, names))
    return node.attributes.filter { names.contains($0.key) }
  }

  func actionNames(of element: Int) throws(AccessibilitySourceError) -> [String] {
    try touch(element).actions
  }

  func isValueSettable(_ element: Int) throws(AccessibilitySourceError) -> Bool {
    try touch(element).settable
  }

  func children(of element: Int, preferVisible: Bool, head: Int, tail: Int) throws(AccessibilitySourceError)
    -> AccessibilityChildren<Int>
  {
    let node = try touch(element)
    // Like Electron, the assistive tree is built a moment after the switch.
    let assistiveTreeOn = recorder.flagWrites.contains { $0.value } && clock?.pauses.isEmpty == false
    var all = (childIDs[element] ?? []).filter { assistiveTreeOn || nodes[$0]?.assistiveOnly != true }
    var visibleOnly = false
    if preferVisible, let visible = node.visibleRowCount {
      all = Array(all.prefix(visible))
      visibleOnly = true
    }
    let children = AccessibilityChildren<Int>.ranges(total: all.count, head: head, tail: tail).flatMap { range in
      range.map { AccessibilityChildren<Int>.Child(index: $0, element: all[$0]) }
    }
    return AccessibilityChildren(elements: children, total: all.count, visibleOnly: visibleOnly)
  }

  func selectedRows(of element: Int) throws(AccessibilitySourceError) -> [Int] {
    _ = try touch(element)
    return (childIDs[element] ?? []).filter { nodes[$0]?.isSelected == true }
  }

  /// The app's current value: the last write, else the starting value.
  func appFlag(_ name: String) -> Bool? {
    recorder.flagWrites.last { $0.name == name }?.value ?? appFlags[name]
  }

  @discardableResult func setAppFlag(_ name: String, _ value: Bool) -> Bool {
    recorder.flagWrites.append((name, value))
    return true
  }
}

final class FixtureClock {
  private(set) var now: TimeInterval = 1_000
  private(set) var pauses: [TimeInterval] = []

  func advance(_ seconds: TimeInterval) { now += seconds }

  func pause(_ seconds: TimeInterval) {
    pauses.append(seconds)
    now += seconds
  }
}

extension WindowSnapshotWalker where Source == FixtureAccessibilitySource {
  init(fixture: FixtureAccessibilitySource, clock: FixtureClock = FixtureClock()) {
    self.init(source: fixture, now: { clock.now }, pause: { clock.pause($0) })
  }
}

let fixtureWindowFrame = CGRect(x: 100, y: 100, width: 800, height: 600)

/// A standard window over the default fixture frame.
func fixtureWindow(_ title: String, frame: CGRect = fixtureWindowFrame, children: [FixtureAXNode]) -> FixtureAXNode {
  axNode("AXWindow", title, subrole: "AXStandardWindow", frame: frame, children: children)
}
