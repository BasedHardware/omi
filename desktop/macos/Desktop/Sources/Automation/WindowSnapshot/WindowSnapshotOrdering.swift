import Foundation

/// Puts a window's main content before its sidebars, toolbars and chrome.
///
/// The model sees as many element lines as fit its budget, in order, and the
/// rest only by searching. In document order a chat app's sidebar of channels
/// fills that view before the conversation does. This finds the region that
/// holds most of the window's text (by the length of text values, not control
/// labels) and moves it to the front. An `AXLandmarkMain` region, when the app
/// marks one, wins. It is a general measure of where the text is, never a rule
/// about any app, and it changes only order: references, fingerprints and
/// paths stay what the walk gave them.
enum WindowSnapshotOrdering {
  /// Below this much text, order hardly matters and document order is kept.
  static let minimumText = 100
  /// The region must hold at least this share of the window's text.
  static let dominantShare = 0.6

  /// Control roles whose label names the control rather than content.
  private static let controlRoles: Set<String> = [
    "AXButton", "AXLink", "AXMenuButton", "AXPopUpButton", "AXCheckBox", "AXRadioButton", "AXTab", "AXMenuItem",
    "AXMenuBarItem", "AXDisclosureTriangle", "AXSlider", "AXIncrementor", "AXSwitch", "AXToggle", "AXComboBox",
  ]

  /// How much readable text an element carries.
  static func textWeight(_ node: WindowSnapshotNode) -> Int {
    var weight = 0
    switch node.value {
    case .text(let text): weight += text.count
    case .omitted(let characters): weight += characters
    default: break
    }
    if !controlRoles.contains(node.role) {
      switch node.label {
      case .text(let text)?: weight += text.count
      case .omitted(let characters)?: weight += characters
      case nil: break
      }
    }
    return weight
  }

  /// The path of the main content region, or nil to keep document order.
  static func contentRegion(_ nodes: [WindowSnapshotNode]) -> [WindowSnapshotNode.PathStep]? {
    if let main = nodes.first(where: { $0.subrole == "AXLandmarkMain" || $0.role == "AXLandmarkMain" }) {
      return main.path
    }
    var weightByPrefix: [[WindowSnapshotNode.PathStep]: Int] = [:]
    var total = 0
    for node in nodes {
      let weight = textWeight(node)
      guard weight > 0 else { continue }
      total += weight
      for length in 1...max(1, node.path.count) where length <= node.path.count {
        weightByPrefix[Array(node.path.prefix(length)), default: 0] += weight
      }
    }
    guard total >= minimumText else { return nil }
    let threshold = Int((Double(total) * dominantShare).rounded(.up))
    // The deepest region that still holds the dominant share of the text.
    return weightByPrefix.filter { $0.value >= threshold }.max { lhs, rhs in
      lhs.key.count != rhs.key.count ? lhs.key.count < rhs.key.count : lhs.value < rhs.value
    }?.key
  }

  /// The nodes with the content region first, its depth dots starting from
  /// zero, then everything else in document order. Returns whether it moved anything.
  static func contentFirst(_ nodes: [WindowSnapshotNode]) -> (nodes: [WindowSnapshotNode], reordered: Bool) {
    guard let region = contentRegion(nodes) else { return (nodes, false) }
    let inRegion = { (node: WindowSnapshotNode) in node.path.starts(with: region) }
    let content = nodes.filter(inRegion)
    guard let firstContent = nodes.firstIndex(where: inRegion), firstContent > 0, !content.isEmpty else {
      return (nodes, false)
    }
    let baseDepth = content.map(\.depth).min() ?? 0
    let lifted = content.map { node -> WindowSnapshotNode in
      var node = node
      node.depth -= baseDepth
      return node
    }
    return (lifted + nodes.filter { !inRegion($0) }, true)
  }
}
