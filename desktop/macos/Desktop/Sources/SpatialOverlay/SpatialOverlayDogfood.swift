import AppKit
import Foundation

enum SpatialOverlayDogfoodFixture: String, CaseIterable {
  case claudeAddExplicit = "claude-add-explicit"
  case claudeAddInferredFromCancel = "claude-add-inferred-from-cancel"
  case claudeAddHeuristic = "claude-add-heuristic"
  case claudeConnectExplicit = "claude-connect-explicit"
  case claudeConnectHeuristic = "claude-connect-heuristic"

  var actionLabel: String {
    switch self {
    case .claudeAddExplicit, .claudeAddInferredFromCancel, .claudeAddHeuristic:
      return "Add"
    case .claudeConnectExplicit, .claudeConnectHeuristic:
      return "Connect"
    }
  }

  var windowFrame: CGRect {
    switch self {
    case .claudeAddExplicit, .claudeAddInferredFromCancel, .claudeAddHeuristic:
      return CGRect(x: 0, y: 0, width: 1510, height: 1596)
    case .claudeConnectExplicit, .claudeConnectHeuristic:
      return CGRect(x: 0, y: 0, width: 1920, height: 1080)
    }
  }

  var targetRect: CGRect {
    switch self {
    case .claudeAddExplicit:
      return appKitRect(topLeftRect: CGRect(x: 1_124, y: 1_296, width: 92, height: 54))
    case .claudeAddInferredFromCancel:
      return appKitRect(
        topLeftRect: CloudConnectorFormAutomation.inferredClaudeAddButtonFrameFromCancel(
          CGRect(x: 1_006, y: 1_296, width: 106, height: 54)
        )
      )
    case .claudeAddHeuristic:
      let point = CloudConnectorFormAutomation.claudeAddGuidanceAnchor(in: windowFrame)
      return CGRect(x: point.x - 46, y: point.y - 27, width: 92, height: 54)
    case .claudeConnectExplicit:
      return appKitRect(topLeftRect: CGRect(x: 1_225, y: 641, width: 132, height: 54))
    case .claudeConnectHeuristic:
      let point = CloudConnectorFormAutomation.claudeConnectGuidanceAnchor(in: windowFrame)
      return CGRect(x: point.x - 66, y: point.y - 27, width: 132, height: 54)
    }
  }

  var topLeftTargetRect: CGRect {
    switch self {
    case .claudeAddExplicit:
      return CGRect(x: 1_124, y: 1_296, width: 92, height: 54)
    case .claudeAddInferredFromCancel:
      return topLeftRect(appKitRect: targetRect)
    case .claudeAddHeuristic:
      return topLeftRect(appKitRect: targetRect)
    case .claudeConnectExplicit:
      return CGRect(x: 1_225, y: 641, width: 132, height: 54)
    case .claudeConnectHeuristic:
      return topLeftRect(appKitRect: targetRect)
    }
  }

  var candidates: [SpatialOverlayAnchorCandidate] {
    switch self {
    case .claudeAddExplicit:
      return CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
        windowFrame: windowFrame,
        explicitTargetFrames: [targetRect]
      )
    case .claudeAddInferredFromCancel:
      return [inferredAddCandidate]
    case .claudeAddHeuristic:
      return CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
        windowFrame: windowFrame,
        explicitTargetFrames: []
      )
    case .claudeConnectExplicit:
      return CloudConnectorFormAutomation.claudeConnectGuidanceCandidates(
        windowFrame: windowFrame,
        explicitTargetFrames: [targetRect]
      )
    case .claudeConnectHeuristic:
      return CloudConnectorFormAutomation.claudeConnectGuidanceCandidates(
        windowFrame: windowFrame,
        explicitTargetFrames: []
      )
    }
  }

  func topLeftRect(appKitRect: CGRect) -> CGRect {
    CGRect(
      x: appKitRect.minX,
      y: windowFrame.maxY - appKitRect.maxY,
      width: appKitRect.width,
      height: appKitRect.height
    )
  }

  private func appKitRect(topLeftRect: CGRect) -> CGRect {
    SpatialOverlayGeometry.appKitFrame(topLeftFrame: topLeftRect, screenFrame: windowFrame)
  }

  private var inferredAddCandidate: SpatialOverlayAnchorCandidate {
    let screen = SpatialOverlayScreen(id: "claude-window", frame: windowFrame, visibleFrame: windowFrame)
    let window = SpatialOverlayWindow(
      id: "claude-window",
      frame: windowFrame,
      screenID: screen.id
    )
    return SpatialOverlayAnchorCandidate(
      id: "claude-add-inferred-from-cancel",
      targetRect: targetRect,
      screen: screen,
      window: window,
      evidence: [
        SpatialOverlayTargetEvidence(
          source: .layoutHeuristic,
          confidence: 0.82,
          label: "Claude Add inferred from Cancel button",
          diagnostics: ["display-guidance-only", "inferred-from-cancel-button"]
        )
      ],
      confidence: 0.82,
      allowedUses: [.displayGuidance]
    )
  }
}

enum SpatialOverlayDogfoodIssue: Equatable, CustomStringConvertible {
  case arrowMissesTarget(distance: CGFloat)
  case panelCoversTarget

  var description: String {
    switch self {
    case .arrowMissesTarget(let distance):
      return "arrow misses target by \(String(format: "%.1f", distance))px"
    case .panelCoversTarget:
      return "panel covers target"
    }
  }
}

enum SpatialOverlayDogfoodOracle {
  static func issues(
    placement: SpatialOverlayPlacementResult,
    targetRect: CGRect,
    coveredTargetRect: CGRect? = nil,
    maximumArrowDistance: CGFloat = 3,
    avoidTargetPadding: CGFloat = 0
  ) -> [SpatialOverlayDogfoodIssue] {
    issues(
      arrowTip: placement.globalArrowTip,
      panelFrame: placement.panelFrame,
      targetRect: targetRect,
      coveredTargetRect: coveredTargetRect,
      maximumArrowDistance: maximumArrowDistance,
      avoidTargetPadding: avoidTargetPadding
    )
  }

  /// Validate against an explicit arrow apex and panel rect. Prefer this overload with
  /// the *rendered* apex (`SpatialOverlayRenderGeometry.globalRenderedArrowTip`) so the
  /// check reflects the pixel the user sees, not just the solver's intent.
  static func issues(
    arrowTip: CGPoint,
    panelFrame: CGRect,
    targetRect: CGRect,
    coveredTargetRect: CGRect? = nil,
    maximumArrowDistance: CGFloat = 3,
    avoidTargetPadding: CGFloat = 0
  ) -> [SpatialOverlayDogfoodIssue] {
    var issues: [SpatialOverlayDogfoodIssue] = []
    let distance = distanceFromRect(arrowTip, to: targetRect)
    if distance > maximumArrowDistance {
      issues.append(.arrowMissesTarget(distance: distance))
    }

    let coverRect = coveredTargetRect ?? targetRect
    if panelFrame.intersects(coverRect.insetBy(dx: -avoidTargetPadding, dy: -avoidTargetPadding)) {
      issues.append(.panelCoversTarget)
    }

    return issues
  }

  private static func distanceFromRect(_ point: CGPoint, to rect: CGRect) -> CGFloat {
    let dx = max(rect.minX - point.x, 0, point.x - rect.maxX)
    let dy = max(rect.minY - point.y, 0, point.y - rect.maxY)
    return hypot(dx, dy)
  }
}
