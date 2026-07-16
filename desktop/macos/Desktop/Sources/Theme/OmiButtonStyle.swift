import SwiftUI

/// The app's single button primitive. Primary: accent (white) fill with ink
/// content; secondary: dark fill with a subtle border. Use this instead of
/// per-view ButtonStyle structs so CTAs look and press the same everywhere.
package struct OmiButtonStyle: ButtonStyle {
  @Environment(\.isEnabled) private var isEnabled
  @State private var isHovered = false

  package enum Kind {
    case primary
    case secondary
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

  package func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .scaledFont(size: fontSize, weight: .semibold)
      .foregroundColor(foregroundColor)
      .padding(.horizontal, horizontalPadding)
      .padding(.vertical, verticalPadding)
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(backgroundColor(isPressed: configuration.isPressed))
      )
      .overlay {
        if kind == .secondary {
          RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(
              OmiColors.border.opacity(isHovered || configuration.isPressed ? 0.80 : 0.32),
              lineWidth: 1
            )
        }
      }
      .scaleEffect(configuration.isPressed ? 0.97 : 1)
      .omiAnimation(.easeOut(duration: 0.12), value: configuration.isPressed)
      .omiAnimation(.easeOut(duration: 0.15), value: isHovered)
      .onHover { isHovered = $0 }
      .omiPointerCursor(isEnabled: isEnabled)
  }

  private var foregroundColor: Color {
    guard isEnabled else { return OmiColors.disabledForeground }
    return kind == .primary ? OmiColors.backgroundPrimary : OmiColors.textPrimary
  }

  private func backgroundColor(isPressed: Bool) -> Color {
    guard isEnabled else { return OmiColors.disabledBackground }

    switch kind {
    case .primary:
      if isPressed { return OmiColors.accentPressed }
      if isHovered { return OmiColors.accentHover }
      return OmiColors.accent
    case .secondary:
      if isPressed || isHovered { return OmiColors.backgroundQuaternary }
      return OmiColors.backgroundTertiary
    }
  }
}
