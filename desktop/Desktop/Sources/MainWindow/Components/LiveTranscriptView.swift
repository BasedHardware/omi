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
        if displaySegments.isEmpty {
            VStack(spacing: 16) {
                Image(systemName: "waveform")
                    .scaledFont(size: 48)
                    .foregroundColor(OmiColors.textTertiary)
                    .opacity(0.5)
                Text("Live Transcript")
                    .scaledFont(size: 16, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                Text("Start speaking and your transcript will appear here")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(32)
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
        HStack(spacing: 16) {
            HStack(spacing: 6) {
                Image(systemName: "mic.fill")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                AudioLevelWaveformView(
                    level: monitor.microphoneLevel,
                    barCount: 8,
                    isActive: true
                )
            }

            HStack(spacing: 6) {
                Image(systemName: "speaker.wave.2.fill")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
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
            .scaledFont(size: 14, weight: .medium, design: .monospaced)
            .foregroundColor(OmiColors.textSecondary)
    }
}

/// Small view for the recording bar that observes LiveTranscriptMonitor
/// without forcing the parent to re-render.
struct RecordingBarTranscriptText: View {
    @ObservedObject private var monitor = LiveTranscriptMonitor.shared

    var body: some View {
        if let latestText = monitor.latestText, !monitor.isEmpty {
            Text(latestText)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(1)
                .truncationMode(.head)
                .frame(maxWidth: 260, alignment: .leading)
        } else {
            Text("Listening")
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
        }
    }
}

/// Live transcript view showing speaker segments during recording
struct LiveTranscriptView: View {
    let segments: [SpeakerSegment]
    var speakerNames: [Int: String] = [:]
    var onSpeakerTapped: ((SpeakerSegment) -> Void)? = nil

    /// Format timestamp as MM:SS
    private func formatTime(_ seconds: Double) -> String {
        let totalSeconds = Int(seconds)
        let minutes = totalSeconds / 60
        let secs = totalSeconds % 60
        return String(format: "%d:%02d", minutes, secs)
    }

    /// A lightweight fingerprint of the segments to detect any content change
    private var scrollTrigger: String {
        guard let last = segments.last else { return "" }
        return "\(segments.count)-\(last.id)-\(last.text.count)"
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(segments) { segment in
                        LiveSegmentView(
                            segment: segment,
                            formatTime: formatTime,
                            personName: speakerNames[segment.speaker],
                            onSpeakerTapped: segment.speaker != 0 ? { onSpeakerTapped?(segment) } : nil
                        )
                    }

                    // Stable bottom anchor that never changes ID
                    Color.clear
                        .frame(height: 1)
                        .id("transcript-bottom")
                }
                .padding(16)
            }
            .defaultScrollAnchor(.bottom)
            .onChange(of: scrollTrigger) { _, _ in
                proxy.scrollTo("transcript-bottom", anchor: .bottom)
            }
        }
    }
}

/// Individual segment view for live transcript
private struct LiveSegmentView: View {
    let segment: SpeakerSegment
    let formatTime: (Double) -> String
    var personName: String? = nil
    var onSpeakerTapped: (() -> Void)? = nil

    @State private var isHovered = false

    private var isUser: Bool {
        segment.speaker == 0
    }

    private var speakerLabel: String {
        if isUser { return "You" }
        if let name = personName { return name }
        return "Speaker \(segment.speaker)"
    }

    private var bubbleColor: Color {
        isUser ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.backgroundTertiary
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            if !isUser {
                // Other speakers - left aligned
                segmentContent
                Spacer(minLength: 60)
            } else {
                // User - right aligned
                Spacer(minLength: 60)
                segmentContent
            }
        }
    }

    private var segmentContent: some View {
        VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
            // Speaker label and timestamp
            HStack(spacing: 8) {
                if !isUser {
                    speakerAvatar
                }

                if !isUser, let onTap = onSpeakerTapped {
                    Button(action: onTap) {
                        HStack(spacing: 4) {
                            Text(speakerLabel)
                                .scaledFont(size: 12, weight: personName != nil ? .semibold : .medium)
                                .foregroundColor(personName != nil ? OmiColors.purplePrimary : OmiColors.textTertiary)

                            if personName == nil {
                                Image(systemName: "pencil")
                                    .scaledFont(size: 9)
                                    .foregroundColor(OmiColors.textQuaternary)
                                    .opacity(isHovered ? 1 : 0)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .onHover { hovering in
                        isHovered = hovering
                        if hovering {
                            NSCursor.pointingHand.push()
                        } else {
                            NSCursor.pop()
                        }
                    }
                } else {
                    Text(speakerLabel)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Text(formatTime(segment.start))
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textQuaternary)

                if isUser {
                    speakerAvatar
                }
            }

            // Message bubble
            Text(segment.text)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(bubbleColor)
                )
        }
    }

    private var speakerAvatar: some View {
        Circle()
            .fill(isUser ? OmiColors.purplePrimary : (personName != nil ? OmiColors.purplePrimary.opacity(0.6) : OmiColors.backgroundQuaternary))
            .frame(width: 24, height: 24)
            .overlay(
                Text(isUser ? "Y" : (personName?.prefix(1).uppercased() ?? String(segment.speaker)))
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
            )
    }
}

#Preview {
    LiveTranscriptView(segments: [
        SpeakerSegment(speaker: 0, text: "Hello, how are you doing today?", start: 0.0, end: 2.5),
        SpeakerSegment(speaker: 1, text: "I'm doing great, thanks for asking!", start: 3.0, end: 5.5),
        SpeakerSegment(speaker: 0, text: "That's wonderful to hear. Let me tell you about what we're working on.", start: 6.0, end: 10.0),
        SpeakerSegment(speaker: 1, text: "Sure, I'd love to hear more about it.", start: 10.5, end: 12.0)
    ])
    .frame(width: 400, height: 300)
    .background(OmiColors.backgroundSecondary)
}
