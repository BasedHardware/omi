import OmiTheme
import SwiftUI

/// Chat bubble view for a transcript segment
struct SpeakerBubbleView: View {
  let segment: TranscriptSegment
  let isUser: Bool
  var personName: String? = nil
  var onSpeakerTapped: (() -> Void)? = nil
  /// Capture transcripts: jump playback to this segment. Both the bubble and
  /// its timestamp trigger it; other sources pass nil and stay read-only.
  var onMomentTapped: (() -> Void)? = nil
  var isMomentPlayable = false

  @State private var isBubbleHovered = false

  /// Get speaker color based on speaker ID
  private var bubbleColor: Color {
    if isUser {
      return Ink.rowFillHover
    }
    let colorIndex = segment.speakerId % PageGlass.speakerTints.count
    return PageGlass.speakerTints[colorIndex]
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
            .foregroundColor(personName != nil ? Ink.primary : Ink.secondary)
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
            .foregroundColor(Ink.secondary)
        }

        // Message bubble
        // NOTE: .textSelection(.enabled) was removed here because it wraps each Text
        // in an NSTextView-backed StyledTextLayoutEngine, which is extremely expensive.
        // With 400 segments in a conversation, this caused 2+ second main thread hangs.
        // Users can still copy the full transcript via the "Copy" button in the header.
        if let onMomentTapped, isMomentPlayable {
          // The whole sentence is the seek target, not only the small
          // timestamp under it: a listener re-reading a line wants to hear it.
          Button(action: onMomentTapped) {
            messageBubble
              .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                  .stroke(Ink.accent.opacity(isBubbleHovered ? 0.55 : 0), lineWidth: 1)
              )
              .contentShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
          }
          .buttonStyle(.plain)
          .help("Play from \(formatTime(segment.start))")
          .accessibilityLabel("Play transcript from \(formatTime(segment.start)): \(segment.text)")
          .accessibilityIdentifier("transcript_bubble_button_\(segment.id)")
          .onHover { hovering in
            isBubbleHovered = hovering
            if hovering {
              NSCursor.pointingHand.push()
            } else {
              NSCursor.pop()
            }
          }
        } else {
          messageBubble
        }

        // Translations from backend
        if !segment.translations.isEmpty {
          ForEach(segment.translations, id: \.lang) { translation in
            Text(translation.text)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
              .italic()
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                  .fill(bubbleColor.opacity(0.5))
              )
          }
        }

        // Capture transcripts reuse their existing timestamps as precise
        // playback controls. Other conversation sources keep the ordinary
        // read-only timestamp without acquiring capture-specific chrome.
        if let onMomentTapped {
          Button(action: onMomentTapped) {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "play.circle")
              Text(formatTime(segment.start))
            }
            .scaledFont(size: OmiType.caption)
            .foregroundColor(isMomentPlayable ? Ink.primary : Ink.secondary)
          }
          .buttonStyle(.plain)
          .disabled(!isMomentPlayable)
          .help(isMomentPlayable ? "Play from this moment" : "Timestamped playback is still preparing")
          .accessibilityLabel("Play transcript from \(formatTime(segment.start))")
        } else {
          Text(formatTime(segment.start))
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }

      if isUser {
        // Avatar for user
        avatar
      }
    }
    .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
  }

  private var messageBubble: some View {
    Text(segment.text)
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
          .fill(bubbleColor)
      )
  }

  private var avatar: some View {
    Circle()
      .fill(isUser ? Ink.primary : Ink.rowFillHover)
      .frame(width: 32, height: 32)
      .overlay(
        Text(avatarInitial)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(isUser ? Ink.surface : Ink.primary)
      )
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    VStack(spacing: OmiSpacing.lg) {
      Text("SpeakerBubbleView Preview")
        .foregroundColor(Ink.primary)
    }
    .padding()
    .background(Ink.surface)
  }
#endif
