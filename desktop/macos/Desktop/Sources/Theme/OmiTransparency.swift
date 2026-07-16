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

/// AppKit-backed material that can sample content behind a transparent window.
package struct OmiVisualEffectView: NSViewRepresentable {
  private let material: NSVisualEffectView.Material
  private let blendingMode: NSVisualEffectView.BlendingMode
  private let alphaValue: CGFloat

  package init(
    material: NSVisualEffectView.Material,
    blendingMode: NSVisualEffectView.BlendingMode,
    alphaValue: CGFloat = 1
  ) {
    self.material = material
    self.blendingMode = blendingMode
    self.alphaValue = alphaValue
  }

  package func makeNSView(context: Context) -> NSVisualEffectView {
    let view = NSVisualEffectView()
    view.material = material
    view.blendingMode = blendingMode
    view.state = .active
    view.alphaValue = alphaValue
    return view
  }

  package func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
    nsView.material = material
    nsView.blendingMode = blendingMode
    nsView.state = .active
    nsView.alphaValue = alphaValue
  }
}

/// A material surface that becomes fully opaque when macOS Reduce Transparency
/// is enabled. It listens for display-option changes so the fallback updates
/// without requiring an app restart.
package struct OmiAdaptiveMaterialBackground: View {
  private let material: NSVisualEffectView.Material
  private let blendingMode: NSVisualEffectView.BlendingMode
  private let alphaValue: CGFloat
  private let fallback: Color
  private let materialOverlay: Color
  @State private var reduceTransparency: Bool

  package init(
    material: NSVisualEffectView.Material = .hudWindow,
    blendingMode: NSVisualEffectView.BlendingMode = .behindWindow,
    alphaValue: CGFloat = 1,
    fallback: Color = OmiColors.backgroundPrimary,
    materialOverlay: Color = .clear
  ) {
    self.material = material
    self.blendingMode = blendingMode
    self.alphaValue = alphaValue
    self.fallback = fallback
    self.materialOverlay = materialOverlay
    _reduceTransparency = State(initialValue: OmiTransparency.reduceTransparency)
  }

  package var body: some View {
    Group {
      if OmiTransparency.shouldUseMaterial(reduceTransparency: reduceTransparency) {
        ZStack {
          OmiVisualEffectView(
            material: material,
            blendingMode: blendingMode,
            alphaValue: alphaValue
          )
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
