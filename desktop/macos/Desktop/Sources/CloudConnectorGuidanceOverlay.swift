import AppKit
import SwiftUI

@MainActor
final class CloudConnectorGuidanceOverlay {
  static let shared = CloudConnectorGuidanceOverlay()

  private var window: NSWindow?
  private var dismissTask: Task<Void, Never>?

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
    else { return }

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

  func dismiss() {
    dismissTask?.cancel()
    dismissTask = nil
    window?.close()
    window = nil
  }

  static func placementResult(
    windowFrame: CGRect,
    candidates: [SpatialOverlayAnchorCandidate],
    overlaySize: CGSize = CGSize(width: 330, height: 118)
  ) -> SpatialOverlayPlacementResult? {
    let screen = SpatialOverlayGeometry.screenForTarget(windowFrame: windowFrame)
    for candidate in candidates.filter({ $0.allowedUses.contains(.displayGuidance) }).map({ candidate in
      guard let screen else { return candidate }
      return SpatialOverlayAnchorCandidate(
        id: candidate.id,
        targetRect: candidate.targetRect,
        targetPoint: candidate.targetPoint,
        screen: screen,
        window: candidate.window,
        evidence: candidate.evidence,
        confidence: candidate.confidence,
        allowedUses: candidate.allowedUses
      )
    }).sorted(by: candidateSort) {
      let spec = SpatialOverlayPlacementSpec(
        overlaySize: overlaySize,
        preferredEdges: [.above, .below, .trailing, .leading],
        gap: 0,
        canCoverTarget: true
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
}

private struct CloudConnectorGuidanceView: View {
  let actionLabel: String
  let placement: SpatialOverlayPlacementResult

  private let arrowSize = CGSize(width: 18, height: 13)

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
      ZStack(alignment: .topLeading) {
        bubble
          .frame(width: bubbleFrame(in: proxy.size).width, height: bubbleFrame(in: proxy.size).height)
          .position(x: bubbleFrame(in: proxy.size).midX, y: bubbleFrame(in: proxy.size).midY)

        TrianglePointer(edge: placement.attachmentEdge)
          .fill(OmiColors.success)
          .frame(width: pointerFrame(in: proxy.size).width, height: pointerFrame(in: proxy.size).height)
          .position(x: pointerFrame(in: proxy.size).midX, y: pointerFrame(in: proxy.size).midY)
      }
    }
  }

  private var bubble: some View {
    HStack(spacing: 10) {
      ZStack {
        Circle()
          .fill(OmiColors.success.opacity(0.18))
        Image(systemName: arrowIcon)
          .scaledFont(size: 15, weight: .bold)
          .foregroundColor(OmiColors.success)
      }
      .frame(width: 34, height: 34)

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
    .padding(.horizontal, 14)
    .padding(.vertical, 12)
    .background(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .fill(Color.black.opacity(0.88))
    )
    .overlay(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .stroke(OmiColors.success.opacity(0.55), lineWidth: 1)
    )
    .shadow(color: .black.opacity(0.32), radius: 18, y: 8)
  }

  private func bubbleFrame(in size: CGSize) -> CGRect {
    switch placement.attachmentEdge {
    case .above:
      return CGRect(x: 8, y: 8, width: size.width - 16, height: size.height - arrowSize.height - 8)
    case .below:
      return CGRect(x: 8, y: arrowSize.height, width: size.width - 16, height: size.height - arrowSize.height - 8)
    case .leading:
      return CGRect(x: 8, y: 8, width: size.width - arrowSize.height - 8, height: size.height - 16)
    case .trailing:
      return CGRect(x: arrowSize.height, y: 8, width: size.width - arrowSize.height - 8, height: size.height - 16)
    }
  }

  private func pointerFrame(in size: CGSize) -> CGRect {
    let tip = swiftUITipPoint(in: size)
    switch placement.attachmentEdge {
    case .above:
      return CGRect(
        x: tip.x - arrowSize.width / 2,
        y: tip.y - arrowSize.height,
        width: arrowSize.width,
        height: arrowSize.height
      )
    case .below:
      return CGRect(
        x: tip.x - arrowSize.width / 2,
        y: tip.y,
        width: arrowSize.width,
        height: arrowSize.height
      )
    case .leading:
      return CGRect(
        x: tip.x - arrowSize.height,
        y: tip.y - arrowSize.width / 2,
        width: arrowSize.height,
        height: arrowSize.width
      )
    case .trailing:
      return CGRect(
        x: tip.x,
        y: tip.y - arrowSize.width / 2,
        width: arrowSize.height,
        height: arrowSize.width
      )
    }
  }

  private func swiftUITipPoint(in size: CGSize) -> CGPoint {
    CGPoint(
      x: placement.arrowTipInPanel.x,
      y: size.height - placement.arrowTipInPanel.y
    )
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
