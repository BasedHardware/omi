import SwiftUI

/// Neutral switch toggle: white accent track when on (dark thumb), muted track
/// when off (white thumb). Use instead of the native switch style wherever the
/// app-wide white tint would put a white knob on a white track.
package struct OmiToggleStyle: ToggleStyle {
  private let width: CGFloat = 36
  private let height: CGFloat = 20
  private let thumbSize: CGFloat = 16
  private let thumbPadding: CGFloat = 2

  package init() {}

  package func makeBody(configuration: Configuration) -> some View {
    // No Spacer: call sites lay out their own rows (labels are usually empty),
    // so the style must not expand beyond the switch itself.
    HStack(spacing: OmiSpacing.sm) {
      configuration.label
      ZStack(alignment: configuration.isOn ? .trailing : .leading) {
        Capsule()
          .fill(configuration.isOn ? OmiColors.accent : OmiColors.backgroundQuaternary)
          .frame(width: width, height: height)

        Circle()
          .fill(configuration.isOn ? OmiColors.backgroundPrimary : Color.white)
          .frame(width: thumbSize, height: thumbSize)
          .padding(thumbPadding)
          .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
      }
      .omiAnimation(.easeInOut(duration: 0.15), value: configuration.isOn)
      .onTapGesture {
        configuration.isOn.toggle()
      }
    }
  }
}
