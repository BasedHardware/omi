import OmiTheme
import SwiftUI

/// Chat bubble view for a transcript segment
struct SpeakerBubbleView: View {
  let segment: TranscriptSegment
  let isUser: Bool
  var personName: String? = nil
  var onSpeakerTapped: (() -> Void)? = nil

  /// Get speaker color based on speaker ID
  private var bubbleColor: Color {
    if isUser {
      return OmiColors.userBubble
    }
    let colorIndex = segment.speakerId % OmiColors.speakerColors.count
    return OmiColors.speakerColors[colorIndex]
  }

  /// Format timestamp as MM:SS
  private func formatTime(_ seconds: Double) -> String {
    let totalSeconds = Int(seconds)
    let minutes = totalSeconds / 60
    let secs = totalSeconds % 60
    return String(format: "%d:%02d", minutes, secs)
  }

  private var speakerLabel: String {
    if isUser { return "You" }
    if let name = personName { return name }
    return "Speaker \(segment.speakerId)"
  }

  private var avatarInitial: String {
    if isUser { return "Y" }
    if let name = personName, let first = name.first {
      return String(first).uppercased()
    }
    return String(segment.speakerId)
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      if !isUser {
        // Avatar for other speakers
        avatar
      }

      VStack(alignment: isUser ? .trailing : .leading, spacing: OmiSpacing.xxs) {
        // Speaker label — clickable for non-user speakers
        if !isUser, let onTap = onSpeakerTapped {
          Button(action: onTap) {
            HStack(spacing: OmiSpacing.xxs) {
              Text(speakerLabel)
                .scaledFont(size: OmiType.caption, weight: .medium)
              if personName == nil {
                Image(systemName: "pencil")
                  .scaledFont(size: OmiType.micro)
              }
            }
            .padding(.vertical, OmiSpacing.hairline)
            .contentShape(Rectangle())
            .foregroundColor(personName != nil ? OmiColors.accent : OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .accessibilityIdentifier("transcript_speaker_button_\(segment.id)")
          .accessibilityLabel("Transcript speaker \(speakerLabel)")
          .onHover { hovering in
            if hovering {
              NSCursor.pointingHand.push()
            } else {
              NSCursor.pop()
            }
          }
        } else {
          Text(speakerLabel)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }

        // Message bubble
        // NOTE: .textSelection(.enabled) was removed here because it wraps each Text
        // in an NSTextView-backed StyledTextLayoutEngine, which is extremely expensive.
        // With 400 segments in a conversation, this caused 2+ second main thread hangs.
        // Users can still copy the full transcript via the "Copy" button in the header.
        Text(segment.text)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textPrimary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.sm)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
              .fill(bubbleColor)
          )

        // Translations from backend
        if !segment.translations.isEmpty {
          ForEach(segment.translations, id: \.lang) { translation in
            Text(translation.text)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
              .italic()
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                  .fill(bubbleColor.opacity(0.5))
              )
          }
        }

        // Timestamp
        Text(formatTime(segment.start))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textQuaternary)
      }

      if isUser {
        // Avatar for user
        avatar
      }
    }
    .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
  }

  private var avatar: some View {
    Circle()
      .fill(
        isUser ? OmiColors.accent : (personName != nil ? OmiColors.accent.opacity(0.3) : OmiColors.backgroundQuaternary)
      )
      .frame(width: 32, height: 32)
      .overlay(
        Text(avatarInitial)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
      )
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    VStack(spacing: OmiSpacing.lg) {
      Text("SpeakerBubbleView Preview")
        .foregroundColor(.white)
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
  }
#endif
