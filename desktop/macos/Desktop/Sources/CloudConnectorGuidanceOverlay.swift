import AppKit
import OmiTheme
import SwiftUI

/// One copy row on the assisted cloud-connector card. `id` must be unique across
/// the card — never derive it from `label` alone (duplicate labels crash SwiftUI).
struct CloudConnectorCopyField: Identifiable, Sendable {
  let id: String
  let label: String
  let value: String
  /// When true, the on-screen preview is masked but copy still uses `value`.
  let masksValue: Bool

  init(id: String, label: String, value: String, masksValue: Bool? = nil) {
    self.id = id
    self.label = label
    self.value = value
    self.masksValue = masksValue ?? Self.defaultMasksValue(label: label, value: value)
  }

  var displayValue: String {
    if value.isEmpty { return "leave blank" }
    return masksValue ? String(repeating: "•", count: 12) : value
  }

  /// Labels that commonly hold secrets when the value is non-empty.
  static func defaultMasksValue(label: String, value: String) -> Bool {
    guard !value.isEmpty else { return false }
    let lower = label.lowercased()
    let sensitiveTerms = ["secret", "key", "token", "password", "credential", "private"]
    return sensitiveTerms.contains { lower.contains($0) }
  }

  /// Crash in debug when callers pass duplicate ids (SwiftUI `ForEach` footgun).
  static func assertUniqueIDs(_ fields: [CloudConnectorCopyField]) {
    #if DEBUG
      let ids = fields.map(\.id)
      precondition(Set(ids).count == ids.count, "CloudConnectorCopyField ids must be unique")
    #endif
  }
}

/// A visible group of copy rows on the assisted cloud-connector card.
struct CloudConnectorCopySection: Identifiable, Sendable {
  let id: String
  let title: String
  let fields: [CloudConnectorCopyField]

  init(id: String, title: String, fields: [CloudConnectorCopyField]) {
    self.id = id
    self.title = title
    self.fields = fields
  }

  var hasVisibleTitle: Bool {
    !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  static func flattenedFields(_ sections: [CloudConnectorCopySection]) -> [CloudConnectorCopyField] {
    sections.flatMap(\.fields)
  }

  static func visibleTitleCount(_ sections: [CloudConnectorCopySection]) -> Int {
    sections.filter(\.hasVisibleTitle).count
  }

  static func assertUniqueIDs(_ sections: [CloudConnectorCopySection]) {
    #if DEBUG
      let sectionIDs = sections.map(\.id)
      precondition(Set(sectionIDs).count == sectionIDs.count, "CloudConnectorCopySection ids must be unique")
    #endif
    CloudConnectorCopyField.assertUniqueIDs(flattenedFields(sections))
  }
}

@MainActor
final class CloudConnectorGuidanceOverlay {
  static let shared = CloudConnectorGuidanceOverlay()

  private var window: NSWindow?
  private var dismissTask: Task<Void, Never>?
  private var settingsWatchTask: Task<Void, Never>?
  private var lastAutomationState: [String: String]?
  private var dragCardSize: CGSize?
  private var dragTargetState: ScreenRecordingDragTargetState?

  private init() {}

  func presentClaudeAddHint(windowFrame: CGRect, candidates: [SpatialOverlayAnchorCandidate]) {
    presentClaudeHint(
      actionLabel: "Add",
      windowFrame: windowFrame,
      candidates: candidates
    )
  }

  func presentClaudeConnectHint(windowFrame: CGRect, candidates: [SpatialOverlayAnchorCandidate]) {
    presentClaudeHint(
      actionLabel: "Connect",
      windowFrame: windowFrame,
      candidates: candidates
    )
  }

  private func presentClaudeHint(
    actionLabel: String,
    windowFrame: CGRect,
    candidates: [SpatialOverlayAnchorCandidate]
  ) {
    dismissTask?.cancel()
    window?.close()

    let overlaySize = CGSize(width: 330, height: 118)
    guard
      let placement = Self.placementResult(
        windowFrame: windowFrame,
        candidates: candidates,
        overlaySize: overlaySize
      )
    else {
      presentInstructionCard(
        title: "Finish in Claude",
        subtitle: "Click \(actionLabel) in the connector window to continue.",
        near: windowFrame
      )
      return
    }

    lastAutomationState = Self.stateDictionary(
      actionLabel: actionLabel,
      placement: placement,
      candidates: candidates,
      overlaySize: overlaySize
    )

    let view = CloudConnectorGuidanceView(actionLabel: actionLabel, placement: placement)
    let hostingController = NSHostingController(rootView: view)
    hostingController.view.frame = CGRect(origin: .zero, size: overlaySize)

    let panel = NSPanel(
      contentRect: placement.panelFrame,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    panel.contentViewController = hostingController
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.level = .popUpMenu
    panel.ignoresMouseEvents = true
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    panel.animationBehavior = .none
    panel.orderFrontRegardless()
    window = panel

    dismissTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 14_000_000_000)
      await MainActor.run {
        guard !Task.isCancelled else { return }
        self?.dismiss()
      }
    }
  }

  /// Non-pointing instruction card, shown when we cannot anchor to a real target (e.g.
  /// the Screen Recording permission fallback). It explains what to do and is placed
  /// near the relevant window (System Settings) so the user connects the dots.
  func presentInstructionCard(title: String, subtitle: String, near anchor: CGRect?) {
    dismissTask?.cancel()
    window?.close()

    let cardSize = Self.instructionCardSize(title: title, subtitle: subtitle)
    let screen = Self.screen(forAnchor: anchor)
    let frame = Self.instructionCardFrame(
      anchor: anchor, cardSize: cardSize, visibleFrame: screen.visibleFrame)

    lastAutomationState = [
      "visible": "true",
      "kind": "instruction",
      "title": title,
      "subtitle": subtitle,
      "panelFrame": Self.string(frame),
    ]

    let view = CloudConnectorInstructionCardView(
      title: title, subtitle: subtitle, size: cardSize,
      onDismiss: { [weak self] in self?.dismiss() })
    let hostingController = NSHostingController(rootView: view)
    hostingController.view.frame = CGRect(origin: .zero, size: cardSize)

    let panel = NSPanel(
      contentRect: frame,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    panel.contentViewController = hostingController
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.level = .popUpMenu
    // The card carries a close button, so it must receive clicks (the pointing overlay
    // stays click-through).
    panel.ignoresMouseEvents = false
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    panel.animationBehavior = .none
    panel.orderFrontRegardless()
    window = panel

    dismissTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 30_000_000_000)
      await MainActor.run {
        guard !Task.isCancelled else { return }
        self?.dismiss()
      }
    }
  }

  /// Screen Recording helper whose app icon can be dropped into System Settings.
  func presentDragToGrantCard(appIcon: NSImage, appName: String, appURL: URL, near anchor: CGRect?) {
    dismissTask?.cancel()
    settingsWatchTask?.cancel()
    window?.close()

    let cardSize = Self.dragCardSize(appName: appName)
    dragCardSize = cardSize
    let screen = Self.screen(forAnchor: anchor)
    let pointsDown = Self.dragCardArrowPointsDown(
      anchor: anchor, cardSize: cardSize, visibleFrame: screen.visibleFrame)
    let dragTargetState = ScreenRecordingDragTargetState(frame: anchor, arrowPointsDown: pointsDown)
    self.dragTargetState = dragTargetState
    let frame = Self.dragCardFrame(
      anchor: anchor, cardSize: cardSize, visibleFrame: screen.visibleFrame)

    lastAutomationState = [
      "visible": "true",
      "kind": "dragToGrant",
      "appName": appName,
      "panelFrame": Self.string(frame),
    ]

    let view = ScreenRecordingDragCardView(
      appIcon: appIcon, appName: appName, appURL: appURL, targetState: dragTargetState,
      size: cardSize)
    let hostingView = TransparentHostingView(rootView: view)
    hostingView.frame = CGRect(origin: .zero, size: cardSize)
    hostingView.wantsLayer = true
    hostingView.layer?.backgroundColor = NSColor.clear.cgColor
    hostingView.layer?.isOpaque = false

    let panel = NSPanel(
      contentRect: frame,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    panel.contentView = hostingView
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.level = .screenSaver
    panel.ignoresMouseEvents = false
    panel.becomesKeyOnlyIfNeeded = true
    // Moving the panel would consume the icon's mouse-down before AppKit starts the drag.
    panel.isMovableByWindowBackground = false
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
    panel.animationBehavior = .none
    let reduceMotion = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
    panel.alphaValue = Self.dragCardInitialAlpha(reduceMotion: reduceMotion)
    panel.orderFrontRegardless()
    if !reduceMotion {
      NSAnimationContext.runAnimationGroup { context in
        context.duration = 0.22
        panel.animator().alphaValue = 1
      }
    }
    window = panel

    dismissTask = Task { [weak self] in
      try? await Task.sleep(nanoseconds: 60_000_000_000)
      await MainActor.run {
        guard !Task.isCancelled else { return }
        self?.dismiss()
      }
    }

    // Follow the System Settings window: re-anchor over it once it appears, and
    // dismiss the card as soon as the user closes it — the drag target is gone.
    settingsWatchTask = Task { [weak self] in
      var sawSettings = false
      while !Task.isCancelled {
        let settingsFrame = await MainActor.run {
          CloudConnectorFormAutomation.systemSettingsWindowAppKitFrame()
        }
        if let settingsFrame {
          sawSettings = true
          await MainActor.run { self?.repositionDragCard(near: settingsFrame) }
        } else if sawSettings {
          // Window appeared and is now gone → the user closed Settings.
          await MainActor.run { self?.dismiss() }
          return
        }
        try? await Task.sleep(nanoseconds: 300_000_000)
      }
    }
  }

  func repositionDragCard(near anchor: CGRect) {
    guard let window, let size = dragCardSize else { return }
    dragTargetState?.frame = anchor
    let screen = Self.screen(forAnchor: anchor)
    dragTargetState?.arrowPointsDown = Self.dragCardArrowPointsDown(
      anchor: anchor, cardSize: size, visibleFrame: screen.visibleFrame)
    let frame = Self.dragCardFrame(
      anchor: anchor, cardSize: size, visibleFrame: screen.visibleFrame)
    window.setFrame(frame, display: true)
    lastAutomationState?["panelFrame"] = Self.string(frame)
  }

  /// Drag-card placement: horizontally centered on the anchor (Settings window)
  /// and pinned directly beneath it, so the card follows the window and never
  /// covers the drop target. If there's no room below (Settings sits near the
  /// screen bottom), flip to just above the window instead. With no anchor yet,
  /// fall back to the bottom quarter of the screen.
  static func dragCardFrame(anchor: CGRect?, cardSize: CGSize, visibleFrame: CGRect) -> CGRect {
    let gap: CGFloat = 12
    let padding: CGFloat = 12
    let x = (anchor ?? visibleFrame).midX - cardSize.width / 2
    let y: CGFloat
    if let anchor {
      // AppKit is bottom-left origin: the window's bottom edge is `minY`, so
      // "under" the window is a smaller y.
      let below = anchor.minY - gap - cardSize.height
      y = below >= visibleFrame.minY + padding ? below : anchor.maxY + gap
    } else {
      y = visibleFrame.minY + (visibleFrame.height / 4 - cardSize.height) / 2
    }
    let proposed = CGRect(x: x, y: y, width: cardSize.width, height: cardSize.height)
    return SpatialOverlayGeometry.clamped(proposed, to: visibleFrame, padding: padding)
  }

  /// Whether the drag card's arrow should point DOWN toward the anchor. The card
  /// normally sits below the Settings window (arrow up), but `dragCardFrame` flips
  /// it above the window when there's no room below — in which case the drop target
  /// (the list) is beneath the card and the arrow must point down. Mirrors the exact
  /// placement decision in `dragCardFrame` so the arrow always points at the list.
  static func dragCardArrowPointsDown(anchor: CGRect?, cardSize: CGSize, visibleFrame: CGRect) -> Bool {
    guard let anchor else { return false }  // no anchor → bottom-of-screen fallback, arrow up
    let gap: CGFloat = 12
    let padding: CGFloat = 12
    let below = anchor.minY - gap - cardSize.height
    let fitsBelow = below >= visibleFrame.minY + padding
    return !fitsBelow
  }

  /// A named development bundle can have a much longer display name than the
  /// production app. Widen the helper rather than allowing its instruction to
  /// render outside the transparent panel and get clipped by AppKit.
  static func dragCardSize(appName: String) -> CGSize {
    let hasLongDisplayName = appName.count > 16
    return CGSize(width: hasLongDisplayName ? 240 : 180, height: hasLongDisplayName ? 180 : 164)
  }

  static func dragCardInitialAlpha(reduceMotion: Bool) -> CGFloat {
    reduceMotion ? 1 : 0
  }

  /// Interactive card with one copy button per connector field, for assisted cloud
  /// setup where the provider's form needs values pasted one at a time. Secrets are
  /// masked on screen but copy their real value.
  func presentFieldCopyCard(
    title: String,
    subtitle: String,
    fields: [CloudConnectorCopyField],
    near anchor: CGRect?
  ) {
    presentFieldCopyCard(
      title: title,
      subtitle: subtitle,
      sections: [CloudConnectorCopySection(id: "fields", title: "", fields: fields)],
      near: anchor
    )
  }

  func presentFieldCopyCard(
    title: String,
    subtitle: String,
    sections: [CloudConnectorCopySection],
    near anchor: CGRect?
  ) {
    dismissTask?.cancel()
    window?.close()

    CloudConnectorCopySection.assertUniqueIDs(sections)
    let fields = CloudConnectorCopySection.flattenedFields(sections)
    let cardSize = Self.fieldCopyCardSize(
      title: title,
      subtitle: subtitle,
      fieldCount: fields.count,
      sectionTitleCount: CloudConnectorCopySection.visibleTitleCount(sections)
    )
    let screen = Self.screen(forAnchor: anchor)
    let frame = Self.instructionCardFrame(
      anchor: anchor, cardSize: cardSize, visibleFrame: screen.visibleFrame)

    lastAutomationState = [
      "visible": "true",
      "kind": "fieldCopy",
      "title": title,
      "subtitle": subtitle,
      "fieldCount": "\(fields.count)",
      "fieldLabels": fields.map(\.label).joined(separator: "|"),
      "panelFrame": Self.string(frame),
    ]

    let view = CloudConnectorFieldCopyCardView(
      title: title,
      subtitle: subtitle,
      sections: sections,
      size: cardSize,
      onDismiss: { [weak self] in self?.dismiss() })
    let hostingController = NSHostingController(rootView: view)
    hostingController.view.frame = CGRect(origin: .zero, size: cardSize)

    let panel = NSPanel(
      contentRect: frame,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    panel.contentViewController = hostingController
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.level = .popUpMenu
    // Copy buttons must receive clicks; .nonactivatingPanel keeps the browser focused.
    panel.ignoresMouseEvents = false
    // The card can sit over the provider's form — let the user drag it anywhere
    // by grabbing any non-button area.
    panel.isMovableByWindowBackground = true
    panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
    panel.animationBehavior = .none
    panel.orderFrontRegardless()
    window = panel

    dismissTask = Task { [weak self] in
      // Generous window: the user works through several fields (and, for ChatGPT,
      // may need to enable Developer mode first).
      try? await Task.sleep(nanoseconds: 240_000_000_000)
      await MainActor.run {
        guard !Task.isCancelled else { return }
        self?.dismiss()
      }
    }
  }

  static func fieldCopyCardSize(
    title: String,
    subtitle: String,
    fieldCount: Int,
    sectionTitleCount: Int = 0
  ) -> CGSize {
    // Match instruction-card subtitle wrapping: long copy needs extra header height.
    let compactSubtitleThreshold = 86
    let headerHeight: CGFloat = subtitle.count <= compactSubtitleThreshold ? 96 : 118
    let sectionHeaderHeight = CGFloat(sectionTitleCount) * 24
    return CGSize(width: 460, height: headerHeight + CGFloat(fieldCount) * 30 + sectionHeaderHeight)
  }

  private static func screen(forAnchor anchor: CGRect?) -> NSScreen {
    if let anchor {
      let overlapping = NSScreen.screens
        .map { screen -> (NSScreen, CGFloat) in
          let r = screen.frame.intersection(anchor)
          let area = (r.isNull || r.isEmpty) ? 0 : r.width * r.height
          return (screen, area)
        }
        .filter { $0.1 > 0 }
        .sorted { $0.1 > $1.1 }
      if let best = overlapping.first?.0 { return best }
    }
    return NSScreen.main ?? NSScreen.screens.first ?? NSScreen()
  }

  /// Pure placement: center the card horizontally on the anchor and pin it near the
  /// anchor's top edge, clamped inside the visible frame. With no anchor, center it in
  /// the upper third of the screen. Testable.
  /// Parse an "x,y,w,h" anchor string (AppKit global) for the dogfood bridge action.
  static func anchorRect(fromParam raw: String?) -> CGRect? {
    guard let parts = raw?.split(separator: ",").map({ Double($0.trimmingCharacters(in: .whitespaces)) }),
      parts.count == 4, let x = parts[0], let y = parts[1], let w = parts[2], let h = parts[3]
    else { return nil }
    return CGRect(x: x, y: y, width: w, height: h)
  }

  static func instructionCardSize(title: String, subtitle: String) -> CGSize {
    let compactThreshold = 86
    let height: CGFloat = subtitle.count <= compactThreshold ? 88 : 118
    return CGSize(width: 420, height: height)
  }

  static func instructionCardFrame(anchor: CGRect?, cardSize: CGSize, visibleFrame: CGRect)
    -> CGRect
  {
    let target = anchor ?? visibleFrame
    let x = target.midX - cardSize.width / 2
    // AppKit: maxY is the top edge. Sit just below the top of the anchored window.
    let y = anchor != nil ? target.maxY - cardSize.height - 24 : target.midY + target.height / 6
    let proposed = CGRect(x: x, y: y, width: cardSize.width, height: cardSize.height)
    return SpatialOverlayGeometry.clamped(proposed, to: visibleFrame, padding: 12)
  }

  func dismiss() {
    dismissTask?.cancel()
    dismissTask = nil
    settingsWatchTask?.cancel()
    settingsWatchTask = nil
    window?.close()
    window = nil
    dragCardSize = nil
    dragTargetState = nil
  }

  var automationWindow: NSWindow? {
    window
  }

  func automationState() -> [String: String] {
    var state = lastAutomationState ?? [:]
    state["visible"] = window?.isVisible == true ? "true" : "false"
    if let window {
      // Live frame, not the frame at present time — the user can drag the card.
      state["panelFrame"] = Self.string(window.frame)
    }
    return state
  }

  func presentAutomationFixture(_ fixture: SpatialOverlayDogfoodFixture) -> [String: String] {
    switch fixture {
    case .claudeAddExplicit, .claudeAddInferredFromCancel, .claudeAddHeuristic:
      presentClaudeAddHint(windowFrame: fixture.windowFrame, candidates: fixture.candidates)
    case .claudeConnectExplicit, .claudeConnectHeuristic:
      presentClaudeConnectHint(windowFrame: fixture.windowFrame, candidates: fixture.candidates)
    }

    var state = automationState()
    state["fixture"] = fixture.rawValue
    state["action"] = fixture.actionLabel.lowercased()
    return state
  }

  static func placementResult(
    windowFrame: CGRect,
    candidates: [SpatialOverlayAnchorCandidate],
    overlaySize: CGSize = CGSize(width: 330, height: 118)
  ) -> SpatialOverlayPlacementResult? {
    for candidate in candidates.filter({ $0.allowedUses.contains(.displayGuidance) }).sorted(by: candidateSort) {
      let spec = SpatialOverlayPlacementSpec(
        overlaySize: overlaySize,
        preferredEdges: [.above, .below, .trailing, .leading],
        gap: 0,
        canCoverTarget: false
      )
      if case .success(let placement) = SpatialOverlayPlacementSolver.place(target: candidate, spec: spec) {
        return placement
      }
    }
    return nil
  }

  private static func candidateSort(
    lhs: SpatialOverlayAnchorCandidate,
    rhs: SpatialOverlayAnchorCandidate
  ) -> Bool {
    let lhsExplicit = lhs.evidence.contains { $0.source == .accessibility || $0.source == .ocr }
    let rhsExplicit = rhs.evidence.contains { $0.source == .accessibility || $0.source == .ocr }
    if lhsExplicit != rhsExplicit {
      return lhsExplicit
    }
    if lhs.confidence != rhs.confidence {
      return lhs.confidence > rhs.confidence
    }
    return lhs.id < rhs.id
  }

  private static func stateDictionary(
    actionLabel: String,
    placement: SpatialOverlayPlacementResult,
    candidates: [SpatialOverlayAnchorCandidate],
    overlaySize: CGSize
  ) -> [String: String] {
    let selected = candidates.first { candidate in
      candidate.targetRect.insetBy(dx: -1, dy: -1).contains(placement.targetPoint)
        || (abs(candidate.targetPoint.x - placement.targetPoint.x) <= 1
          && abs(candidate.targetPoint.y - placement.targetPoint.y) <= 1)
    }
    let targetRect =
      selected?.targetRect
      ?? CGRect(
        x: placement.targetPoint.x - 1,
        y: placement.targetPoint.y - 1,
        width: 2,
        height: 2
      )
    // Validate against the actually-rendered arrow apex, not just the solver intent.
    let render = SpatialOverlayRenderGeometry(placement: placement, panelSize: overlaySize)
    let issues = SpatialOverlayDogfoodOracle.issues(
      arrowTip: render.globalRenderedArrowTip,
      panelFrame: placement.panelFrame,
      targetRect: targetRect,
      coveredTargetRect: targetRect
    )
    return [
      "visible": "true",
      "action": actionLabel.lowercased(),
      "edge": "\(placement.attachmentEdge)",
      "targetRect": string(targetRect),
      "targetPoint": string(placement.targetPoint),
      "panelFrame": string(placement.panelFrame),
      "bubbleFrame": string(render.bubbleFrame),
      "pointerFrame": string(render.pointerFrame),
      "arrowTip": string(placement.globalArrowTip),
      "renderedArrowTip": string(render.globalRenderedArrowTip),
      "attachmentEdge": "\(placement.attachmentEdge)",
      "candidateId": selected?.id ?? "",
      "candidateSource": selected?.evidence.first?.source.rawValue ?? "",
      "issues": issues.map(\.description).joined(separator: "; "),
    ]
  }

  private static func string(_ point: CGPoint) -> String {
    "\(String(format: "%.1f", point.x)),\(String(format: "%.1f", point.y))"
  }

  private static func string(_ rect: CGRect) -> String {
    "\(String(format: "%.1f", rect.minX)),\(String(format: "%.1f", rect.minY)),\(String(format: "%.1f", rect.width)),\(String(format: "%.1f", rect.height))"
  }
}

private struct CloudConnectorCardHeaderView: View {
  let title: String
  let subtitle: String
  let onDismiss: () -> Void

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      SpatialOverlayAccentIcon(systemName: "checklist", diameter: 38)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: 13.5, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
        Text(subtitle)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
          .lineSpacing(1.5)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 0)

      Button(action: onDismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.micro, weight: .bold)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 22, height: 22)
          .background(Circle().fill(Color.white.opacity(0.10)))
          .contentShape(Circle())
      }
      .buttonStyle(.plain)
      .help("Dismiss")
      .accessibilityLabel("Close")
    }
  }
}

private struct CloudConnectorInstructionCardView: View {
  let title: String
  let subtitle: String
  let size: CGSize
  let onDismiss: () -> Void

  var body: some View {
    CloudConnectorCardHeaderView(title: title, subtitle: subtitle, onDismiss: onDismiss)
      .padding(.leading, OmiSpacing.lg)
      .padding(.trailing, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.lg)
      .frame(width: size.width, height: size.height, alignment: .topLeading)
      .background(SpatialOverlayCardBackground())
      .contentShape(Rectangle())
      .onTapGesture(perform: onDismiss)
  }
}

private final class TransparentHostingView<Content: View>: NSHostingView<Content> {
  override var isOpaque: Bool { false }
}

final class ScreenRecordingDragTargetState: ObservableObject {
  var frame: CGRect?
  /// Drives the drag card's arrow direction — true when the card sits above the
  /// Settings window (list is below → point down), false when below (point up).
  @Published var arrowPointsDown: Bool

  init(frame: CGRect?, arrowPointsDown: Bool = false) {
    self.frame = frame
    self.arrowPointsDown = arrowPointsDown
  }
}

/// Uses the same file-URL pasteboard payload as dragging an app from Finder.
final class AppBundleDragSourceNSView: NSView, NSDraggingSource {
  static let fullDragIconSize = CGSize(width: 64, height: 64)
  static let compactDragIconSize = CGSize(width: 38, height: 38)

  var appURL: URL?
  var targetState: ScreenRecordingDragTargetState?
  var image: NSImage? {
    didSet { needsDisplay = true }
  }
  private var currentDragIconSize = fullDragIconSize
  /// While the dragging session is in flight the card must not keep painting the
  /// icon — the dragged copy under the cursor is "it". Restored on end/cancel.
  private var isDragInFlight = false

  static func pasteboardWriter(for appURL: URL) -> NSURL {
    appURL as NSURL
  }

  override func mouseDown(with event: NSEvent) {
    guard let appURL, let image else { return }
    let item = NSDraggingItem(pasteboardWriter: Self.pasteboardWriter(for: appURL))
    item.setDraggingFrame(bounds, contents: image)
    let session = beginDraggingSession(with: [item], event: event, source: self)
    session.draggingFormation = .none
    session.animatesToStartingPositionsOnCancelOrFail = true
    isDragInFlight = true
    needsDisplay = true
  }

  override var isOpaque: Bool { false }

  override func draw(_ dirtyRect: NSRect) {
    super.draw(dirtyRect)
    guard !isDragInFlight else { return }
    image?.draw(
      in: bounds,
      from: .zero,
      operation: .sourceOver,
      fraction: 1,
      respectFlipped: true,
      hints: [.interpolation: NSImageInterpolation.high]
    )
  }

  func draggingSession(
    _ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext
  ) -> NSDragOperation {
    context == .outsideApplication ? [.copy, .generic, .link] : []
  }

  func draggingSession(_ session: NSDraggingSession, movedTo screenPoint: NSPoint) {
    guard let image else { return }
    // Re-anchor the item on every move: once setDraggingFrame has been called
    // mid-session, AppKit stops moving the drag image itself, so skipping events
    // (e.g. only on size change) leaves the icon pinned instead of following the
    // cursor in real time.
    let size = Self.dragIconSize(pointer: screenPoint, targetFrame: targetState?.frame)
    currentDragIconSize = size
    let frame = NSRect(
      x: screenPoint.x - size.width / 2,
      y: screenPoint.y - size.height / 2,
      width: size.width,
      height: size.height)
    session.enumerateDraggingItems(
      options: [], for: nil, classes: [NSURL.self], searchOptions: [:]
    ) { item, _, _ in
      item.setDraggingFrame(frame, contents: image)
    }
  }

  func draggingSession(
    _ session: NSDraggingSession, endedAt screenPoint: NSPoint, operation: NSDragOperation
  ) {
    currentDragIconSize = Self.fullDragIconSize
    isDragInFlight = false
    needsDisplay = true
  }

  static func dragIconSize(pointer: CGPoint, targetFrame: CGRect?) -> CGSize {
    guard let targetFrame, targetFrame.contains(pointer) else { return fullDragIconSize }
    let depth = min(
      pointer.x - targetFrame.minX,
      targetFrame.maxX - pointer.x,
      pointer.y - targetFrame.minY,
      targetFrame.maxY - pointer.y)
    let progress = min(max(depth / 40, 0), 1)
    let side =
      fullDragIconSize.width
      - (fullDragIconSize.width - compactDragIconSize.width) * progress
    return CGSize(width: side, height: side)
  }
}

private struct AppBundleDragSource: NSViewRepresentable {
  let icon: NSImage
  let appURL: URL
  let targetState: ScreenRecordingDragTargetState

  func makeNSView(context: Context) -> AppBundleDragSourceNSView {
    let view = AppBundleDragSourceNSView()
    view.image = icon
    view.appURL = appURL
    view.targetState = targetState
    view.unregisterDraggedTypes()
    return view
  }

  func updateNSView(_ view: AppBundleDragSourceNSView, context: Context) {
    view.image = icon
    view.appURL = appURL
    view.targetState = targetState
  }
}

private struct ScreenRecordingDragCardView: View {
  let appIcon: NSImage
  let appName: String
  let appURL: URL
  @ObservedObject var targetState: ScreenRecordingDragTargetState
  let size: CGSize

  /// Idle hint: the icon + chevron drift toward the list and settle, on a slow
  /// loop, so the card reads as "drag me into the list". Respects reduce-motion.
  @State private var hintUp = false
  private var reduceMotion: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }
  /// Direction the drop target sits relative to the card (down when the card is
  /// flipped above the Settings window). The idle drift follows the same axis.
  private var pointsDown: Bool { targetState.arrowPointsDown }
  private var hintOffset: CGFloat { (pointsDown ? 1 : -1) * (hintUp ? 3 : -1) }
  private var iconHintOffset: CGFloat { (pointsDown ? 1 : -1) * (hintUp ? 6 : 0) }

  var body: some View {
    ZStack {
      RadialGradient(
        colors: [OmiColors.success.opacity(0.22), Color.clear],
        center: .center,
        startRadius: 8,
        endRadius: 88
      )

      VStack(spacing: 7) {
        Image(systemName: pointsDown ? "chevron.down" : "chevron.up")
          .scaledFont(size: 14, weight: .bold)
          .foregroundColor(OmiColors.textSecondary.opacity(hintUp ? 1 : 0.6))
          .offset(y: hintOffset)

        AppBundleDragSource(icon: appIcon, appURL: appURL, targetState: targetState)
          .frame(width: 64, height: 64)
          .shadow(color: Color.black.opacity(0.58), radius: 12, y: 5)
          .offset(y: iconHintOffset)
          .help("Drag \(appName) into the Screen Recording list")
          .accessibilityLabel("Drag \(appName) to enable Screen Recording")

        Text("Drag \(appName)\ninto the list")
          .scaledFont(size: 13.5, weight: .bold)
          .foregroundColor(OmiColors.textPrimary)
          .multilineTextAlignment(.center)
          .lineSpacing(-1)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: size.width - 20)
          .shadow(color: Color.black.opacity(0.65), radius: 3, y: 1)
      }
    }
    .frame(width: size.width, height: size.height)
    .background(Color.clear)
    .onAppear {
      guard !reduceMotion else { return }
      withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
        hintUp = true
      }
    }
  }
}

private struct CloudConnectorFieldCopyCardView: View {
  let title: String
  let subtitle: String
  let sections: [CloudConnectorCopySection]
  let size: CGSize
  let onDismiss: () -> Void

  @State private var copiedFieldID: String?

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      CloudConnectorCardHeaderView(title: title, subtitle: subtitle, onDismiss: onDismiss)

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(sections) { section in
          sectionView(section)
        }
      }
    }
    .padding(.leading, OmiSpacing.lg)
    .padding(.trailing, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.lg)
    .frame(width: size.width, height: size.height, alignment: .topLeading)
    .background(SpatialOverlayCardBackground())
  }

  private func sectionView(_ section: CloudConnectorCopySection) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      if section.hasVisibleTitle {
        Text(section.title)
          .scaledFont(size: 10.5, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(section.fields) { field in
          fieldRow(field)
        }
      }
    }
  }

  private func fieldRow(_ field: CloudConnectorCopyField) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Text(field.label)
        .scaledFont(size: 11.5, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .lineLimit(1)
        .minimumScaleFactor(0.82)
        .frame(width: 152, alignment: .leading)

      Text(field.displayValue)
        .font(.system(size: 11, design: .monospaced))
        .italic(field.value.isEmpty)
        .foregroundColor(field.value.isEmpty ? OmiColors.textTertiary : OmiColors.textSecondary)
        .lineLimit(1)
        .truncationMode(.middle)
        .frame(maxWidth: .infinity, alignment: .leading)

      if field.value.isEmpty {
        Text("—")
          .scaledFont(size: 10.5, weight: .semibold)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
      } else {
        copyButton(field)
      }
    }
    .frame(height: 24)
  }

  private func copyButton(_ field: CloudConnectorCopyField) -> some View {
    Button {
      copy(field)
    } label: {
      ZStack {
        Image(systemName: copiedFieldID == field.id ? "checkmark" : "doc.on.doc")
          .scaledFont(size: OmiType.micro, weight: .bold)
      }
      .frame(width: 28, height: 22)
      .foregroundColor(copiedFieldID == field.id ? OmiColors.success : OmiColors.textPrimary)
      .background(
        Capsule().fill(
          copiedFieldID == field.id
            ? OmiColors.success.opacity(0.16) : Color.white.opacity(0.12))
      )
      .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help(copiedFieldID == field.id ? "Copied \(field.label)" : "Copy \(field.label)")
    .accessibilityLabel(copiedFieldID == field.id ? "Copied \(field.label)" : "Copy \(field.label)")
  }

  private func copy(_ field: CloudConnectorCopyField) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(field.value, forType: .string)
    copiedFieldID = field.id
    let copiedID = field.id
    Task {
      try? await Task.sleep(nanoseconds: 1_800_000_000)
      if copiedFieldID == copiedID {
        copiedFieldID = nil
      }
    }
  }
}

/// Frosted, lightly accented surface shared by the guidance bubble and the
/// instruction card so both read as one polished family.
private struct SpatialOverlayCardBackground: View {
  var cornerRadius: CGFloat = 20

  var body: some View {
    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
      .fill(.ultraThinMaterial)
      .overlay(
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
          .fill(Color.black.opacity(0.42))
      )
      .overlay(
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
          .strokeBorder(
            LinearGradient(
              colors: [Color.white.opacity(0.24), Color.white.opacity(0.06)],
              startPoint: .top, endPoint: .bottom),
            lineWidth: 1)
      )
      .shadow(color: .black.opacity(0.42), radius: 26, y: 14)
  }
}

/// Green gradient badge used as the leading glyph in spatial overlays.
private struct SpatialOverlayAccentIcon: View {
  let systemName: String
  var diameter: CGFloat = 36

  var body: some View {
    ZStack {
      Circle()
        .fill(
          LinearGradient(
            colors: [OmiColors.success, OmiColors.success.opacity(0.72)],
            startPoint: .topLeading, endPoint: .bottomTrailing))
      Image(systemName: systemName)
        .scaledFont(size: diameter * 0.42, weight: .bold)
        .foregroundColor(.white)
    }
    .frame(width: diameter, height: diameter)
    .overlay(Circle().strokeBorder(Color.white.opacity(0.18), lineWidth: 0.75))
    .shadow(color: OmiColors.success.opacity(0.45), radius: 9, y: 2)
  }
}

private struct CloudConnectorGuidanceView: View {
  let actionLabel: String
  let placement: SpatialOverlayPlacementResult

  private var arrowIcon: String {
    switch placement.attachmentEdge {
    case .above: return "arrow.down"
    case .below: return "arrow.up"
    case .leading: return "arrow.right"
    case .trailing: return "arrow.left"
    }
  }

  var body: some View {
    GeometryReader { proxy in
      let geometry = SpatialOverlayRenderGeometry(placement: placement, panelSize: proxy.size)
      let bubbleRect = geometry.bubbleFrame
      let pointerRect = geometry.pointerFrame
      ZStack(alignment: .topLeading) {
        bubble
          .frame(width: bubbleRect.width, height: bubbleRect.height)
          .position(x: bubbleRect.midX, y: bubbleRect.midY)

        TrianglePointer(edge: placement.attachmentEdge)
          .fill(OmiColors.success)
          .frame(width: pointerRect.width, height: pointerRect.height)
          .position(x: pointerRect.midX, y: pointerRect.midY)
      }
    }
  }

  private var bubble: some View {
    HStack(spacing: OmiSpacing.md) {
      SpatialOverlayAccentIcon(systemName: arrowIcon, diameter: 34)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text("Finish in Claude")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Click the \(actionLabel) button.")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      }
      Spacer(minLength: 0)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
    .background(SpatialOverlayCardBackground(cornerRadius: OmiChrome.controlRadius))
  }
}

private struct TrianglePointer: Shape {
  let edge: SpatialOverlayAttachmentEdge

  func path(in rect: CGRect) -> Path {
    var path = Path()
    switch edge {
    case .above:
      path.move(to: CGPoint(x: rect.midX, y: rect.maxY))
      path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
      path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
    case .below:
      path.move(to: CGPoint(x: rect.midX, y: rect.minY))
      path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
      path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
    case .leading:
      path.move(to: CGPoint(x: rect.maxX, y: rect.midY))
      path.addLine(to: CGPoint(x: rect.minX, y: rect.minY))
      path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
    case .trailing:
      path.move(to: CGPoint(x: rect.minX, y: rect.midY))
      path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
      path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    }
    path.closeSubpath()
    return path
  }
}
