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
            return NootoColors.userBubble
        }
        let colorIndex = segment.speakerId % NootoColors.speakerColors.count
        return NootoColors.speakerColors[colorIndex]
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
        HStack(alignment: .top, spacing: 10) {
            if !isUser {
                // Avatar for other speakers
                avatar
            }

            VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
                // Speaker label — clickable for non-user speakers
                if !isUser, let onTap = onSpeakerTapped {
                    Button(action: onTap) {
                        HStack(spacing: 4) {
                            Text(speakerLabel)
                                .scaledFont(size: 12, weight: .medium)
                            if personName == nil {
                                Image(systemName: "pencil")
                                    .scaledFont(size: 10)
                            }
                        }
                        .foregroundColor(personName != nil ? NootoColors.brandPrimary : NootoColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .onHover { hovering in
                        if hovering {
                            NSCursor.pointingHand.push()
                        } else {
                            NSCursor.pop()
                        }
                    }
                } else {
                    Text(speakerLabel)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(NootoColors.textTertiary)
                }

                // Message bubble
                // NOTE: .textSelection(.enabled) was removed here because it wraps each Text
                // in an NSTextView-backed StyledTextLayoutEngine, which is extremely expensive.
                // With 400 segments in a conversation, this caused 2+ second main thread hangs.
                // Users can still copy the full transcript via the "Copy" button in the header.
                Text(segment.text)
                    .scaledFont(size: 14)
                    .foregroundColor(NootoColors.textPrimary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 18)
                            .fill(bubbleColor)
                    )

                // Timestamp
                Text(formatTime(segment.start))
                    .scaledFont(size: 11)
                    .foregroundColor(NootoColors.textQuaternary)
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
            .fill(isUser ? NootoColors.brandPrimary : (personName != nil ? NootoColors.brandPrimary.opacity(0.3) : NootoColors.backgroundQuaternary))
            .frame(width: 32, height: 32)
            .overlay(
                Text(avatarInitial)
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(NootoColors.textPrimary)
            )
    }
}

#Preview {
    VStack(spacing: 16) {
        Text("SpeakerBubbleView Preview")
            .foregroundColor(.white)
    }
    .padding()
    .background(NootoColors.backgroundPrimary)
}
