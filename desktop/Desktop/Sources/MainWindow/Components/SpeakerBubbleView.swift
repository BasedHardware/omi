import SwiftUI

/// Chat bubble view for a transcript segment
struct SpeakerBubbleView: View {
    let segment: TranscriptSegment
    let isUser: Bool

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
        isUser ? "You" : "Speaker \(segment.speakerId)"
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if !isUser {
                // Avatar for other speakers
                avatar
            }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                // Speaker label
                Text(speakerLabel)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(OmiColors.textTertiary)

                // Message bubble
                Text(segment.text)
                    .font(.system(size: 14))
                    .foregroundColor(OmiColors.textPrimary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 18)
                            .fill(bubbleColor)
                    )

                // Timestamp
                Text(formatTime(segment.start))
                    .font(.system(size: 11))
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
            .fill(isUser ? OmiColors.purplePrimary : OmiColors.backgroundQuaternary)
            .frame(width: 32, height: 32)
            .overlay(
                Text(isUser ? "Y" : String(segment.speakerId))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
            )
    }
}

#Preview {
    VStack(spacing: 16) {
        Text("SpeakerBubbleView Preview")
            .foregroundColor(.white)
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
