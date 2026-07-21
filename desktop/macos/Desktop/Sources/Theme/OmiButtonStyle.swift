import SwiftUI

/// The app's single button primitive. Primary: accent (white) fill with ink
/// content; secondary: dark fill with a subtle border. Use this instead of
/// per-view ButtonStyle structs so CTAs look and press the same everywhere.
package struct OmiButtonStyle: ButtonStyle {
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
      .foregroundColor(kind == .primary ? OmiColors.backgroundPrimary : OmiColors.textPrimary)
      .padding(.horizontal, horizontalPadding)
      .padding(.vertical, verticalPadding)
      .background(
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(kind == .primary ? OmiColors.accent : OmiColors.backgroundTertiary)
      )
      .overlay {
        if kind == .secondary {
          RoundedRectangle(cornerRadius: radius, style: .continuous)
            .stroke(Color.white.opacity(0.08), lineWidth: 1)
        }
      }
      .opacity(configuration.isPressed ? 0.92 : 1)
      .scaleEffect(configuration.isPressed ? 0.985 : 1)
      .omiAnimation(.easeOut(duration: 0.12), value: configuration.isPressed)
  }
}
