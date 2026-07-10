import AppKit
import SwiftUI
import OmiTheme

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
  private var lastAutomationState: [String: String]?

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
    window?.close()
    window = nil
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
    let targetRect = selected?.targetRect ?? CGRect(
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
    HStack(alignment: .top, spacing: 13) {
      SpatialOverlayAccentIcon(systemName: "checklist", diameter: 38)

      VStack(alignment: .leading, spacing: 4) {
        Text(title)
          .scaledFont(size: 13.5, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
        Text(subtitle)
          .scaledFont(size: 12, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
          .lineSpacing(1.5)
          .fixedSize(horizontal: false, vertical: true)
      }

      Spacer(minLength: 0)

      Button(action: onDismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: 10, weight: .bold)
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
    .padding(.leading, 16)
    .padding(.trailing, 12)
    .padding(.vertical, 15)
    .frame(width: size.width, height: size.height, alignment: .topLeading)
    .background(SpatialOverlayCardBackground())
    .contentShape(Rectangle())
    .onTapGesture(perform: onDismiss)
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
    VStack(alignment: .leading, spacing: 10) {
      CloudConnectorCardHeaderView(title: title, subtitle: subtitle, onDismiss: onDismiss)

      VStack(alignment: .leading, spacing: 10) {
        ForEach(sections) { section in
          sectionView(section)
        }
      }
    }
    .padding(.leading, 16)
    .padding(.trailing, 12)
    .padding(.vertical, 15)
    .frame(width: size.width, height: size.height, alignment: .topLeading)
    .background(SpatialOverlayCardBackground())
  }

  private func sectionView(_ section: CloudConnectorCopySection) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      if section.hasVisibleTitle {
        Text(section.title)
          .scaledFont(size: 10.5, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }

      VStack(alignment: .leading, spacing: 6) {
        ForEach(section.fields) { field in
          fieldRow(field)
        }
      }
    }
  }

  private func fieldRow(_ field: CloudConnectorCopyField) -> some View {
    HStack(spacing: 8) {
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
          .padding(.horizontal, 9)
          .padding(.vertical, 4)
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
          .scaledFont(size: 10, weight: .bold)
      }
      .frame(width: 28, height: 22)
      .foregroundColor(copiedFieldID == field.id ? OmiColors.success : OmiColors.textPrimary)
      .background(
        Capsule().fill(
          copiedFieldID == field.id
            ? OmiColors.success.opacity(0.16) : Color.white.opacity(0.12)))
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
    HStack(spacing: 11) {
      SpatialOverlayAccentIcon(systemName: arrowIcon, diameter: 34)

      VStack(alignment: .leading, spacing: 2) {
        Text("Finish in Claude")
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Click the \(actionLabel) button.")
          .scaledFont(size: 12, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
      }
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 15)
    .padding(.vertical, 12)
    .background(SpatialOverlayCardBackground(cornerRadius: 18))
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
