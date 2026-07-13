import AppKit
import SwiftUI

/// Accessibility-aware transparency policy, parallel to `OmiMotion`.
package enum OmiTransparency {
  package static var reduceTransparency: Bool {
    NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
  }

  package static func shouldUseMaterial(reduceTransparency: Bool) -> Bool {
    !reduceTransparency
  }
}

/// A material surface that becomes fully opaque when macOS Reduce Transparency
/// is enabled. It listens for display-option changes so the fallback updates
/// without requiring an app restart.
package struct OmiAdaptiveMaterialBackground: View {
  private let material: Material
  private let fallback: Color
  private let materialOverlay: Color
  @State private var reduceTransparency: Bool

  package init(
    material: Material = .ultraThinMaterial,
    fallback: Color = OmiColors.backgroundPrimary,
    materialOverlay: Color = .clear
  ) {
    self.material = material
    self.fallback = fallback
    self.materialOverlay = materialOverlay
    _reduceTransparency = State(initialValue: OmiTransparency.reduceTransparency)
  }

  package var body: some View {
    Group {
      if OmiTransparency.shouldUseMaterial(reduceTransparency: reduceTransparency) {
        ZStack {
          Rectangle().fill(material)
          materialOverlay
        }
      } else {
        fallback
      }
    }
    .onReceive(
      NotificationCenter.default.publisher(
        for: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification
      )
    ) { _ in
      reduceTransparency = OmiTransparency.reduceTransparency
    }
  }
}
