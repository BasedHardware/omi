import AppKit
import Foundation
import SwiftUI

/// Owns the isolated, real-page window used by the non-production Omens flow.
///
/// Keeping this seam out of `DesktopAutomationBridge.swift` prevents the central
/// automation transport from growing whenever a feature adds presentation coverage.
@MainActor
final class ProjectionAutomationHarness {
  static let shared = ProjectionAutomationHarness()

  private static let windowTitle = "Omi — Omens harness"
  private var window: NSWindow?

  var visibleWindow: NSWindow? {
    window?.isVisible == true ? window : nil
  }

  func registerActions(in registry: DesktopAutomationActionRegistry) {
    registry.register(
      name: "open_projection_harness",
      summary: "Open the real Omens page in an isolated non-production harness window",
      category: "projections",
      surfaces: ["projections"],
      safety: "local_ui_state",
      sideEffects: ["Opens one local test window"]
    ) { [weak self] _ in
      guard let self else { return ["error": "projection harness unavailable"] }
      return await self.open(registry: .shared)
    }
    registry.register(
      name: "close_projection_harness",
      summary: "Close the isolated Omens harness window",
      category: "projections",
      surfaces: ["projections"],
      safety: "local_ui_state",
      sideEffects: ["Closes one local test window"]
    ) { [weak self] _ in
      self?.close()
      return ["closed": "true"]
    }
  }

  private func open(registry: DesktopAutomationActionRegistry) async -> [String: String] {
    close()

    let controller = NSHostingController(
      rootView: ProjectionPage(refreshesOnActivation: false))
    let window = NSWindow(contentViewController: controller)
    window.title = Self.windowTitle
    window.setContentSize(NSSize(width: 720, height: 760))
    window.isReleasedWhenClosed = false
    window.center()
    window.makeKeyAndOrderFront(nil)
    NSApp.activate()
    self.window = window

    let deadline = Date().addingTimeInterval(2)
    while !registry.descriptors().contains(where: { $0.name == "projection_harness_state" }),
      Date() < deadline
    {
      try? await Task.sleep(for: .milliseconds(20))
    }
    let actionRegistered = registry.descriptors().contains {
      $0.name == "projection_harness_state"
    }
    return [
      "opened": "true",
      "action_registered": actionRegistered ? "true" : "false",
    ]
  }

  private func close() {
    window?.close()
    window = nil
  }
}
