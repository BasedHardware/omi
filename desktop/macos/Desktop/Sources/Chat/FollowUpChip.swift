import OmiTheme
import SwiftUI

/// The one grounded next question under an answer, as a chip you can tap.
///
/// It is a chip rather than a sentence in the prose because the measurement it
/// exists for is whether the reader takes it: a tap is an unambiguous accept,
/// and it sends the exact question Omi offered rather than whatever the reader
/// retypes. The secondary hint appears only where push-to-talk is actually
/// available — offering a shortcut that does nothing on this surface is worse
/// than offering none.
struct FollowUpChip: View {
  enum Palette {
    /// The floating bar and notch, whose ink is the white-on-black glass scale.
    case glass
    /// The main window, on the standard semantic ink scale.
    case standard
  }

  let question: String
  var palette: Palette = .glass
  /// Secondary hint, shown only where push-to-talk exists on this surface.
  /// Nil elsewhere: a shortcut hint that does nothing is worse than none.
  var voiceHint: String?
  let action: () -> Void

  @State private var isHovered = false

  private var labelColor: Color {
    switch palette {
    case .glass: return NotchGlass.ink(.w85)
    case .standard: return Ink.primary
    }
  }

  private var hintColor: Color {
    switch palette {
    case .glass: return NotchGlass.quiet
    case .standard: return Ink.secondary
    }
  }

  private var fill: Color {
    switch palette {
    case .glass: return NotchGlass.ink(isHovered ? .w15 : .w1)
    case .standard: return isHovered ? Ink.rowFillHover : Ink.rowFill
    }
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Button(action: action) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "arrow.turn.down.right")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(hintColor)
          Text(question)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(labelColor)
            .multilineTextAlignment(.leading)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xs)
        .background(fill)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .onHover { isHovered = $0 }
      .accessibilityLabel("Ask: \(question)")
      .accessibilityIdentifier("chat-follow-up-chip")

      if let voiceHint {
        Text(voiceHint)
          .scaledFont(size: OmiType.micro)
          .foregroundColor(hintColor)
          .padding(.leading, OmiSpacing.sm)
          .accessibilityIdentifier("chat-follow-up-voice-hint")
      }
    }
  }
}
