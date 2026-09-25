import OmiTheme
import SwiftUI

/// One transcript turn as a chat bubble. The saved transcript and the live capture both render
/// through it, so a meeting looks the same while it is recorded and after it is saved: name · time
/// in the name row, the user's bubble in `Ink.rowFillHover`, every other speaker in their
/// `PageGlass.speakerTints` tint, the same avatar, and `SpeakerLabelFormatter` naming.
struct SpeakerBubbleView: View {
  struct Translation: Equatable {
    let lang: String
    let text: String
  }

  /// Stable per-segment identity, used for accessibility identifiers.
  let segmentID: String
  let text: String
  /// Raw diarization index (0-based); labels and avatars show it 1-based.
  let speakerId: Int
  let start: Double
  let translations: [Translation]
  let isUser: Bool
  var personName: String? = nil
  var onSpeakerTapped: (() -> Void)? = nil
  /// Capture transcripts: jump playback to this segment. Both the bubble and
  /// its timestamp trigger it; other sources pass nil and stay read-only.
  var onMomentTapped: (() -> Void)? = nil
  var isMomentPlayable = false
  /// Find-in-transcript matches inside `text`. Empty for every bubble while no search runs.
  var searchHighlights: [Range<String.Index>] = []
  var currentSearchHighlight: Range<String.Index>? = nil

  @State private var isBubbleHovered = false
  @State private var isLabelHovered = false

  /// A saved transcript segment.
  init(
    segment: TranscriptSegment,
    isUser: Bool,
    personName: String? = nil,
    onSpeakerTapped: (() -> Void)? = nil,
    onMomentTapped: (() -> Void)? = nil,
    isMomentPlayable: Bool = false,
    searchHighlights: [Range<String.Index>] = [],
    currentSearchHighlight: Range<String.Index>? = nil
  ) {
    segmentID = segment.id
    text = segment.text
    speakerId = segment.speakerId
    start = segment.start
    translations = segment.translations.map { Translation(lang: $0.lang, text: $0.text) }
    self.isUser = isUser
    self.personName = personName
    self.onSpeakerTapped = onSpeakerTapped
    self.onMomentTapped = onMomentTapped
    self.isMomentPlayable = isMomentPlayable
    self.searchHighlights = searchHighlights
    self.currentSearchHighlight = currentSearchHighlight
  }

  /// A live-capture segment, still streaming. Live bubbles carry no playback or search.
  init(liveSegment: SpeakerSegment, personName: String? = nil, onSpeakerTapped: (() -> Void)? = nil) {
    segmentID = liveSegment.id
    text = liveSegment.text
    speakerId = liveSegment.speaker
    start = liveSegment.start
    translations = liveSegment.translations.map { Translation(lang: $0.lang, text: $0.text) }
    isUser = liveSegment.isUser
    self.personName = personName
    self.onSpeakerTapped = onSpeakerTapped
  }

  /// The user's bubble is the neutral fill; every other speaker gets their tint.
  var bubbleColor: Color {
    if isUser {
      return Ink.rowFillHover
    }
    let colorIndex = max(0, speakerId) % PageGlass.speakerTints.count
    return PageGlass.speakerTints[colorIndex]
  }

  /// "3:38", or "1:02:05" once the recording passes an hour.
  private func formatTime(_ seconds: Double) -> String {
    OmiDateFormat.offset(seconds)
  }

  var speakerLabel: String {
    if isUser { return "You" }
    if let name = personName, !name.isEmpty { return name }
    return SpeakerLabelFormatter.anonymousLabel(speakerId: speakerId)
  }

  var avatarInitial: String {
    if isUser { return "Y" }
    if let name = personName, let first = name.first {
      return String(first).uppercased()
    }
    return String(SpeakerLabelFormatter.displayNumber(speakerId: speakerId))
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.sm) {
      if !isUser {
        // Avatar for other speakers
        avatar
      }

      VStack(alignment: isUser ? .trailing : .leading, spacing: OmiSpacing.xxs) {
        // Name row: the speaker and where in the recording they spoke, together, so the time reads
        // as part of the turn rather than floating loose under the bubble.
        HStack(spacing: OmiSpacing.xs) {
          if isUser { timestamp }
          speakerLabelView
          if !isUser { timestamp }
        }

        // Message bubble
        // NOTE: SwiftUI text selection was removed here because it wraps each Text
        // in an NSTextView-backed StyledTextLayoutEngine, which is extremely expensive.
        // With 400 segments in a conversation, this caused 2+ second main thread hangs.
        // Users can still copy the full transcript via the "Copy" button in the header.
        if let onMomentTapped, isMomentPlayable {
          // The whole sentence is the seek target, not only the small
          // timestamp under it: a listener re-reading a line wants to hear it.
          Button(action: onMomentTapped) {
            HStack(alignment: .center, spacing: OmiSpacing.xs) {
              if isUser {
                hoverPlayGlyph
              }
              messageBubble
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                    .fill(Ink.accent.opacity(isBubbleHovered ? 0.16 : 0))
                )
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                    .stroke(Ink.accent.opacity(isBubbleHovered ? 0.8 : 0), lineWidth: 1.5)
                )
              if !isUser {
                hoverPlayGlyph
              }
            }
            .contentShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
          }
          .buttonStyle(.plain)
          .help("Play from \(formatTime(start))")
          .accessibilityLabel("Play transcript from \(formatTime(start)): \(text)")
          .accessibilityIdentifier("transcript_bubble_button_\(segmentID)")
          .pointingHandOnHover { isBubbleHovered = $0 }
        } else {
          messageBubble
        }

        // Translations from backend
        if !translations.isEmpty {
          ForEach(translations, id: \.lang) { translation in
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

      }

      if isUser {
        // Avatar for user
        avatar
      }
    }
    .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
  }

  /// The speaker's name. For other speakers it is the way to (re)assign who spoke: an unnamed speaker
  /// always shows the pencil, a named one shows it under the pointer, so correcting a wrong name is
  /// as discoverable as setting the first one.
  @ViewBuilder
  private var speakerLabelView: some View {
    if !isUser, let onTap = onSpeakerTapped {
      Button(action: onTap) {
        HStack(spacing: OmiSpacing.xxs) {
          Text(speakerLabel)
            .scaledFont(size: OmiType.caption, weight: .medium)
          Image(systemName: "pencil")
            .scaledFont(size: OmiType.micro)
            .opacity(personName == nil || isLabelHovered ? 1 : 0)
        }
        .padding(.vertical, OmiSpacing.xxs)
        .contentShape(Rectangle())
        .foregroundColor(personName != nil ? Ink.primary : Ink.secondary)
      }
      .buttonStyle(.plain)
      .help(personName == nil ? "Name this speaker…" : "Change speaker…")
      .accessibilityIdentifier("transcript_speaker_button_\(segmentID)")
      .accessibilityLabel("Transcript speaker \(speakerLabel)")
      .pointingHandOnHover { isLabelHovered = $0 }
    } else {
      Text(speakerLabel)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
    }
  }

  /// Capture transcripts reuse their timestamps as precise playback controls. Other conversation
  /// sources keep the ordinary read-only timestamp without acquiring capture-specific chrome.
  @ViewBuilder
  private var timestamp: some View {
    if let onMomentTapped {
      Button(action: onMomentTapped) {
        HStack(spacing: OmiSpacing.xxs) {
          Image(systemName: "play.circle")
          Text(formatTime(start))
            .monospacedDigit()
        }
        .scaledFont(size: OmiType.caption)
        .foregroundColor(isMomentPlayable ? Ink.primary : Ink.secondary)
      }
      .buttonStyle(.plain)
      .disabled(!isMomentPlayable)
      .help(isMomentPlayable ? "Play from this moment" : "Timestamped playback is still preparing")
      .accessibilityLabel("Play transcript from \(formatTime(start))")
    } else {
      Text(formatTime(start))
        .scaledFont(size: OmiType.caption)
        .monospacedDigit()
        .foregroundColor(Ink.secondary)
    }
  }

  /// Appears beside the bubble under the pointer so the affordance is
  /// unmistakable without cluttering the transcript at rest.
  private var hoverPlayGlyph: some View {
    Image(systemName: "play.circle.fill")
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.accent)
      .opacity(isBubbleHovered ? 1 : 0)
      .accessibilityHidden(true)
  }

  private var messageBubble: some View {
    bubbleText
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
          .fill(bubbleColor)
      )
  }

  /// Plain `Text` unless this bubble holds a search match; only matching bubbles pay for an
  /// attributed string.
  private var bubbleText: Text {
    guard !searchHighlights.isEmpty else { return Text(text) }
    return Text(
      TranscriptSearchModel.highlighted(
        text,
        ranges: searchHighlights,
        current: currentSearchHighlight,
        matchColor: Ink.accent.opacity(0.22),
        currentColor: Ink.accent.opacity(0.5)
      ))
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
