import CoreGraphics
import CryptoKit
import Foundation

struct WindowSnapshotLimits: Equatable, Sendable {
  static let maxNodesCeiling = 400

  /// Elements emitted into the result.
  var maxNodes = maxNodesCeiling
  /// Depth below the window, counting only informative elements: anonymous
  /// wrapper groups (Electron and Chromium nest dozens around web content)
  /// cost no depth.
  var maxDepth = 12
  /// Raw accessibility depth, wrappers included: an absolute stop.
  var maxRawDepth = 64
  /// Elements read, emitted or not: pruned containers still cost IPC.
  var maxVisited = 2_000
  /// Wall-clock budget for the whole read.
  var deadline: TimeInterval = 3
  /// Longer text (a value, a label, a window title) is left out and only its
  /// length is reported; nothing is shortened and sent.
  var maxTextCharacters = 300
  /// Children read from one container, half from its start and half from its
  /// end, so one huge group cannot use up the visit budget for the rest of the
  /// window and the newest rows of a long log are still read.
  var maxChildrenPerContainer = 200
  /// An `n:` reference is used only for labels this short.
  var maxReferenceLabelCharacters = 80
}

/// Electron and Chromium apps expose their elements only to an assistive
/// client, which they detect through these app-level switches. Either switch
/// is turned on for the read and turned back off afterwards, on every exit,
/// only if Omi turned it on and it is still on: a read leaves no lasting
/// change in the other app, and another assistive client's switch is kept.
enum AssistiveTreeMode: Equatable, Sendable {
  case none
  /// `AXManualAccessibility`.
  case electron
  /// `AXEnhancedUserInterface`, which also changes Chromium's window
  /// behaviour while it is on.
  case chromium

  /// The app-level switch this mode turns on, if any.
  var switchName: String? {
    switch self {
    case .none: return nil
    case .electron: return AXName.manualAccessibility
    case .chromium: return AXName.enhancedUserInterface
    }
  }

  /// For the log: which switch the read used.
  var logName: String {
    switch self {
    case .none: return "none"
    case .electron: return "electron"
    case .chromium: return "chromium"
    }
  }
}

struct WindowSnapshotRequest: Equatable, Sendable {
  var windowID: CGWindowID?
  var windowTitle: String?
  var limits = WindowSnapshotLimits()
  var assistiveTree = AssistiveTreeMode.none
  /// Set for System Settings: the open pane is checked before anything is read.
  var paneGuard: SettingsPaneGuard?
}

struct WindowSnapshotFailure: Error, Equatable, Sendable {
  let reason: String
  let message: String
  var windows: [WindowSnapshotWindowSummary] = []
}

/// Reads one window of another app into named elements.
///
/// The walk is pure over an `AccessibilityElementSource`, so every limit and
/// every redaction rule is tested against fixture trees shaped like real
/// AppKit, Catalyst and Electron apps. It never acts: the source has no
/// action method, and the only write is the assistive-tree switch.
struct WindowSnapshotWalker<Source: AccessibilityElementSource> {
  typealias Element = Source.Element

  /// The closed action vocabulary, mirroring the Windows helper's patterns.
  /// `AXRaise` and anything unknown are never listed.
  static var actionVocabulary: [(axAction: String, name: String)] {
    [
      ("AXPress", "press"), ("AXShowMenu", "menu"), ("AXIncrement", "adjust"), ("AXDecrement", "adjust"),
      ("AXConfirm", "confirm"), ("AXPick", "pick"),
    ]
  }

  static var textRoles: Set<String> { ["AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"] }
  static var toggleRoles: Set<String> {
    ["AXCheckBox", "AXRadioButton", "AXSwitch", "AXToggle", "AXDisclosureTriangle"]
  }
  /// Roles whose `AXValue` is worth reading; everything else skips that IPC.
  static var valueRoles: Set<String> {
    textRoles.union(toggleRoles).union([
      "AXStaticText", "AXSlider", "AXIncrementor", "AXPopUpButton", "AXMenuButton", "AXValueIndicator",
      "AXProgressIndicator", "AXLevelIndicator", "AXCell", "AXHeading", "AXLink",
    ])
  }
  /// Kept even without a label, so the model sees the window's structure.
  static var structuralRoles: Set<String> {
    [
      "AXSheet", "AXDialog", "AXWebArea", "AXList", "AXTable", "AXOutline", "AXRow", "AXMenu", "AXMenuBar",
      "AXToolbar", "AXTabGroup", "AXBrowser",
    ]
  }
  static var visibleRowContainers: Set<String> { ["AXTable", "AXOutline", "AXList", "AXBrowser"] }
  /// Containers that, with no label, value, identifier or action of their own
  /// (a context menu alone does not count), only wrap other elements.
  static var wrapperRoles: Set<String> {
    ["AXGroup", "AXGenericElement", "AXUnknown", "AXSplitGroup", "AXScrollArea", "AXLayoutArea", "AXLayoutItem"]
  }

  let source: Source
  /// Monotonic seconds.
  let now: () -> TimeInterval
  /// Waits before the one retry after turning on an assistive tree.
  let pause: (TimeInterval) -> Void
  /// Checked at every element; the executor wires it to the calling task's cancellation.
  var isCancelled: () -> Bool = { Task.isCancelled }

  func snapshot(_ request: WindowSnapshotRequest) -> Result<WindowSnapshot, WindowSnapshotFailure> {
    let start = now()
    let deadline = start + request.limits.deadline
    let isExpired = { now() >= deadline || isCancelled() }
    if isCancelled() {
      return .failure(WindowSnapshotFailure(reason: "cancelled", message: "The read was cancelled before it began."))
    }
    var assistiveTreeEnabled = false
    var switchToRestore: String?
    if let name = request.assistiveTree.switchName {
      if source.appFlag(name) == true {
        assistiveTreeEnabled = true
      } else if source.setAppFlag(name, true) {
        assistiveTreeEnabled = true
        switchToRestore = name
      }
    }
    defer {
      // Only Omi's own change is undone, and only while it still stands, so
      // another assistive client that turned the switch on keeps it.
      if let name = switchToRestore, source.appFlag(name) == true {
        source.setAppFlag(name, false)
      }
    }

    do {
      let windows = try listWindows(isExpired: isExpired, limits: request.limits)
      let chosen = try chooseWindow(request, windows: windows, limits: request.limits)
      if let paneGuard = request.paneGuard {
        // Every Settings window must be identified, the one read first.
        for window in [chosen] + windows.filter({ $0.element != chosen.element }) {
          let verdict = paneGuard.evaluate(
            window: window.element, title: window.fullTitle, source: source, isExpired: isExpired)
          if let failure = verdict.failure { return .failure(failure) }
        }
      }
      let bounds = try windowBounds(chosen.element)
      var walk = walkWindow(chosen.element, bounds: bounds, request: request, deadline: deadline)
      if let fatal = walk.fatal { return .failure(fatal) }
      var retried = false
      if assistiveTreeEnabled, Self.sparseReason(walk.nodes, stopReason: walk.stopReason) != nil,
        now() + 0.3 < deadline
      {
        // The tree is built on the first assistive request; look once more.
        pause(0.3)
        retried = true
        let retry = walkWindow(chosen.element, bounds: bounds, request: request, deadline: deadline)
        if let fatal = retry.fatal { return .failure(fatal) }
        if retry.nodes.count >= walk.nodes.count { walk = retry }
      }
      let others = windows.filter { $0.element != chosen.element }.prefix(10).map(\.summary)
      let ordered = WindowSnapshotOrdering.contentFirst(Self.assigningReferences(walk.nodes, limits: request.limits))
      var snapshot =
        WindowSnapshot(
          window: chosen.summary,
          isFocusedWindow: chosen.isFocused,
          otherWindows: Array(others),
          nodes: ordered.nodes,
          visited: walk.visited,
          stopReason: walk.stopReason,
          childrenOmitted: walk.childrenOmitted,
          sparseReason: Self.sparseReason(walk.nodes, stopReason: walk.stopReason),
          assistiveTreeEnabled: assistiveTreeEnabled,
          assistiveTreeRetried: retried,
          elapsedMilliseconds: Int(((now() - start) * 1_000).rounded()))
      snapshot.isContentFirst = ordered.reordered
      return .success(snapshot)
    } catch {
      return .failure(error)
    }
  }

  /// Why the snapshot says little about the window, or nil: fewer than five
  /// elements, none the model could act on, or a walk cut off by depth that
  /// found almost nothing beyond the window's own buttons.
  static func sparseReason(_ nodes: [WindowSnapshotNode], stopReason: WindowSnapshot.StopReason?) -> String? {
    if nodes.count < 5 { return "few_elements" }
    if !nodes.contains(where: { !$0.actions.isEmpty }) { return "no_actions" }
    if stopReason == .depthLimit {
      let chrome: Set<String> = ["AXCloseButton", "AXMinimizeButton", "AXZoomButton", "AXFullScreenButton"]
      let informative = nodes.filter { ($0.label != nil || $0.value != nil) && !chrome.contains($0.subrole ?? "") }
      if informative.count < 20 { return "depth_limit" }
    }
    return nil
  }

  // MARK: - Windows

  private struct Window {
    let element: Element
    /// Sanitized and complete: matched against, never sent.
    let fullTitle: String
    let summary: WindowSnapshotWindowSummary
    let subrole: String?
    var isFocused = false
  }

  private func window(_ element: Element, title raw: String?, subrole: String?, limits: WindowSnapshotLimits)
    -> Window
  {
    let title = WindowSnapshotText.sanitize(raw ?? "")
    return Window(
      element: element, fullTitle: title,
      summary: WindowSnapshotWindowSummary(
        windowID: source.windowID(of: element),
        text: WindowSnapshotText.bounded(WindowSnapshotText.redactingURLs(title), limits: limits)),
      subrole: subrole)
  }

  private func listWindows(isExpired: () -> Bool, limits: WindowSnapshotLimits) throws(WindowSnapshotFailure)
    -> [Window]
  {
    do throws(AccessibilitySourceError) {
      var windows: [Window] = []
      for element in try source.windows().prefix(50) {
        if isExpired() { break }
        let attributes = try source.attributes([AXName.title, AXName.subrole], of: element)
        windows.append(
          window(
            element, title: attributes[AXName.title]?.string, subrole: attributes[AXName.subrole]?.string,
            limits: limits))
      }
      return windows
    } catch {
      throw Self.failure(error)
    }
  }

  private func chooseWindow(_ request: WindowSnapshotRequest, windows: [Window], limits: WindowSnapshotLimits)
    throws(WindowSnapshotFailure) -> Window
  {
    let summaries = windows.map(\.summary)
    var focused: Element?
    do throws(AccessibilitySourceError) {
      focused = try source.focusedWindow()
      if focused == nil { focused = try source.mainWindow() }
    } catch {
      throw Self.failure(error)
    }
    var chosen: Window?
    if let windowID = request.windowID {
      chosen = windows.first { $0.summary.windowID == windowID }
      if chosen == nil {
        throw WindowSnapshotFailure(
          reason: "window_not_found", message: "No window of this app has number \(windowID).", windows: summaries)
      }
    } else if let wanted = request.windowTitle?.trimmingCharacters(in: .whitespacesAndNewlines), !wanted.isEmpty {
      let needle = WindowSnapshotText.sanitize(wanted).lowercased()
      let exact = windows.filter { $0.fullTitle.lowercased() == needle }
      let partial = windows.filter { $0.fullTitle.lowercased().contains(needle) }
      if exact.count == 1 {
        chosen = exact[0]
      } else if exact.isEmpty, partial.count == 1 {
        chosen = partial[0]
      } else {
        throw WindowSnapshotFailure(
          reason: exact.count + partial.count == 0 ? "window_not_found" : "window_ambiguous",
          message: exact.count + partial.count == 0
            ? "No window title matches. Pick one from windows, or pass window_id."
            : "More than one window matches. Pass window_id from windows.",
          windows: summaries)
      }
    } else {
      chosen =
        windows.first { focused != nil && $0.element == focused }
        ?? windows.first { $0.subrole == "AXStandardWindow" }
        ?? windows.first
      if chosen == nil, let focused {
        let title = (try? source.attributes([AXName.title], of: focused))?[AXName.title]?.string
        chosen = window(focused, title: title, subrole: nil, limits: limits)
      }
    }
    guard var window = chosen else {
      throw WindowSnapshotFailure(
        reason: "no_window",
        message:
          "This app has no window Omi can read. It may be minimised or on another Space; Omi never brings it forward.",
        windows: summaries)
    }
    window.isFocused = focused != nil && window.element == focused
    return window
  }

  /// The window's screen frame; an unknown size disables the off-window check.
  private func windowBounds(_ window: Element) throws(WindowSnapshotFailure) -> CGRect {
    do throws(AccessibilitySourceError) {
      let attributes = try source.attributes([AXName.position, AXName.size], of: window)
      var bounds = CGRect.zero
      if case .point(let origin)? = attributes[AXName.position] { bounds.origin = origin }
      if case .size(let size)? = attributes[AXName.size] { bounds.size = size }
      return bounds
    } catch {
      throw Self.failure(error)
    }
  }

  static func failure(_ error: AccessibilitySourceError) -> WindowSnapshotFailure {
    switch error {
    case .apiDisabled:
      return WindowSnapshotFailure(
        reason: "accessibility_not_granted", message: "Omi needs Accessibility permission to read app windows.")
    case .timedOut:
      return WindowSnapshotFailure(
        reason: "app_not_responding", message: "The app did not answer. It may be busy; try again shortly.")
    case .invalidElement:
      return WindowSnapshotFailure(
        reason: "no_window", message: "The window closed or the app does not expose it to Accessibility.")
    }
  }
}
