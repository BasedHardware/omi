import SwiftUI

/// The app's single button primitive. Primary: accent (white) fill with ink
/// content; secondary: dark fill with a subtle border; destructive: error fill
/// with white content. Use this instead of per-view ButtonStyle structs so CTAs
/// look and press the same everywhere.
package struct OmiButtonStyle: ButtonStyle {
  package enum Kind {
    case primary
    case secondary
    case destructive
  }

  package enum Size {
    case regular
    case compact
  }

  let kind: Kind
  let size: Size

  package init(_ kind: Kind = .primary, size: Size = .regular) {
    self.kind = kind
    self.size = size
  }

  private var fontSize: CGFloat {
    size == .regular ? OmiType.subheading : OmiType.body
  }

  private var horizontalPadding: CGFloat {
    size == .regular ? 18 : OmiSpacing.md
  }

  private var verticalPadding: CGFloat {
    size == .regular ? OmiSpacing.md : OmiSpacing.sm
  }

  private var radius: CGFloat {
    size == .regular ? OmiChrome.chipRadius : OmiChrome.smallControlRadius
  }

  private var foregroundColor: Color {
    switch kind {
    case .primary:
      OmiColors.backgroundPrimary
    case .secondary, .destructive:
      OmiColors.textPrimary
    }
  }

  private var backgroundColor: Color {
    switch kind {
    case .primary:
      OmiColors.accent
    case .secondary:
      OmiColors.backgroundTertiary
    case .destructive:
      OmiColors.error
    }
  }

  package func makeBody(configuration: Configuration) -> some View {
    OmiButtonContent(
      configuration: configuration,
      kind: kind,
      fontSize: fontSize,
      foregroundColor: foregroundColor,
      backgroundColor: backgroundColor,
      horizontalPadding: horizontalPadding,
      verticalPadding: verticalPadding,
      radius: radius
    )
  }
}

/// Extracted body so it can read `@Environment(\.isEnabled)` — `ButtonStyle`
/// configurations do not expose enabled state directly.
private struct OmiButtonContent: View {
  let configuration: ButtonStyle.Configuration
  let kind: OmiButtonStyle.Kind
  let fontSize: CGFloat
  let foregroundColor: Color
  let backgroundColor: Color
  let horizontalPadding: CGFloat
  let verticalPadding: CGFloat
  let radius: CGFloat

  @Environment(\.isEnabled) private var isEnabled

  var body: some View {
    configuration.label
      .scaledFont(size: fontSize, weight: .semibold)
      .foregroundColor(foregroundColor)
      .padding(.horizontal, horizontalPadding)
      .padding(.vertical, verticalPadding)
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(backgroundColor)
      )
      .overlay {
        if kind == .secondary {
          RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        }
      }
      .opacity(isEnabled ? (configuration.isPressed ? 0.92 : 1) : 0.45)
      .scaleEffect(configuration.isPressed ? 0.985 : 1)
      .omiAnimation(.easeOut(duration: 0.12), value: configuration.isPressed)
  }
}
