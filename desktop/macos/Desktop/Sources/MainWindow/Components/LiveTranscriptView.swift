import OmiTheme
import SwiftUI

/// Self-contained panel that observes LiveTranscriptMonitor internally,
/// so the parent view does NOT need to observe transcript changes.
struct LiveTranscriptPanel: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared
  var speakerNames: [Int: String] = [:]
  var onSpeakerTapped: ((SpeakerSegment) -> Void)? = nil

  private var displaySegments: [SpeakerSegment] {
    if !monitor.segments.isEmpty { return monitor.segments }
    return monitor.savedSegments
  }

  var body: some View {
    content.reportsLiveTranscriptVisibility()
  }

  @ViewBuilder private var content: some View {
    if displaySegments.isEmpty {
      VStack(spacing: OmiSpacing.lg) {
        Image(systemName: "waveform")
          .scaledFont(size: 48)
          .foregroundColor(Ink.secondary)
          .opacity(0.5)
        Text("Live Transcript")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(Ink.secondary)
        Text("Start speaking and your transcript will appear here")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .padding(OmiSpacing.section)
    } else {
      LiveTranscriptView(
        segments: displaySegments,
        speakerNames: speakerNames,
        onSpeakerTapped: onSpeakerTapped
      )
    }
  }
}

/// Self-contained audio level waveforms that observe AudioLevelMonitor internally,
/// so the parent view does NOT need to observe audio level changes.
struct RecordingBarAudioLevels: View {
  @ObservedObject private var monitor = AudioLevelMonitor.shared

  var body: some View {
    HStack(spacing: OmiSpacing.lg) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "mic.fill")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        AudioLevelWaveformView(
          level: monitor.microphoneLevel,
          barCount: 8,
          isActive: true
        )
      }

      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "speaker.wave.2.fill")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        AudioLevelWaveformView(
          level: monitor.systemLevel,
          barCount: 8,
          isActive: true
        )
      }
    }
    .fixedSize()  // Prevent constraint invalidations from propagating to parent NSHostingView
  }
}

/// Self-contained recording duration text that observes RecordingTimer internally.
struct RecordingBarDuration: View {
  @ObservedObject private var timer = RecordingTimer.shared

  var body: some View {
    Text(timer.formattedDuration)
      .scaledFont(size: OmiType.body, weight: .medium, design: .monospaced)
      .foregroundColor(Ink.secondary)
  }
}

/// Small view for the recording bar that observes LiveTranscriptMonitor
/// without forcing the parent to re-render.
struct RecordingBarTranscriptText: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared

  var body: some View {
    if let latestText = monitor.latestText, !monitor.isEmpty {
      Text(latestText)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .lineLimit(1)
        .truncationMode(.head)
        .frame(maxWidth: 260, alignment: .leading)
    } else {
      Text("Listening")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
    }
  }
}

/// Live transcript card shown at the top of Conversations while recording —
/// updates in real time as speech is transcribed. Observes the monitor directly
/// so the surrounding page doesn't re-render on every segment.
///
/// Clicking anywhere on the card invokes `onExpand`, letting the parent present
/// a full-screen view of the live transcript.
struct ConversationsLiveTranscript: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared

  /// Invoked when the user clicks the card. When non-nil, the card shows an
  /// expand affordance and the whole surface becomes tappable.
  var onExpand: (() -> Void)? = nil

  @State private var isHovered = false

  var body: some View {
    content.reportsLiveTranscriptVisibility()
  }

  @ViewBuilder private var content: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        Circle().fill(Ink.errorRed).frame(width: 7, height: 7)
        Text("Live").scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.secondary)
        Spacer()
        if onExpand != nil {
          Image(systemName: "arrow.up.left.and.arrow.down.right")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(isHovered ? Ink.primary : Ink.secondary)
        }
      }
      if monitor.isEmpty {
        Text("Listening…").scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
          .padding(.vertical, OmiSpacing.sm)
      } else {
        LiveTranscriptView(segments: monitor.segments)
          .frame(maxHeight: 220)
          // Let clicks fall through to the card's expand tap rather than being
          // captured by the inner scroll view.
          .allowsHitTesting(false)
      }
    }
    .padding(OmiSpacing.lg)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous)
        .fill(Ink.rowFill)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous)
            .stroke(
              Ink.separator.opacity(onExpand != nil && isHovered ? 0.55 : 0.3), lineWidth: 1))
    )
    .contentShape(RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous))
    .modifier(LiveTranscriptExpandTap(onExpand: onExpand, isHovered: $isHovered))
  }
}

/// Replaces the Live card between "capture stopped" and "row in the list".
/// Same slot, same shape, same last line of transcript — the capture the
/// user was watching is what is being saved.
struct ConversationsSavingCaptureCard: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared
  @State private var pulse = false

  private var lastLine: String? {
    monitor.savedSegments.last?.text ?? monitor.latestText
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        Circle()
          .fill(Ink.accent)
          .frame(width: 7, height: 7)
          .opacity(pulse ? 0.4 : 1.0)
          .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: pulse)
        Text("Saving").scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.secondary)
        Spacer()
      }
      if let lastLine, !lastLine.isEmpty {
        Text(lastLine)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .lineLimit(2)
          .padding(.vertical, OmiSpacing.sm)
      } else {
        Text("Adding to your conversations…").scaledFont(size: OmiType.body).foregroundColor(Ink.secondary)
          .padding(.vertical, OmiSpacing.sm)
      }
    }
    .padding(OmiSpacing.lg)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous)
        .fill(Ink.rowFill)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.cardRadius, style: .continuous)
            .stroke(Ink.separator.opacity(0.3), lineWidth: 1))
    )
    .onAppear { pulse = true }
    .accessibilityIdentifier("conversations-saving-capture")
  }
}

/// Adds the click-to-expand behavior only when an `onExpand` handler is present,
/// so the card stays inert (no pointer cursor, no tap) when expansion is
/// unavailable.
private struct LiveTranscriptExpandTap: ViewModifier {
  let onExpand: (() -> Void)?
  @Binding var isHovered: Bool

  /// Tracks whether we currently hold a pushed cursor so push/pop stay balanced
  /// and the pointing-hand cursor is always popped when the card stops being
  /// hovered — SwiftUI doesn't deliver an `onHover(false)` when the view leaves
  /// the hierarchy. Two exit paths are handled explicitly: `onDisappear`
  /// (capture pauses and the `if appState.isLiveCapturing` card is removed) and
  /// the tap handler (expanding replaces the page, which also unmounts the card;
  /// popping here keeps the cursor from lingering for a frame).
  @State private var didPushCursor = false

  private func setHovered(_ hovering: Bool) {
    isHovered = hovering
    if hovering, !didPushCursor {
      NSCursor.pointingHand.push()
      didPushCursor = true
    } else if !hovering, didPushCursor {
      NSCursor.pop()
      didPushCursor = false
    }
  }

  func body(content: Content) -> some View {
    if let onExpand {
      content
        .onTapGesture {
          // Pop the pointing-hand before the page swaps away the card.
          setHovered(false)
          onExpand()
        }
        .onHover { setHovered($0) }
        .onDisappear { setHovered(false) }
        .help("Expand live transcript")
    } else {
      content
    }
  }
}

/// Full-panel live transcript, presented in place of the Conversations list when
/// the user expands the compact live card. Observes the monitor directly so it
/// keeps updating live. Hosted on the same glass panel — paints no ground of its own.
struct ConversationsLiveTranscriptFullScreen: View {
  @ObservedObject private var monitor = LiveTranscriptMonitor.shared
  var onCollapse: () -> Void

  var body: some View {
    content.reportsLiveTranscriptVisibility()
  }

  @ViewBuilder private var content: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: OmiSpacing.sm) {
        Circle().fill(Ink.errorRed).frame(width: 8, height: 8)
        Text("Live Transcript")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Spacer()
        Button(action: onCollapse) {
          Image(systemName: "arrow.down.right.and.arrow.up.left")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .padding(OmiSpacing.sm)
            .glassChip()
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.escape, modifiers: [])
        .help("Collapse")
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.top, OmiSpacing.lg)
      .padding(.bottom, OmiSpacing.md)

      Divider().overlay(Ink.separator.opacity(0.3))

      if monitor.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "waveform")
            .scaledFont(size: 48)
            .foregroundColor(Ink.secondary)
            .opacity(0.5)
          Text("Listening…")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        LiveTranscriptView(segments: monitor.segments)
          .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

/// Live transcript view showing speaker segments during recording. Each turn renders through the
/// saved transcript's `SpeakerBubbleView`, so a capture does not change layout or colors once saved.
struct LiveTranscriptView: View {
  let segments: [SpeakerSegment]
  var speakerNames: [Int: String] = [:]
  var onSpeakerTapped: ((SpeakerSegment) -> Void)? = nil

  /// A lightweight fingerprint of the segments to detect any content change
  private var scrollTrigger: String {
    guard let last = segments.last else { return "" }
    return "\(segments.count)-\(last.id)-\(last.text.count)"
  }

  var body: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          // NOTE: no SwiftUI text selection on these bubbles. It wraps each Text in an
          // NSTextView-backed StyledTextLayoutEngine (SelectionOverlay), the
          // FC-selection-overlay-layout-loop failure class the saved transcript hit; a long capture
          // mounts one overlay per segment and every live update relays them all. Once saved, the
          // conversation detail header's Copy control copies the full transcript.
          ForEach(segments) { segment in
            SpeakerBubbleView(
              liveSegment: segment,
              personName: speakerNames[segment.speaker],
              onSpeakerTapped: segment.isUser || onSpeakerTapped == nil ? nil : { onSpeakerTapped?(segment) }
            )
          }

          // Stable bottom anchor that never changes ID
          Color.clear
            .frame(height: 1)
            .id("transcript-bottom")
        }
        .padding(OmiSpacing.lg)
      }
      .defaultScrollAnchor(.bottom)
      .onChange(of: scrollTrigger) { _, _ in
        proxy.scrollTo("transcript-bottom", anchor: .bottom)
      }
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    LiveTranscriptView(segments: [
      SpeakerSegment(speaker: 0, text: "Hello, how are you doing today?", start: 0.0, end: 2.5),
      SpeakerSegment(speaker: 1, text: "I'm doing great, thanks for asking!", start: 3.0, end: 5.5),
      SpeakerSegment(
        speaker: 0, text: "That's wonderful to hear. Let me tell you about what we're working on.", start: 6.0,
        end: 10.0),
      SpeakerSegment(speaker: 1, text: "Sure, I'd love to hear more about it.", start: 10.5, end: 12.0),
    ])
    .frame(width: 400, height: 300)
    .background(Ink.rowFill)
  }
#endif
