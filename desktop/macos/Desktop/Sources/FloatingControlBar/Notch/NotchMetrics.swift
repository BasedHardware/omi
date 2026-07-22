import AppKit
import SwiftUI

/// The notch's animation springs — single source of truth so every call site
/// stays in step. The morph (open/close/tab) rides these; continuous height
/// growth rides its own `.smooth` timeline in NotchView and must never merge
/// with them.
enum NotchAnimation {
  static let open = Animation.spring(response: 0.40, dampingFraction: 0.78)
  static let close = Animation.spring(response: 0.34, dampingFraction: 0.9)
  static let tab = Animation.spring(response: 0.36, dampingFraction: 0.82)
}

/// Single source of truth for the notch's fixed geometry.
enum NotchMetrics {
  /// Notch size on displays without a physical notch.
  static let fallbackClosedSize = CGSize(width: 240, height: 34)
  /// Fallback camera dead zone when the auxiliary areas can't be measured.
  static let fallbackHiddenCenterWidth: CGFloat = 172
  /// Padding added around the measured camera gap so chrome never touches it.
  static let hiddenCenterSafetyPadding: CGFloat = 34
  /// Width of each chrome lobe flanking the camera: omi logo (left), settings
  /// gear (right) — always visible in the closed state.
  static let closedSideWidth: CGFloat = 30
  /// Central void reserved for the camera in the open panel's header row.
  static let headerCameraReserve: CGFloat = 28
  /// Size deltas for the compact voice states (waveform / thinking mark).
  static let listeningExtraWidth: CGFloat = 100
  static let listeningExtraHeight: CGFloat = 26
  static let thinkingExtraWidth: CGFloat = 24
  /// Readable status strip under the chrome for too-short PTT / mic errors.
  static let hintRowHeight: CGFloat = 30
  /// Proactive notification card shown below the closed chrome.
  static let notificationSize = CGSize(width: 430, height: 108)
  static let notificationSpacing: CGFloat = 8
  /// Slack around the content so the fixed window can hold glow bleed + shadow.
  static let shadowPadding: CGFloat = 22
  /// The floating composer tray lives BELOW the black body: gap between the
  /// body's bottom edge and the tray, the tray's reserve height (composer grown
  /// to its multi-line maximum), and breathing room. The window reserves all of
  /// it so a max-height answer plus the tray still fits in the fixed panel.
  static let trayGap: CGFloat = 10
  static let trayHeight: CGFloat = 84
  static let trayReserve: CGFloat = trayGap + trayHeight + 16
  /// Corner radii: (top, bottom) for the closed notch and the open panel.
  static let cornerClosed: (top: CGFloat, bottom: CGFloat) = (6, 14)
  static let cornerOpen: (top: CGFloat, bottom: CGFloat) = (20, 26)

  // MARK: - Closed-size math (pure, injectable for tests)

  /// Whether a display should render the hardware-notch presentation.
  /// Testing hooks OMI_FORCE_NOTCH / OMI_FORCE_NO_NOTCH mirror the legacy
  /// behavior; NO_NOTCH wins when both are set.
  static func screenHasCameraHousing(_ screen: NSScreen?) -> Bool {
    if let forced = getenv("OMI_FORCE_NO_NOTCH"), String(cString: forced) == "1" { return false }
    if let forced = getenv("OMI_FORCE_NOTCH"), String(cString: forced) == "1" { return true }
    guard let screen else { return false }
    if let leftArea = screen.auxiliaryTopLeftArea,
      let rightArea = screen.auxiliaryTopRightArea,
      !leftArea.isEmpty,
      !rightArea.isEmpty
    {
      return true
    }
    return screen.safeAreaInsets.top > 0
  }

  /// The physical camera housing width alone (no safety padding) — what the
  /// chrome icons visually hug.
  static func cameraWidth(auxiliaryTopLeftArea: NSRect?, auxiliaryTopRightArea: NSRect?) -> CGFloat {
    if let leftArea = auxiliaryTopLeftArea,
      let rightArea = auxiliaryTopRightArea,
      !leftArea.isEmpty,
      !rightArea.isEmpty
    {
      let measuredGap = rightArea.minX - leftArea.maxX
      if measuredGap > 0 { return measuredGap }
    }
    return fallbackHiddenCenterWidth
  }

  /// The camera dead zone the chrome must straddle: the measured gap between
  /// the two auxiliary top areas plus safety padding.
  static func hiddenCenterWidth(auxiliaryTopLeftArea: NSRect?, auxiliaryTopRightArea: NSRect?) -> CGFloat {
    if let leftArea = auxiliaryTopLeftArea,
      let rightArea = auxiliaryTopRightArea,
      !leftArea.isEmpty,
      !rightArea.isEmpty
    {
      let measuredGap = rightArea.minX - leftArea.maxX
      if measuredGap > 0 {
        return max(fallbackHiddenCenterWidth + hiddenCenterSafetyPadding, measuredGap + hiddenCenterSafetyPadding)
      }
    }
    return fallbackHiddenCenterWidth + hiddenCenterSafetyPadding
  }

  /// Closed chrome height: the physical notch height when present, else the
  /// menu-bar strip height, floored at the fallback.
  static func closedHeight(topSafeAreaInset: CGFloat, frameMaxY: CGFloat, visibleFrameMaxY: CGFloat) -> CGFloat {
    if topSafeAreaInset > 0 { return topSafeAreaInset }
    return max(fallbackClosedSize.height, frameMaxY - visibleFrameMaxY - 1)
  }

  /// The closed notch: camera dead zone flanked by the two always-visible
  /// chrome lobes (logo / gear).
  static func closedSize(
    hasCameraHousing: Bool,
    auxiliaryTopLeftArea: NSRect?,
    auxiliaryTopRightArea: NSRect?,
    topSafeAreaInset: CGFloat,
    frameMaxY: CGFloat,
    visibleFrameMaxY: CGFloat
  ) -> CGSize {
    let height = closedHeight(
      topSafeAreaInset: topSafeAreaInset, frameMaxY: frameMaxY, visibleFrameMaxY: visibleFrameMaxY)
    guard hasCameraHousing else {
      return CGSize(width: fallbackClosedSize.width, height: height)
    }
    let center = hiddenCenterWidth(
      auxiliaryTopLeftArea: auxiliaryTopLeftArea, auxiliaryTopRightArea: auxiliaryTopRightArea)
    return CGSize(width: center + closedSideWidth * 2, height: height)
  }

  static func closedSize(for screen: NSScreen) -> CGSize {
    closedSize(
      hasCameraHousing: screenHasCameraHousing(screen),
      auxiliaryTopLeftArea: screen.auxiliaryTopLeftArea,
      auxiliaryTopRightArea: screen.auxiliaryTopRightArea,
      topSafeAreaInset: screen.safeAreaInsets.top,
      frameMaxY: screen.frame.maxY,
      visibleFrameMaxY: screen.visibleFrame.maxY
    )
  }
}

extension NSScreen {
  var omiDisplayID: CGDirectDisplayID {
    (deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0
  }
}
