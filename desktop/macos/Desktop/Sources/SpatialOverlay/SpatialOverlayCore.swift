import AppKit
import Foundation

enum SpatialOverlayAnchorUse: Hashable {
  case displayGuidance
  case performClick
  case glow
  case positionUtilityUI
}

enum SpatialOverlayTargetSource: String {
  case accessibility
  case ocr
  case cgWindowList
  case semanticState
  case layoutHeuristic
  case fixedScreenAnchor
  case appWindow
}

enum SpatialOverlayExclusionKind: String {
  case menuBar
  case dock
  case notch
  case omiFloatingBar
  case omiAgentPills
  case target
  case browserToolbar
  case targetWindowChrome
  case otherOverlay
}

enum SpatialOverlayAttachmentEdge: CaseIterable, Equatable {
  case above
  case below
  case leading
  case trailing
}

struct SpatialOverlayScreen: Equatable {
  var id: String
  var frame: CGRect
  var visibleFrame: CGRect
  var scale: CGFloat
  var exclusionZones: [SpatialOverlayExclusionZone]

  init(
    id: String,
    frame: CGRect,
    visibleFrame: CGRect? = nil,
    scale: CGFloat = 1,
    exclusionZones: [SpatialOverlayExclusionZone] = []
  ) {
    self.id = id
    self.frame = frame
    self.visibleFrame = visibleFrame ?? frame
    self.scale = scale
    self.exclusionZones = exclusionZones
  }
}

struct SpatialOverlayExclusionZone: Equatable {
  var rect: CGRect
  var kind: SpatialOverlayExclusionKind
  var isHard: Bool

  init(rect: CGRect, kind: SpatialOverlayExclusionKind, isHard: Bool = true) {
    self.rect = rect
    self.kind = kind
    self.isHard = isHard
  }
}

struct SpatialOverlayWindow: Equatable {
  var id: String
  var frame: CGRect
  var screenID: String?
  var bundleID: String?
  var isFrontmostApp: Bool
  var isFocusedWindow: Bool

  init(
    id: String,
    frame: CGRect,
    screenID: String? = nil,
    bundleID: String? = nil,
    isFrontmostApp: Bool = false,
    isFocusedWindow: Bool = false
  ) {
    self.id = id
    self.frame = frame
    self.screenID = screenID
    self.bundleID = bundleID
    self.isFrontmostApp = isFrontmostApp
    self.isFocusedWindow = isFocusedWindow
  }
}

struct SpatialOverlayTargetEvidence: Equatable {
  var source: SpatialOverlayTargetSource
  var confidence: Double
  var label: String?
  var diagnostics: [String]

  init(
    source: SpatialOverlayTargetSource,
    confidence: Double,
    label: String? = nil,
    diagnostics: [String] = []
  ) {
    self.source = source
    self.confidence = confidence
    self.label = label
    self.diagnostics = diagnostics
  }
}

struct SpatialOverlayAnchorCandidate: Equatable {
  var id: String
  var targetRect: CGRect
  var targetPoint: CGPoint
  var screen: SpatialOverlayScreen
  var window: SpatialOverlayWindow?
  var evidence: [SpatialOverlayTargetEvidence]
  var confidence: Double
  var allowedUses: Set<SpatialOverlayAnchorUse>

  init(
    id: String,
    targetRect: CGRect,
    targetPoint: CGPoint? = nil,
    screen: SpatialOverlayScreen,
    window: SpatialOverlayWindow? = nil,
    evidence: [SpatialOverlayTargetEvidence] = [],
    confidence: Double,
    allowedUses: Set<SpatialOverlayAnchorUse>
  ) {
    self.id = id
    self.targetRect = targetRect
    self.targetPoint = targetPoint ?? CGPoint(x: targetRect.midX, y: targetRect.midY)
    self.screen = screen
    self.window = window
    self.evidence = evidence
    self.confidence = confidence
    self.allowedUses = allowedUses
  }
}

struct SpatialOverlayPlacementSpec: Equatable {
  var overlaySize: CGSize
  var preferredEdges: [SpatialOverlayAttachmentEdge]
  var margin: CGFloat
  var gap: CGFloat
  var arrowSize: CGSize
  var minimumArrowInset: CGFloat
  var avoidTargetPadding: CGFloat
  var canCoverTarget: Bool

  init(
    overlaySize: CGSize,
    preferredEdges: [SpatialOverlayAttachmentEdge] = [.above, .below, .trailing, .leading],
    margin: CGFloat = 12,
    gap: CGFloat = 0,
    arrowSize: CGSize = CGSize(width: 18, height: 13),
    minimumArrowInset: CGFloat = 28,
    avoidTargetPadding: CGFloat = 0,
    canCoverTarget: Bool = false
  ) {
    self.overlaySize = overlaySize
    self.preferredEdges =
      preferredEdges.isEmpty ? [.above, .below, .trailing, .leading] : preferredEdges
    self.margin = margin
    self.gap = gap
    self.arrowSize = arrowSize
    self.minimumArrowInset = minimumArrowInset
    self.avoidTargetPadding = avoidTargetPadding
    self.canCoverTarget = canCoverTarget
  }
}

struct SpatialOverlayPlacementResult: Equatable {
  var panelFrame: CGRect
  var targetPoint: CGPoint
  var arrowTipInPanel: CGPoint
  var arrowSize: CGSize = CGSize(width: 18, height: 13)
  var attachmentEdge: SpatialOverlayAttachmentEdge
  var score: Double
  var clampDelta: CGVector
  var diagnostics: [String]

  var globalArrowTip: CGPoint {
    CGPoint(x: panelFrame.minX + arrowTipInPanel.x, y: panelFrame.minY + arrowTipInPanel.y)
  }
}

enum SpatialOverlayPlacementFailure: Error, Equatable, CustomStringConvertible {
  case noScreenForTarget
  case overlayTooLargeForSafeArea
  case arrowCannotReachTargetAfterClamping
  case blockedByRequiredExclusionZones
  case noViablePlacement

  var description: String {
    switch self {
    case .noScreenForTarget:
      return "No screen contains the target"
    case .overlayTooLargeForSafeArea:
      return "Overlay is too large for the safe area"
    case .arrowCannotReachTargetAfterClamping:
      return "Arrow cannot reach the target after clamping"
    case .blockedByRequiredExclusionZones:
      return "Overlay is blocked by required exclusion zones"
    case .noViablePlacement:
      return "No viable overlay placement"
    }
  }
}

enum SpatialOverlayPlacementSolver {
  static func place(
    target: SpatialOverlayAnchorCandidate,
    spec: SpatialOverlayPlacementSpec
  ) -> Result<SpatialOverlayPlacementResult, SpatialOverlayPlacementFailure> {
    let safeFrame = target.screen.visibleFrame.insetBy(dx: spec.margin, dy: spec.margin)
    guard safeFrame.width >= spec.overlaySize.width, safeFrame.height >= spec.overlaySize.height
    else {
      return .failure(.overlayTooLargeForSafeArea)
    }

    var best: SpatialOverlayPlacementResult?
    var sawDetachedArrow = false
    var sawBlocked = false

    for edge in spec.preferredEdges {
      let anchorPoint = anchorPoint(for: target, edge: edge, canCoverTarget: spec.canCoverTarget)
      let proposedFrame = frame(for: anchorPoint, edge: edge, spec: spec)
      let clampedFrame = clamp(proposedFrame, inside: safeFrame)
      let arrowTip = arrowTip(
        in: clampedFrame, targetPoint: anchorPoint, edge: edge, spec: spec)
      let globalTip = CGPoint(x: clampedFrame.minX + arrowTip.x, y: clampedFrame.minY + arrowTip.y)
      let arrowDistance = hypot(
        globalTip.x - anchorPoint.x, globalTip.y - anchorPoint.y)
      guard arrowDistance <= 3 else {
        sawDetachedArrow = true
        continue
      }

      if !spec.canCoverTarget {
        let paddedTarget = target.targetRect.insetBy(
          dx: -spec.avoidTargetPadding, dy: -spec.avoidTargetPadding)
        if clampedFrame.intersects(paddedTarget) {
          sawBlocked = true
          continue
        }
      }

      if target.screen.exclusionZones.contains(where: { zone in
        zone.isHard && zone.kind != .target && clampedFrame.intersects(zone.rect)
      }) {
        sawBlocked = true
        continue
      }

      let clampDelta = CGVector(
        dx: clampedFrame.minX - proposedFrame.minX, dy: clampedFrame.minY - proposedFrame.minY)
      let preferenceScore = Double(spec.preferredEdges.firstIndex(of: edge) ?? 0)
      let score =
        1_000 - preferenceScore * 25 - Double(abs(clampDelta.dx) + abs(clampDelta.dy))
        - arrowDistance * 10
      let result = SpatialOverlayPlacementResult(
        panelFrame: clampedFrame,
        targetPoint: anchorPoint,
        arrowTipInPanel: arrowTip,
        arrowSize: spec.arrowSize,
        attachmentEdge: edge,
        score: score,
        clampDelta: clampDelta,
        diagnostics: [
          "edge=\(edge)",
          "arrowDistance=\(String(format: "%.2f", arrowDistance))",
          "clampDelta=(\(String(format: "%.1f", clampDelta.dx)),\(String(format: "%.1f", clampDelta.dy)))",
        ]
      )
      if best == nil || result.score > best!.score {
        best = result
      }
    }

    if let best {
      return .success(best)
    }
    if sawDetachedArrow {
      return .failure(.arrowCannotReachTargetAfterClamping)
    }
    if sawBlocked {
      return .failure(.blockedByRequiredExclusionZones)
    }
    return .failure(.noViablePlacement)
  }

  private static func anchorPoint(
    for target: SpatialOverlayAnchorCandidate,
    edge: SpatialOverlayAttachmentEdge,
    canCoverTarget: Bool
  ) -> CGPoint {
    guard !canCoverTarget else { return target.targetPoint }

    switch edge {
    case .above:
      return CGPoint(x: target.targetPoint.x, y: target.targetRect.maxY)
    case .below:
      return CGPoint(x: target.targetPoint.x, y: target.targetRect.minY)
    case .leading:
      return CGPoint(x: target.targetRect.minX, y: target.targetPoint.y)
    case .trailing:
      return CGPoint(x: target.targetRect.maxX, y: target.targetPoint.y)
    }
  }

  private static func frame(
    for targetPoint: CGPoint,
    edge: SpatialOverlayAttachmentEdge,
    spec: SpatialOverlayPlacementSpec
  ) -> CGRect {
    let size = spec.overlaySize
    switch edge {
    case .above:
      return CGRect(
        x: targetPoint.x - size.width / 2, y: targetPoint.y + spec.gap, width: size.width,
        height: size.height)
    case .below:
      return CGRect(
        x: targetPoint.x - size.width / 2,
        y: targetPoint.y - size.height - spec.gap,
        width: size.width,
        height: size.height
      )
    case .leading:
      return CGRect(
        x: targetPoint.x - size.width - spec.gap,
        y: targetPoint.y - size.height / 2,
        width: size.width,
        height: size.height
      )
    case .trailing:
      return CGRect(
        x: targetPoint.x + spec.gap, y: targetPoint.y - size.height / 2, width: size.width,
        height: size.height)
    }
  }

  private static func arrowTip(
    in frame: CGRect,
    targetPoint: CGPoint,
    edge: SpatialOverlayAttachmentEdge,
    spec: SpatialOverlayPlacementSpec
  ) -> CGPoint {
    let horizontalInset = min(
      max(spec.minimumArrowInset, spec.arrowSize.width / 2), frame.width / 2)
    let verticalInset = min(
      max(spec.minimumArrowInset, spec.arrowSize.height / 2), frame.height / 2)
    switch edge {
    case .above:
      return CGPoint(
        x: clamp(
          targetPoint.x - frame.minX, min: horizontalInset,
          max: frame.width - horizontalInset),
        y: 0
      )
    case .below:
      return CGPoint(
        x: clamp(
          targetPoint.x - frame.minX, min: horizontalInset,
          max: frame.width - horizontalInset),
        y: frame.height
      )
    case .leading:
      return CGPoint(
        x: frame.width,
        y: clamp(
          targetPoint.y - frame.minY, min: verticalInset,
          max: frame.height - verticalInset)
      )
    case .trailing:
      return CGPoint(
        x: 0,
        y: clamp(
          targetPoint.y - frame.minY, min: verticalInset,
          max: frame.height - verticalInset)
      )
    }
  }

  private static func clamp(_ frame: CGRect, inside bounds: CGRect) -> CGRect {
    CGRect(
      x: clamp(frame.minX, min: bounds.minX, max: bounds.maxX - frame.width),
      y: clamp(frame.minY, min: bounds.minY, max: bounds.maxY - frame.height),
      width: frame.width,
      height: frame.height
    )
  }

  private static func clamp(_ value: CGFloat, min minValue: CGFloat, max maxValue: CGFloat)
    -> CGFloat
  {
    guard minValue <= maxValue else { return minValue }
    return Swift.min(Swift.max(value, minValue), maxValue)
  }
}
