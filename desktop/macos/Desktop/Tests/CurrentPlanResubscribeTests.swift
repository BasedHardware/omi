import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The catalog hides the plan a reader is already on, so Resubscribe has to be a
/// button on the current-plan card. These tests host that control and click it.
@MainActor
final class CurrentPlanResubscribeTests: XCTestCase {

  func testCancelPendingCardRendersResubscribeAndSendsTheCurrentPrice() {
    let latch = ActionLatch()
    let size = CGSize(width: 360, height: 64)
    let host = host(
      CurrentPlanCardActions(
        cancelAtPeriodEnd: true,
        currentPriceId: "price_plus_m",
        checkoutBusy: false,
        portalBusy: false,
        onResubscribe: { latch.price = $0 },
        onManage: { latch.managed = true }
      ),
      size: size)

    if let dir = ProcessInfo.processInfo.environment["OMI_CANCEL_VOID_RENDER"], !dir.isEmpty {
      writeSnapshot(
        CurrentPlanCardActions(
          cancelAtPeriodEnd: true,
          currentPriceId: "price_plus_m",
          checkoutBusy: false,
          portalBusy: false,
          onResubscribe: { _ in },
          onManage: {}
        ),
        to: URL(fileURLWithPath: dir).appendingPathComponent("macos-current-plan-resubscribe.png"))
    }
    click(host, at: CGPoint(x: 48, y: 32))

    XCTAssertEqual(latch.price, "price_plus_m")
    XCTAssertFalse(latch.managed, "the leading click must hit Resubscribe, not Manage")
  }

  func testAnActivePlanCardHasNoResubscribeAction() {
    let latch = ActionLatch()
    let size = CGSize(width: 360, height: 64)
    let host = host(
      CurrentPlanCardActions(
        cancelAtPeriodEnd: false,
        currentPriceId: "price_plus_m",
        checkoutBusy: false,
        portalBusy: false,
        onResubscribe: { latch.price = $0 },
        onManage: { latch.managed = true }
      ),
      size: size)

    click(host, at: CGPoint(x: 48, y: 32))
    XCTAssertNil(latch.price)
    XCTAssertTrue(latch.managed)
  }

  private func host(_ view: some View, size: CGSize) -> NSHostingView<AnyView> {
    let host = NSHostingView(rootView: AnyView(view.frame(width: size.width, height: size.height, alignment: .leading)))
    host.frame = NSRect(origin: .zero, size: size)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: size),
      styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
    host.layoutSubtreeIfNeeded()
    addTeardownBlock {
      window.orderOut(nil)
      window.contentView = nil
    }
    return host
  }

  /// `point` is in the hosting view, origin top-left, matching the other click harnesses.
  private func click(_ host: NSView, at point: CGPoint) {
    guard let window = host.window else {
      XCTFail("the hosting view must be in a window before it can be clicked")
      return
    }
    let appKit = NSPoint(x: point.x, y: host.bounds.height - point.y)
    let down = NSEvent.mouseEvent(
      with: .leftMouseDown, location: appKit, modifierFlags: [], timestamp: 0,
      windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)
    let up = NSEvent.mouseEvent(
      with: .leftMouseUp, location: appKit, modifierFlags: [], timestamp: 0.01,
      windowNumber: window.windowNumber, context: nil, eventNumber: 2, clickCount: 1, pressure: 0)
    if let down { window.sendEvent(down) }
    if let up { window.sendEvent(up) }
  }

  private func writeSnapshot(_ view: some View, to url: URL) {
    let renderer = ImageRenderer(
      content:
        view
        .frame(width: 360, height: 64, alignment: .leading)
        .padding(16)
        .background(Color(white: 0.96)))
    renderer.scale = 2
    guard let image = renderer.nsImage,
      let tiff = image.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let data = rep.representation(using: .png, properties: [:])
    else { return }
    try? FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try? data.write(to: url)
  }

  private final class ActionLatch: @unchecked Sendable {
    var price: String?
    var managed = false
  }
}
