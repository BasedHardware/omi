import OmiKit
import SwiftUI

// Chat transcript primitives ported from `react-native/src/ui/ChatTranscript.tsx`
// (compact/mobile presentation): the message row with its bubble, timestamp,
// failure and cancelled copy, and the thinking skeleton.

public struct ChatMessageRowView: View {
    public let message: ChatMessage
    /// Compact = mobile column width and ink-tone avatar.
    public let compact: Bool
    public let animate: Bool
    public let reduceMotion: Bool

    public init(
        message: ChatMessage, compact: Bool = true, animate: Bool = false,
        reduceMotion: Bool = false
    ) {
        self.message = message
        self.compact = compact
        self.animate = animate
        self.reduceMotion = reduceMotion
    }

    public var body: some View {
        let human = message.sender == .human
        let streaming = isStreamingAssistant(message)
        let waiting = streaming && message.text.isEmpty
        HStack(alignment: .top, spacing: Space.sm) {
            if !human {
                OmiAvatarView(
                    size: compact ? 28 : 40, motion: streaming ? .breathe : .resting,
                    reduceMotion: reduceMotion
                )
            }
            VStack(alignment: human ? .trailing : .leading, spacing: 4) {
                bubble(human: human, waiting: waiting)
                if message.generationOutcome == .cancelled {
                    Text("Response stopped")
                        .font(TypeStyle(size: 11, lineHeight: 14, weight: .regular).font)
                        .foregroundColor(Palette.textSubtle)
                }
                Text(KitFormat.chatTime(createdAt: message.createdAt))
                    .font(Typography.caption.font)
                    .foregroundColor(OmiColor.hex(0x666666))
            }
            .frame(maxWidth: compact ? 340 : 480, alignment: human ? .trailing : .leading)
        }
        .frame(maxWidth: .infinity, alignment: human ? .trailing : .leading)
        .accessibilityLabel(accessibility(human: human, waiting: waiting))
        .opacity(animate && !reduceMotion ? 1 : 1)
    }

    @ViewBuilder
    private func bubble(human: Bool, waiting: Bool) -> some View {
        let background = human ? OmiColor.hex(0x2C2C33) : Palette.surface
        VStack(alignment: .leading, spacing: 6) {
            if message.generationOutcome == .failed {
                Text(
                    message.generationRetryable == true
                        ? "Response failed. Try again." : "Response failed."
                )
                .font(TypeStyle(size: 12, lineHeight: 16, weight: .regular).font)
                .foregroundColor(OmiColor.hex(0xD8A0A0))
            } else if waiting {
                SkeletonLines()
            } else {
                Text(message.text)
                    .font(Typography.body.font)
                    .foregroundColor(OmiColor.hex(0xE5E5E5))
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(background)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .opacity(message.generationOutcome == .cancelled ? 0.72 : 1)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(
                    message.generationOutcome == .cancelled
                        ? Palette.textSubtle : Color.clear,
                    lineWidth: Borders.width
                )
        )
    }

    private func accessibility(human: Bool, waiting: Bool) -> String {
        if message.generationOutcome == .failed { return "Failed response" }
        if waiting { return "Waiting for response" }
        return human ? "You said" : "Omi said"
    }
}

/// The thinking skeleton (three placeholder lines) with the breathing pulse.
public struct ChatThinkingView: View {
    public let reduceMotion: Bool

    public init(reduceMotion: Bool = false) {
        self.reduceMotion = reduceMotion
    }

    public var body: some View {
        HStack(alignment: .top, spacing: Space.sm) {
            OmiAvatarView(size: 28, motion: .breathe, reduceMotion: reduceMotion)
            VStack(alignment: .leading, spacing: 6) {
                SkeletonLines()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(Palette.surface)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(reduceMotion ? 1 : 0.9)
        .accessibilityLabel("Waiting for response")
    }
}

public struct SkeletonLines: View {
    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            line(fraction: 1.0)
            line(fraction: 0.86)
            line(fraction: 0.62)
        }
    }

    private func line(fraction: CGFloat) -> some View {
        Capsule()
            .fill(Palette.input)
            .frame(height: 10)
            .frame(maxWidth: .infinity)
            .scaleEffect(x: fraction, anchor: .leading)
    }
}
