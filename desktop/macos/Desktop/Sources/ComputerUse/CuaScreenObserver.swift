import AppKit
import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

/// What is on screen: which displays exist, which windows are open, and the
/// pictures of both.
///
/// Capture goes through ScreenCaptureKit because it is the only supported path
/// on this deployment target — `CGDisplayCreateImage` and
/// `CGWindowListCreateImage` are deprecated and return an empty image under a
/// missing grant rather than failing. A capture here is always requested at an
/// explicit pixel size, so the delivered image and the geometry that maps clicks
/// back onto the desk are computed from the same number.
enum CuaScreenObserver {
  struct Display: Equatable, Sendable {
    let id: CGDirectDisplayID
    /// Global points, top-left origin. The space clicks and AX frames live in.
    let bounds: CGRect
    let pixelWidth: Int
    let pixelHeight: Int
    let isMain: Bool

    var scale: CGFloat {
      bounds.width > 0 ? CGFloat(pixelWidth) / bounds.width : 1
    }
  }

  struct Window: Equatable, Sendable {
    let id: CGWindowID
    let title: String
    let appName: String
    let bundleID: String
    let processID: pid_t
    /// Global points, top-left origin.
    let frame: CGRect
    let isActive: Bool
  }

  struct Capture {
    let image: CGImage
    let geometry: CuaFrameGeometry
  }

  /// Long edge a capture is delivered at.
  ///
  /// Claude rejects an oversized image inside a tool result rather than scaling
  /// it down the way it does for an ordinary message, so the cap has to be the
  /// smaller of the two published tiers: 1568 px is the standard-tier limit and
  /// is accepted by every model, where the 2576 px high-resolution figure is
  /// not. A 16:10 Retina display arrives as 1568x980, which keeps menu bar text
  /// legible.
  static let defaultMaxLongEdge: CGFloat = 1568

  static func displays() -> [Display] {
    var count: UInt32 = 0
    guard CGGetActiveDisplayList(0, nil, &count) == .success, count > 0 else { return [] }
    var ids = [CGDirectDisplayID](repeating: 0, count: Int(count))
    guard CGGetActiveDisplayList(count, &ids, &count) == .success else { return [] }
    let main = CGMainDisplayID()
    return ids.prefix(Int(count)).map { id in
      let bounds = CGDisplayBounds(id)
      let mode = CGDisplayCopyDisplayMode(id)
      return Display(
        id: id,
        bounds: bounds,
        pixelWidth: mode?.pixelWidth ?? Int(bounds.width),
        pixelHeight: mode?.pixelHeight ?? Int(bounds.height),
        isMain: id == main
      )
    }
  }

  /// The display a global point falls on, or the main one when it falls off every
  /// display — which is what a click just outside a window's edge does.
  static func display(containing point: CGPoint, in displays: [Display]) -> Display? {
    displays.first { $0.bounds.contains(point) } ?? displays.first { $0.isMain } ?? displays.first
  }

  static func windows() async -> [Window] {
    guard
      let content = try? await SCShareableContent.excludingDesktopWindows(
        true, onScreenWindowsOnly: true)
    else { return [] }
    let frontmost = await MainActor.run { NSWorkspace.shared.frontmostApplication?.processIdentifier }
    return content.windows.compactMap { window in
      guard let app = window.owningApplication, window.frame.width > 1, window.frame.height > 1
      else { return nil }
      return Window(
        id: window.windowID,
        title: window.title ?? "",
        appName: app.applicationName,
        bundleID: app.bundleIdentifier,
        processID: app.processID,
        frame: window.frame,
        isActive: app.processID == frontmost
      )
    }
  }

  static func captureDisplay(_ display: Display, maxLongEdge: CGFloat = defaultMaxLongEdge) async
    -> Capture?
  {
    guard
      let size = CuaFrameGeometry.fittedImageSize(
        source: CGSize(width: display.pixelWidth, height: display.pixelHeight),
        maxLongEdge: maxLongEdge),
      let content = try? await SCShareableContent.excludingDesktopWindows(
        false, onScreenWindowsOnly: true),
      let target = content.displays.first(where: { $0.displayID == display.id })
    else { return nil }

    let filter = SCContentFilter(display: target, excludingWindows: [])
    guard let image = await captureImage(filter: filter, size: size) else { return nil }
    return Capture(
      image: image,
      geometry: CuaFrameGeometry(bounds: display.bounds, imageSize: size))
  }

  static func captureWindow(id: CGWindowID, maxLongEdge: CGFloat = defaultMaxLongEdge) async
    -> Capture?
  {
    guard
      let content = try? await SCShareableContent.excludingDesktopWindows(
        true, onScreenWindowsOnly: false),
      let window = content.windows.first(where: { $0.windowID == id }),
      window.frame.width > 0, window.frame.height > 0
    else { return nil }

    // A window's frame is in points; capture it at the backing scale of the
    // display it sits on, so text on a Retina screen is captured at the
    // resolution it is drawn at rather than half of it.
    let scale =
      display(containing: CGPoint(x: window.frame.midX, y: window.frame.midY), in: displays())?
      .scale ?? 1
    guard
      let size = CuaFrameGeometry.fittedImageSize(
        source: CGSize(width: window.frame.width * scale, height: window.frame.height * scale),
        maxLongEdge: maxLongEdge)
    else { return nil }

    let filter = SCContentFilter(desktopIndependentWindow: window)
    guard let image = await captureImage(filter: filter, size: size) else { return nil }
    return Capture(
      image: image,
      geometry: CuaFrameGeometry(bounds: window.frame, imageSize: size))
  }

  private static func captureImage(filter: SCContentFilter, size: CGSize) async -> CGImage? {
    let config = SCStreamConfiguration()
    config.width = Int(size.width)
    config.height = Int(size.height)
    config.scalesToFit = true
    config.showsCursor = true
    config.captureResolution = .best
    return try? await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
  }

  /// PNG rather than JPEG: these are screenshots of text, and JPEG artifacts on
  /// small type are exactly what makes a model misread a label it is about to
  /// click.
  static func pngData(from image: CGImage) -> Data? {
    let data = NSMutableData()
    guard
      let destination = CGImageDestinationCreateWithData(
        data, UTType.png.identifier as CFString, 1, nil)
    else { return nil }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination) else { return nil }
    return data as Data
  }
}
