import SwiftUI

/// The app's switch: a white knob on a tinted track when on, on a neutral track when off.
///
/// This is the shape a macOS switch has always had, and it is now the shape this one has too. The
/// dark-palette version inverted it — a **white** track when on with a near-black knob — which was
/// legible only because the page behind it was near-black. On the light glass panel that rendered a
/// white track on a white ground with no border: every switch in Settings looked identically "off",
/// and the one piece of state a switch exists to show was gone.
///
/// So the track carries the state and the knob stays white in both, which is the only arrangement
/// that keeps the on/off difference readable on a light ground.
///
/// The off track is `systemGray` — a *named* system colour, the same kind `Ink` is built from, and
/// not a wash. A wash was the first attempt and it failed a measurement: `Ink.hairline` over the
/// light panel leaves the white knob at **1.55:1**, well under WCAG 1.4.11's 3:1 bar for a
/// graphical object you must see to read the control's state. `systemGray` puts it at 3.28:1. The
/// knob is the part that says *which way the switch is thrown*, so it is not allowed to be a
/// low-contrast detail carried by its drop shadow alone.
package struct OmiToggleStyle: ToggleStyle {
  private let width: CGFloat = 36
  private let height: CGFloat = 20
  private let thumbSize: CGFloat = 16
  private let thumbPadding: CGFloat = 2

  /// The track, as a pure function of state.
  ///
  /// Exposed for the same reason `PageGlass`'s colours are: "the on and off tracks are actually
  /// different, and both are actually visible against the knob" is the entire contract of a switch,
  /// and it is assertable as values without a window server.
  ///
  /// `nonisolated` for the same reason `InkButtonStyle.minHeight` is: `ToggleStyle` is `@MainActor`,
  /// and these are values a caller may want to read rather than draw with.
  nonisolated package static func trackFill(isOn: Bool) -> Color {
    isOn ? Ink.accent : Color(nsColor: .systemGray)
  }

  /// The knob, in both states. White is not decoration here — it is what makes the track's state
  /// readable, so it is stated once rather than forked.
  nonisolated package static let knobFill = Color.white

  package init() {}

  package func makeBody(configuration: Configuration) -> some View {
    // No Spacer: call sites lay out their own rows (labels are usually empty),
    // so the style must not expand beyond the switch itself.
    HStack(spacing: OmiSpacing.sm) {
      configuration.label
      ZStack(alignment: configuration.isOn ? .trailing : .leading) {
        Capsule()
          .fill(Self.trackFill(isOn: configuration.isOn))
          .frame(width: width, height: height)

        Circle()
          .fill(Self.knobFill)
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
