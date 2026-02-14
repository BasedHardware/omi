import SwiftUI

/// Live transcript view showing speaker segments during recording
struct LiveTranscriptView: View {
    let segments: [SpeakerSegment]

    /// Format timestamp as MM:SS
    private func formatTime(_ seconds: Double) -> String {
        let totalSeconds = Int(seconds)
        let minutes = totalSeconds / 60
        let secs = totalSeconds % 60
        return String(format: "%d:%02d", minutes, secs)
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
                        LiveSegmentView(
                            segment: segment,
                            formatTime: formatTime
                        )
                        .id(index)
                    }
                }
                .padding(16)
            }
            .onChange(of: segments.count) { _, _ in
                // Auto-scroll to bottom when new segments arrive
                if let lastIndex = segments.indices.last {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(lastIndex, anchor: .bottom)
                    }
                }
            }
        }
    }
}

/// Individual segment view for live transcript
private struct LiveSegmentView: View {
    let segment: SpeakerSegment
    let formatTime: (Double) -> String

    private var isUser: Bool {
        segment.speaker == 0
    }

    private var speakerLabel: String {
        isUser ? "You" : "Speaker \(segment.speaker)"
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

                Text(speakerLabel)
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)

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
            .fill(isUser ? OmiColors.purplePrimary : OmiColors.backgroundQuaternary)
            .frame(width: 24, height: 24)
            .overlay(
                Text(isUser ? "Y" : String(segment.speaker))
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
