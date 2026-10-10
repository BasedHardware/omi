import CoreGraphics
import Foundation

/// App text as a snapshot may send it: the sanitized text, or only its
/// length when it is longer than the limit. Long text is never shortened and
/// sent.
enum WindowSnapshotAppText: Equatable, Sendable {
  case text(String)
  case omitted(characters: Int)

  var text: String? {
    if case .text(let text) = self { return text }
    return nil
  }
}

/// One named element of another app's window, as `ui_snapshot` reports it.
struct WindowSnapshotNode: Equatable, Sendable {
  enum Value: Equatable, Sendable {
    case text(String)
    /// Long text is never sent; only its length.
    case omitted(characters: Int)
    case toggle(Bool)
    case number(String)
  }

  /// One step from the window to the element. A visible-row step indexes the
  /// container's visible rows rather than its raw children.
  enum PathStep: Hashable, Sendable {
    case child(Int)
    case visibleRow(Int)
  }

  let role: String
  let subrole: String?
  let label: WindowSnapshotAppText?
  let value: Value?
  let identifier: String?
  /// From the closed vocabulary in `WindowSnapshotWalker.actionVocabulary`.
  let actions: [String]
  let isSecure: Bool
  let isFocused: Bool
  let isDisabled: Bool
  let path: [PathStep]
  /// Relative to the window origin. Feeds the fingerprint only; coordinates
  /// are never sent to the model, so nothing can click by position.
  let frame: CGRect?
  /// How many emitted ancestors the element has; drawn as leading dots.
  var depth: Int
  var ref = ""
  var fingerprint = ""
}

struct WindowSnapshotWindowSummary: Equatable, Sendable {
  let windowID: CGWindowID?
  let text: WindowSnapshotAppText?

  var title: String? { text?.text }
}

struct WindowSnapshot: Equatable, Sendable {
  enum StopReason: String, Sendable {
    case nodeLimit = "node_limit"
    case visitLimit = "visit_limit"
    case deadline
    case appNotResponding = "app_not_responding"
    case depthLimit = "depth_limit"
    case childLimit = "child_limit"
    case cancelled
  }

  let window: WindowSnapshotWindowSummary
  let isFocusedWindow: Bool
  let otherWindows: [WindowSnapshotWindowSummary]
  let nodes: [WindowSnapshotNode]
  let visited: Int
  let stopReason: StopReason?
  /// Children of oversized containers that were not read.
  let childrenOmitted: Int
  /// Why the snapshot says little, or nil.
  let sparseReason: String?
  let assistiveTreeEnabled: Bool
  /// The read was repeated once because the first pass after turning the
  /// assistive tree on was sparse.
  let assistiveTreeRetried: Bool
  /// The window's main content region was moved before its sidebars and chrome.
  var isContentFirst = false
  let elapsedMilliseconds: Int

  var isComplete: Bool { stopReason == nil }
  var isSparse: Bool { sparseReason != nil }

  var lines: [String] { nodes.map(Self.line) }

  /// `<dots> <ref> <role> "<label>" value="…" [actions] flags fp=<hex>`.
  ///
  /// Depth is a run of `·` because the kernel's projection collapses
  /// whitespace. An `n:` reference already carries the role and the label,
  /// so they are not repeated after it. Every piece of app text is quoted
  /// with `"` and `\` escaped, so it cannot pose as a flag or another field.
  static func line(_ node: WindowSnapshotNode) -> String {
    var parts: [String] = []
    if node.depth > 0 { parts.append(String(repeating: "·", count: node.depth)) }
    parts.append(node.ref)
    if !node.ref.hasPrefix("n:") {
      parts.append(node.subrole.map { "\(node.role)(\($0))" } ?? node.role)
      switch node.label {
      case .text(let label)?: parts.append(quoted(label))
      case .omitted(let characters)?: parts.append("label_chars=\(characters)")
      case nil: break
      }
    } else if let subrole = node.subrole {
      parts.append("(\(subrole))")
    }
    switch node.value {
    case .text(let text): parts.append("value=\(quoted(text))")
    case .omitted(let characters): parts.append("value_chars=\(characters)")
    case .toggle(let on): parts.append("value=\(on ? "on" : "off")")
    case .number(let number): parts.append("value=\(number)")
    case nil: break
    }
    if !node.actions.isEmpty { parts.append("[\(node.actions.joined(separator: ","))]") }
    if node.isSecure { parts.append("secure") }
    if node.isFocused { parts.append("focused") }
    if node.isDisabled { parts.append("disabled") }
    parts.append("fp=\(node.fingerprint)")
    return parts.joined(separator: " ")
  }

  static func quoted(_ text: String) -> String {
    let escaped = text.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
    return "\"\(escaped)\""
  }

  static func pathRef(_ path: [WindowSnapshotNode.PathStep]) -> String {
    let steps = path.map { step -> String in
      switch step {
      case .child(let index): return "\(index)"
      case .visibleRow(let index): return "v\(index)"
      }
    }
    return "p:" + (steps.isEmpty ? "root" : steps.joined(separator: "."))
  }

  /// `key="text"` for app text, or `key_chars=<n>` when it was left out.
  static func field(_ key: String, _ text: WindowSnapshotAppText?) -> String {
    switch text {
    case .text(let text)?: return "\(key)=\(quoted(text))"
    case .omitted(let characters)?: return "\(key)_chars=\(characters)"
    case nil: return "\(key)=\"\""
    }
  }

  /// One line of facts Omi measured, written first; the app's own name and
  /// window title come last, quoted, so neither can pose as a header field.
  func headerLine(appName: WindowSnapshotAppText?, bundleID: String, pid: pid_t) -> String {
    var parts = ["window", "bundle_id=\(bundleID)", "pid=\(pid)"]
    if let windowID = window.windowID { parts.append("window_id=\(windowID)") }
    parts += [
      "focused_window=\(isFocusedWindow)", "complete=\(isComplete)",
      "stop_reason=\(stopReason?.rawValue ?? "none")", "sparse=\(isSparse)", "sparse_reason=\(sparseReason ?? "none")",
      "node_count=\(nodes.count)",
      "visited=\(visited)", "children_omitted=\(childrenOmitted)",
      "order=\(isContentFirst ? "content_first" : "document")", "assistive_tree_enabled=\(assistiveTreeEnabled)",
      "elapsed_ms=\(elapsedMilliseconds)", Self.field("app", appName), Self.field("window_title", window.text),
    ]
    return parts.joined(separator: " ")
  }

  /// The tool result: the header line and the other windows, then one string
  /// per element. Every item is a plain string, so the kernel's projection
  /// keeps the header first and renders nothing out of order; it keeps as
  /// many elements as fit its 8 KB budget and stores the rest for
  /// `search_tool_output`. The result carries facts only; how to read it is in
  /// the tool's manifest guidelines.
  func payload(appName: WindowSnapshotAppText?, bundleID: String, pid: pid_t) -> [String: Any] {
    let others = otherWindows.map { other -> String in
      var parts = ["other_window"]
      if let windowID = other.windowID { parts.append("window_id=\(windowID)") }
      parts.append(Self.field("window_title", other.text))
      return parts.joined(separator: " ")
    }
    let header = headerLine(appName: appName, bundleID: bundleID, pid: pid)
    return [
      "ok": true,
      "sections": [
        ["name": "window", "total": 1 + others.count, "items": [header] + others],
        ["name": "elements", "total": nodes.count, "items": lines],
      ],
    ]
  }
}

/// Text from another app as it is allowed into a snapshot line.
enum WindowSnapshotText {
  /// Collapses every run of whitespace, including line breaks, to one space
  /// and drops control, bidirectional and invisible characters, so a label
  /// cannot break its line, pose as another element or reorder what follows.
  static func sanitize(_ raw: String) -> String {
    var out = String.UnicodeScalarView()
    var pendingSpace = false
    for scalar in raw.unicodeScalars {
      if scalar.properties.isWhitespace || scalar.value == 0x2028 || scalar.value == 0x2029 {
        pendingSpace = !out.isEmpty
        continue
      }
      if isStripped(scalar) { continue }
      if pendingSpace {
        out.append(" ")
        pendingSpace = false
      }
      out.append(scalar)
    }
    return String(out)
  }

  /// The sanitized text, or only its length when it is over the limit; nil when empty.
  static func bounded(_ text: String, limits: WindowSnapshotLimits) -> WindowSnapshotAppText? {
    if text.isEmpty { return nil }
    return text.count > limits.maxTextCharacters ? .omitted(characters: text.count) : .text(text)
  }

  /// App text as it may be sent: sanitized, then every URL-like token in it
  /// redacted.
  static func appText(_ raw: String) -> String {
    redactingURLs(sanitize(raw))
  }

  /// Every URL-like token, with any scheme (`https:`, `file:`, `mailto:`) or
  /// none (an address bar shows `example.com/reset?token=…`), loses its query
  /// string and fragment, and
  /// long opaque path segments become `…`: these carry the tokens of
  /// password-reset and sign-in links.
  static func redactingURLs(_ text: String) -> String {
    guard text.contains(where: { $0 == "?" || $0 == "#" || $0 == "/" }) else { return text }
    return text.split(separator: " ", omittingEmptySubsequences: false).map { redactURLToken(String($0)) }
      .joined(separator: " ")
  }

  private static func redactURLToken(_ token: String) -> String {
    let leading = String(token.prefix { "([<\"'".contains($0) })
    let body = Substring(token.dropFirst(leading.count))
    guard let hostEnd = urlHostEnd(body) else { return token }
    var rest = body[hostEnd...]
    if let cut = rest.firstIndex(where: { $0 == "?" || $0 == "#" }), rest.index(after: cut) < rest.endIndex {
      rest = rest[..<cut]
    }
    let path = rest.split(separator: "/", omittingEmptySubsequences: false).map { segment -> String in
      isOpaque(segment) ? "…" : String(segment)
    }
    return leading + String(body[..<hostEnd]) + path.joined(separator: "/")
  }

  /// Where the host (and port) of a URL-like token ends, or nil when it is not
  /// URL-like. Any scheme counts: `https://host`, `file:///path` (no host),
  /// and schemes with no slashes at all such as `mailto:` or `tel:`, whose
  /// whole remainder is then treated as the path.
  private static func urlHostEnd(_ token: Substring) -> Substring.Index? {
    if let colon = token.firstIndex(of: ":") {
      let scheme = token[..<colon]
      let isScheme =
        scheme.count >= 2 && scheme.first?.isLetter == true
        && scheme.allSatisfy { $0.isLetter || $0.isNumber || $0 == "+" || $0 == "." || $0 == "-" }
      if isScheme {
        let afterColon = token.index(after: colon)
        guard token[afterColon...].hasPrefix("//") else { return afterColon }
        let start = token.index(afterColon, offsetBy: 2)
        return token[start...].firstIndex { $0 == "/" || $0 == "?" || $0 == "#" } ?? token.endIndex
      }
    }
    let end = token.firstIndex { $0 == "/" || $0 == "?" || $0 == "#" } ?? token.endIndex
    let hostAndPort = token[..<end]
    let host = hostAndPort.split(separator: ":", maxSplits: 1).first ?? ""
    let labels = host.split(separator: ".", omittingEmptySubsequences: false)
    guard labels.count >= 2,
      labels.allSatisfy({ !$0.isEmpty && $0.allSatisfy { $0.isLetter || $0.isNumber || $0 == "-" } }),
      let top = labels.last, top.count >= 2, top.allSatisfy(\.isLetter)
    else { return nil }
    return end
  }

  /// A path segment that looks like a token: long, and mixing letters with digits, or very long.
  private static func isOpaque(_ segment: Substring) -> Bool {
    let hasLetter = segment.contains(where: \.isLetter)
    let hasDigit = segment.contains(where: \.isNumber)
    return (segment.count >= 16 && hasLetter && hasDigit) || segment.count >= 32
  }

  private static func isStripped(_ scalar: Unicode.Scalar) -> Bool {
    switch scalar.value {
    case 0x00...0x1F, 0x7F...0x9F,
      0x00AD, 0x061C, 0x180E, 0x200B, 0x200E, 0x200F, 0x202A...0x202E,
      0x2060...0x2064, 0x2066...0x2069, 0xFEFF:
      return true
    default:
      return false
    }
  }
}
