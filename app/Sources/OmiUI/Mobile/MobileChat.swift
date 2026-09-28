import OmiKit
import SwiftUI

// Mobile chat surface, ported from `react-native/src/mobile/MobileChat.tsx`:
// Close control outside the message scroll region, the breathing mark header,
// the resting prompt state with quick prompts, Load older messages, and the
// error panel. Presentation only — the store owns requests and history.

public struct MobileChat: View {
    @EnvironmentObject private var store: AppStore
    public let onClose: () -> Void
    public let reduceMotion: Bool

    public init(onClose: @escaping () -> Void, reduceMotion: Bool = false) {
        self.onClose = onClose
        self.reduceMotion = reduceMotion
    }

    private var resting: Bool {
        store.chatMessages.isEmpty && !busy && !store.chatHistoryLoading
            && chatError == nil
    }

    private var busy: Bool {
        if case .pending = store.chatGeneration { return true }
        if case .streaming = store.chatGeneration { return true }
        return false
    }

    private var streamingVisible: Bool {
        store.chatMessages.contains { isStreamingAssistant($0) }
    }

    private var chatError: String? {
        if case .streaming = store.chatGeneration { return nil }
        if let message = store.chatMessages.last,
            message.sender == .ai, message.generationOutcome == .failed
        {
            return message.generationRetryable == true
                ? "Response failed. Try again." : "Response failed."
        }
        return nil
    }

    private var hasOlder: Bool {
        // The store owns the history cursor; surface the affordance whenever a
        // loaded history exists and no load is in flight.
        !store.chatMessages.isEmpty
    }

    public var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if store.chatHistoryLoading {
                        HStack(spacing: 12) {
                            ProgressView().tint(MobilePalette.textMuted)
                            Text("Loading your conversation…")
                                .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                                .foregroundColor(MobilePalette.textMuted)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(24)
                        .accessibilityLabel("Loading chat history")
                    }
                    if hasOlder, !store.chatHistoryLoading {
                        Button(action: { Task { await store.loadOlderChatHistory() } }) {
                            Text("Load older messages")
                                .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                                .foregroundColor(MobilePalette.textMuted)
                                .frame(maxWidth: .infinity).frame(minHeight: 44)
                        }
                        .buttonStyle(KitPressableStyle())
                        .background(MobilePalette.surface)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .accessibilityLabel("Load older messages")
                    }
                    if resting {
                        restingState
                    }
                    ForEach(store.chatMessages) { message in
                        ChatMessageRowView(
                            message: message, compact: true,
                            reduceMotion: reduceMotion
                        )
                    }
                    if busy, !streamingVisible {
                        ChatThinkingView(reduceMotion: reduceMotion)
                    }
                    if let chatError {
                        Text(chatError)
                            .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                            .foregroundColor(MobilePalette.textMuted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(Space.md)
                            .background(MobilePalette.surface)
                            .overlay(
                                RoundedRectangle(cornerRadius: MobileRadius.md)
                                    .strokeBorder(MobilePalette.border, lineWidth: 0.5)
                            )
                            .clipShape(RoundedRectangle(cornerRadius: MobileRadius.md))
                            .accessibilityLabel(chatError)
                    }
                }
                .padding(16)
                .frame(minHeight: 400, alignment: .top)
            }
            .accessibilityLabel("Chat scroll region")
        }
        .background(MobilePalette.background)
    }

    private var header: some View {
        HStack(spacing: 12) {
            Button(action: onClose) {
                KitIcon(.chevronLeft, size: 22, color: MobilePalette.text)
                    .frame(width: 44, height: 44)
                    .background(MobilePalette.surface)
                    .clipShape(RoundedRectangle(cornerRadius: MobileRadius.chip))
            }
            .buttonStyle(KitPressableStyle())
            .accessibilityLabel("Close chat")
            Spacer()
            OmiAvatarView(
                size: 36, motion: busy ? .breathe : .arrive, reduceMotion: reduceMotion
            )
            Spacer()
            Color.clear.frame(width: 44, height: 44)
        }
        .padding(Space.md)
        .overlay(
            VStack(spacing: 0) {
                Spacer()
                Rectangle()
                    .fill(MobilePalette.border)
                    .frame(height: 0.5)
            }
        )
    }

    private var restingState: some View {
        VStack(spacing: 16) {
            OmiAvatarView(size: 72, motion: .arrive, reduceMotion: reduceMotion)
            Text("Start with a thought.")
                .font(TypeStyle(size: 26, lineHeight: 32, weight: .regular).font)
                .tracking(-0.6)
                .foregroundColor(MobilePalette.text)
            Text("Ask about your day, untangle an idea, or find a next step.")
                .font(TypeStyle(size: 15, lineHeight: 23, weight: .regular).font)
                .foregroundColor(MobilePalette.textMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 280)
            VStack(spacing: 8) {
                ForEach(AppStore.quickPrompts) { prompt in
                    Button(action: {
                        store.composerText = prompt.text
                        Task { await store.sendChat(prompt.text) }
                    }) {
                        Text(prompt.text)
                            .font(TypeStyle(size: 14, lineHeight: 21, weight: .regular).font)
                            .foregroundColor(MobilePalette.textMuted)
                            .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 48)
                            .padding(14)
                    }
                    .buttonStyle(KitPressableStyle())
                    .background(MobilePalette.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: MobileRadius.md)
                            .strokeBorder(MobilePalette.border, lineWidth: 0.5)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: MobileRadius.md))
                    .accessibilityLabel("Try: \(prompt.text)")
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}
