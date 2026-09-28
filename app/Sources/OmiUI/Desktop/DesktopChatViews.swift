import OmiKit
import SwiftUI

// Port of `DesktopChat.tsx` and the chat overlay + `InlineAskCard` from
// `DesktopApp.tsx`. Assistant messages use bubbles, user messages stay
// unboxed, pending replies show a skeleton with the animated Omi dot; the
// transcript follows the bottom until you scroll away.

// MARK: - Message row

struct DesktopChatMessageRow: View {
    let message: ChatMessage
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            if message.sender == .ai {
                omiDot
                bubble
                Spacer(minLength: 0)
            } else {
                Spacer(minLength: 0)
                text
                    .multilineTextAlignment(.trailing)
            }
        }
    }

    private var text: Text {
        Text(message.text)
            .font(.system(size: 14))
            .foregroundStyle(tokens.ink)
    }

    @ViewBuilder
    private var bubble: some View {
        let radius: CGFloat = 16
        text
            .multilineTextAlignment(.leading)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(
                UnevenRoundedRectangle(
                    topLeadingRadius: radius, bottomLeadingRadius: radius,
                    bottomTrailingRadius: radius, topTrailingRadius: radius
                )
                .fill(tokens.glassStrong)
                .overlay(
                    UnevenRoundedRectangle(
                        topLeadingRadius: radius, bottomLeadingRadius: radius,
                        bottomTrailingRadius: radius, topTrailingRadius: radius
                    )
                    .strokeBorder(tokens.line, lineWidth: 1)
                )
        )
        .accessibilityLabel("Omi")
    }

    private var omiDot: some View {
        Circle()
            .fill(tokens.ink)
            .frame(width: 10, height: 10)
            .padding(.bottom, 6)
    }
}

/// Skeleton row with the animated Omi dot for a pending reply.
struct DesktopChatThinking: View {
    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            OmiLoadingMark(size: 22, ink: tokens.ink)
            RoundedRectangle(cornerRadius: 8)
                .fill(tokens.glassQuiet)
                .frame(width: 120, height: 18)
        }
        .accessibilityLabel("Omi is thinking")
    }
}

// MARK: - Transcript (DesktopChat.tsx)

struct DesktopChatTranscript: View {
    @EnvironmentObject var store: AppStore
    /// Terminal chat transport error copy (surface it under the omnibar that
    /// owns chat; AppContracts carries no chat-error field yet — see report).
    var notice: String? = nil
    let onSuggest: (String) -> Void

    @Environment(\.desktopTokens) private var tokens
    /// Following the bottom pauses on user scroll-away, resumes at bottom or
    /// on a new send.
    @State private var follow = true

    var body: some View {
        VStack(spacing: 0) {
            FadedScrollView {
                VStack(spacing: 20) {
                    olderButton
                    emptyState
                    ForEach(store.chatMessages) { message in
                        DesktopChatMessageRow(message: message)
                    }
                    if store.chatBusy && !hasStreamingText {
                        DesktopChatThinking()
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let notice = visibleChatError(DesktopSessionPhase.ready, store.chatErrorCopy) {
                Text(notice)
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(18)
                    .overlay(alignment: .top) {
                        Rectangle().fill(tokens.line).frame(height: 1)
                    }
                    .accessibilityLabel("Chat transport notice")
            }
        }
        .accessibilityLabel("Chat with Omi")
    }

    /// A streaming assistant turn already renders its own text row.
    private var hasStreamingText: Bool {
        if case ChatGenerationUiState.streaming(let text) = store.chatGeneration {
            return !text.isEmpty
        }
        return false
    }

    @ViewBuilder
    private var olderButton: some View {
        if store.hasOlderChat {
            Button {
                Task { await store.loadOlderChatHistory() }
            } label: {
                Text(store.loadingOlderChat ? "Loading earlier…" : "Load earlier messages")
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
                    .padding(10)
            }
            .buttonStyle(GlassPressableStyle())
            .disabled(store.loadingOlderChat)
            .accessibilityLabel("Load earlier messages")
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        if store.chatMessages.isEmpty && !store.chatHistoryLoading {
            VStack(spacing: 12) {
                OmiAvatarShape()
                    .frame(width: 72, height: 72)
                    .foregroundStyle(tokens.ink)
                Text("What's on your mind?")
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(tokens.ink)
                    .multilineTextAlignment(.center)
                Text("Ask about a conversation, a task, or something you want to remember.")
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 400)
                suggestions
            }
            .frame(maxWidth: .infinity)
            .padding(24)
        }
    }

    private var suggestions: some View {
        let prompts = [
            "Help me think through a decision",
            "Turn these thoughts into a plan",
            "Help me prepare for a conversation",
        ]
        return HStack(spacing: 10) {
            ForEach(prompts, id: \.self) { prompt in
                Button {
                    onSuggest(prompt)
                } label: {
                    HStack(alignment: .top, spacing: 12) {
                        Text(prompt)
                            .font(.system(size: 12))
                            .foregroundStyle(tokens.inkMuted)
                            .multilineTextAlignment(.leading)
                        Spacer(minLength: 0)
                        DesktopIcon.arrowOutward
                            .frame(width: 15, height: 15)
                            .foregroundStyle(tokens.inkMuted)
                    }
                    .padding(16)
                    .frame(minHeight: 76, alignment: .topLeading)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .background(
                        RoundedRectangle(cornerRadius: 14)
                            .strokeBorder(tokens.line, lineWidth: 1)
                    )
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Try: \(prompt)")
            }
        }
    }
}

/// The Omi avatar mark: the wordless circle-and-dot glyph.
struct OmiAvatarShape: View {
    var body: some View {
        ZStack {
            Circle().inset(by: 6)
                .stroke(style: StrokeStyle(lineWidth: 2, lineCap: .round))
            Circle().frame(width: 14, height: 14)
        }
    }
}

// MARK: - Inline ask card (DesktopApp.tsx InlineAskCard)

/// Small ask answers pinned under the omnibar: the trailing exchange with a
/// way into the full transcript.
struct InlineAskCard: View {
    @EnvironmentObject var store: AppStore
    let busy: Bool
    let notice: String?
    let onClose: () -> Void
    let onOpenChat: () -> Void

    @Environment(\.desktopTokens) private var tokens

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("OMI")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(tokens.inkMuted)
                Spacer(minLength: 0)
                Button(action: onClose) {
                    DesktopIcon.close
                        .frame(width: 14, height: 14)
                        .foregroundStyle(tokens.inkMuted)
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(GlassPressableStyle())
                .accessibilityLabel("Dismiss answer")
            }
            if let ask = lastAsk {
                Text(ask)
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.inkMuted)
                    .lineLimit(2)
            }
            if let notice {
                Text(notice)
                    .font(.system(size: 13))
                    .foregroundStyle(tokens.red)
            } else if let answer = firstAnswer {
                Text(answer)
                    .font(.system(size: 14))
                    .foregroundStyle(tokens.ink)
                    .lineLimit(4)
            } else {
                HStack(spacing: 8) {
                    OmiLoadingMark(size: 18, ink: tokens.ink)
                    Text(busy ? "Thinking…" : "No answer yet.")
                        .font(.system(size: 14))
                        .foregroundStyle(tokens.ink)
                }
            }
            Button(action: onOpenChat) {
                Text("Open chat")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(tokens.ink)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 10).fill(tokens.glassSelected))
            }
            .buttonStyle(GlassPressableStyle())
            .accessibilityLabel("Open chat")
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(tokens.surfaceInk)
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .strokeBorder(tokens.lineStrong, lineWidth: 1)
                )
        )
        .accessibilityLabel("Inline chat answer")
    }

    /// The last human turn plus the first assistant answer after it.
    private var lastAsk: String? {
        let index = store.chatMessages.lastIndex { $0.sender == .human }
        guard let index else { return nil }
        let text = store.chatMessages[index].text
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    private var firstAnswer: String? {
        let index = store.chatMessages.lastIndex { $0.sender == .human }
        guard let index else { return nil }
        let after = store.chatMessages.dropFirst(index + 1)
        guard let answer = after.first(where: { $0.sender == .ai }) else { return nil }
        let text = answer.text.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }
}

// MARK: - Chat overlay (DesktopApp.tsx chatOverlay)

/// Chat is an overlay, not a route: rendered over the stage so the omnibar
/// that feeds it stays visible; the close control restores the previous page.
struct DesktopChatOverlay: View {
    let notice: String?
    let onClose: () -> Void
    let onSuggest: (String) -> Void

    @Environment(\.desktopTokens) private var tokens
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var appeared = false

    var body: some View {
        ZStack {
            // Scrim: tapping restores the previous page.
            Color.black.opacity(0.16)
                .onTapGesture(perform: onClose)
                .accessibilityLabel("Close chat")
            VStack(spacing: 0) {
                DesktopChatTranscript(
                    notice: notice,
                    onSuggest: onSuggest
                )
            }
            .frame(maxWidth: 720, maxHeight: .infinity)
            .background(
                RoundedRectangle(cornerRadius: DesktopLayout.glassCornerRadius)
                    .fill(tokens.surfaceInk.opacity(tokens.isLight ? 1 : 0.001))
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesktopLayout.glassCornerRadius)
                    .strokeBorder(tokens.lineStrong, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: DesktopLayout.glassCornerRadius))
            .opacity(appeared ? 1 : 0.65)
            .offset(y: appeared ? 0 : DesktopMotion.chatRiseY)
            .onAppear {
                withAnimation(DesktopMotion.overlayAnimation(reduceMotion)) {
                    appeared = true
                }
            }
        }
        .environment(\.desktopTokens, tokens)
    }
}
