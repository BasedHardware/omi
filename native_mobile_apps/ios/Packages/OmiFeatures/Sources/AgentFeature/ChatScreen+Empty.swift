import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The empty state, the composer and sending.
extension ChatScreen {
    @ViewBuilder
    var loadingOrFailed: some View {
        if chat.historyFailed {
            VStack(spacing: DS.Spacing.md) {
                Label(L("nativeChatHistoryFailed"), systemImage: "wifi.exclamationmark")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                Button(L("retry")) { Task { await chat.retryHistory() } }
                    .buttonStyle(.omiPill)
            }
        } else {
            ProgressView()
        }
    }

    @ViewBuilder
    var greeting: some View {
        if let app = chat.chatApp {
            Text(L("nativeChatWithAppGreeting", app.name))
                .font(DS.Typography.title)
                .padding(.top, DS.Spacing.xl)
                .accessibilityAddTraits(.isHeader)
        } else {
            omiGreeting
        }
    }

    var omiGreeting: some View {
        let hour = Calendar.current.component(.hour, from: .now)
        let part = hour < 12 ? L("greetingMorning") : hour < 18 ? L("greetingAfternoon") : L("greetingEvening")
        let name = session.displayName?.split(separator: " ").first.map(String.init) ?? ""
        return VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text((name.isEmpty ? part : L("greetingWithName", part, name)) + ".")
                .font(DS.Typography.display)
            Text(L("whatDoYouWantToKnow"))
                .font(.title3)
                .foregroundStyle(DS.Palette.inkSecondary)
        }
        .padding(.top, DS.Spacing.xl)
        .accessibilityAddTraits(.isHeader)
    }

    /// Omi's suggestions: about my day once there are conversations, otherwise about Omi.
    var starters: some View {
        let prompts = conversations.conversations.isEmpty
            ? [L("chatStarterPrompt.capabilities"), L("chatStarterPrompt.goal")]
            : [L("askSuggestDecide"), L("askSuggestOwe"), L("askSuggestNotice")]
        return ScrollView(.horizontal) {
            HStack(spacing: DS.Spacing.sm) {
                ForEach(prompts, id: \.self) { prompt in
                    Button { send(prompt) } label: {
                        Text(prompt)
                            .font(DS.Typography.callout)
                            .foregroundStyle(DS.Palette.ink)
                            .padding(.horizontal, DS.Spacing.lg)
                            .frame(minHeight: 40)
                            .omiSurface(Capsule(), interactive: true)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, DS.Spacing.lg)
        }
        .scrollIndicators(.hidden)
    }

    /// Prepends the older page and keeps the message that was on top where it was, so the chat
    /// does not jump.
    func loadEarlier(_ proxy: ScrollViewProxy) async {
        guard let anchor = chat.messages.first?.id else { return }
        await chat.loadEarlier()
        if chat.messages.first?.id != anchor { proxy.scrollTo(anchor, anchor: .top) }
    }

    /// Text to send, and no photo or file still on its way up.
    var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !chat.isUploading
    }

    func send() {
        if isDictating { dictation?.stop() }
        if chat.isStreaming {
            chat.cancel()
            return
        }
        guard canSend else { return }
        send(draft)
        draft = ""
    }

    func send(_ text: String) {
        DSHaptics.tap()
        voice.stop()
        chat.send(text)
    }
}
