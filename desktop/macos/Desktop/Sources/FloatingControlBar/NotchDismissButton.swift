import OmiTheme
import SwiftUI

/// `DismissButton` for the notch's black glass: the one close control every floating-bar card
/// uses.
///
/// `DismissButton` itself draws with `GlassShellChrome`'s light-panel Ink ladder, which is
/// near-black on this surface (see `NotchGlassChrome.swift`), so the notch gets this variant with
/// the same glyph, the same "Dismiss (Esc)" label, and `NotchGlass` colors. The target is
/// `NotchDismissButton.diameter` (24 pt), the minimum click size; the cards it sat on used an
/// 18 pt circle with three different labels, and one had none.
struct NotchDismissButton: View {
  /// The visible circle and the click target: 24 pt, the smallest a pointer should have to hit.
  nonisolated static let diameter: CGFloat = 24
  /// Inset from the card's top-trailing corner, chosen so the larger circle keeps the old one's
  /// center.
  static let inset: CGFloat = OmiSpacing.sm

  let action: () -> Void
  /// What is dismissed, for VoiceOver only ("Dismiss suggestion"). The visible tooltip stays
  /// "Dismiss (Esc)" everywhere.
  var accessibilityLabel: String = "Dismiss"

  var body: some View {
    Button(action: action) {
      Image(systemName: "xmark")  // omi-ux-allow: hand-rolled-close -- this is DismissButton's NotchGlass variant
        .scaledFont(size: OmiType.micro, weight: .bold)
    }
    .buttonStyle(NotchDismissButtonStyle())
    .help("Dismiss (Esc)")
    .accessibilityLabel(accessibilityLabel)
  }
}

extension View {
  /// Places the notch card's close control at its top-trailing corner.
  func notchDismissOverlay(
    accessibilityLabel: String = "Dismiss",
    action: @escaping () -> Void = { FloatingControlBarManager.shared.dismissCurrentNotification() }
  ) -> some View {
    overlay(alignment: .topTrailing) {
      NotchDismissButton(action: action, accessibilityLabel: accessibilityLabel)
        .padding(NotchDismissButton.inset)
    }
  }
}

private struct NotchDismissButtonStyle: ButtonStyle {
  func makeBody(configuration: Configuration) -> some View {
    Chrome(configuration: configuration)
  }

  /// A nested view so the hover flag is real `@State` (see `GlassIconButtonStyle`).
  private struct Chrome: View {
    let configuration: Configuration
    @State private var isHovering = false

    var body: some View {
      configuration.label
        .foregroundStyle(NotchGlass.controlLabel(isActive: isHovering || configuration.isPressed))
        .frame(width: NotchDismissButton.diameter, height: NotchDismissButton.diameter)
        .background(
          Circle().fill(
            NotchGlass.controlFill(isActive: configuration.isPressed, isHovering: isHovering))
        )
        .contentShape(Circle())
        .pointingHandOnHover { isHovering = $0 }
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
        .animation(
          InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: configuration.isPressed)
    }
  }
}
