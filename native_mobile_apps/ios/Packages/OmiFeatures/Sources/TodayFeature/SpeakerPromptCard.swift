import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// "Who is this?" as a sheet from Home's For you row; closes once nothing is left to ask.
struct SpeakerPromptSheet: View {
    @Environment(VoicesStore.self) private var voices
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            SpeakerPromptCard().padding(DS.Spacing.gutter)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(DS.Palette.background)
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .onChange(of: voices.currentPrompt == nil, initial: true) { _, isEmpty in if isEmpty { dismiss() } }
    }
}

/// The "Who is this?" card: one voice from a recent conversation at a time, answered in a tap
/// (Flutter `speaker_tag_prompt_card`). Closing it tells Omi to ask less often.
struct SpeakerPromptCard: View {
    @Environment(VoicesStore.self) private var voices
    @State private var player = AudioClipPlayer()
    @State private var unplayable: Set<String> = []
    @State private var naming = false
    @State private var newName = ""

    var body: some View {
        if let prompt = voices.currentPrompt {
            VStack(alignment: .leading, spacing: DS.Spacing.md) {
                HStack(alignment: .firstTextBaseline) {
                    Label(Self.question(prompt), systemImage: "person.wave.2").font(DS.Typography.cardTitle)
                    Spacer()
                    Button {
                        player.stop()
                        Task { await voices.dismissPrompts() }
                    } label: { Image(systemName: "xmark").font(.footnote.weight(.semibold)) }
                        .foregroundStyle(DS.Palette.inkTertiary)
                        .accessibilityLabel(L("close"))
                        .accessibilityIdentifier("speakerPrompt.dismiss")
                }
                HStack(alignment: .top, spacing: DS.Spacing.md) {
                    playButton(prompt)
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        if !prompt.excerpt.isEmpty {
                            Text("“\(prompt.excerpt)”").font(DS.Typography.callout.italic()).lineLimit(3)
                        }
                        Text(prompt.conversationTitle.isEmpty ? L("untitledConversation") : prompt.conversationTitle)
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkSecondary)
                        if unplayable.contains(prompt.id) {
                            Text(L("speakerTagPromptClipUnavailable")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
                        }
                    }
                }
                answers(prompt)
            }
            .omiCard(padding: DS.Spacing.lg)
            .task(id: prompt.id) { await voices.promptsShown() }
            .alert(L("speakerTagPromptWhoIsThis"), isPresented: $naming) {
                TextField(L("speakerTagPromptNameHint"), text: $newName)
                Button(L("cancel"), role: .cancel) {}
                Button(L("save")) {
                    let name = newName.trimmingCharacters(in: .whitespacesAndNewlines)
                    if name.count >= 2 { answer(prompt, .newPerson(String(name.prefix(40)))) }
                }
            }
            .accessibilityIdentifier("speakerPrompt.card")
        }
    }

    static func question(_ prompt: SpeakerPrompt) -> String {
        switch prompt.kind {
        case .ownerCheck: L("speakerTagPromptIsThisYou")
        case .confirmPerson: L("speakerTagPromptIsThisPerson", prompt.suggestedPersonName ?? "")
        case .identify: L("speakerTagPromptWhoIsThis")
        }
    }

    @ViewBuilder
    private func answers(_ prompt: SpeakerPrompt) -> some View {
        switch prompt.kind {
        case .ownerCheck:
            chips([(L("yes"), .me), (L("no"), .notMe), (L("speakerTagPromptNotSureAction"), .skip)], prompt)
        case .confirmPerson:
            let yes: SpeakerPromptAnswer = prompt.suggestedPersonID.map { .person($0) } ?? .skip
            chips([(L("yes"), yes), (L("no"), .someoneElse), (L("speakerTagPromptNotSureAction"), .skip)], prompt)
        case .identify:
            ScrollView(.horizontal) {
                HStack(spacing: DS.Spacing.sm) {
                    ForEach(prompt.candidates) { candidate in
                        Button(candidate.name) { answer(prompt, .person(candidate.id)) }.buttonStyle(.omiPill)
                    }
                    Button(L("speakerTagPromptThatsMeAction")) { answer(prompt, .me) }.buttonStyle(.omiPillSubtle)
                    Button(L("newPersonEllipsis")) {
                        newName = ""
                        naming = true
                    }
                    .buttonStyle(.omiPillSubtle)
                    Button(L("speakerTagPromptNotAPerson")) { answer(prompt, .notAPerson) }.buttonStyle(.omiPillSubtle)
                    Button(L("speakerTagPromptNotSureAction")) { answer(prompt, .skip) }.buttonStyle(.omiPillSubtle)
                }
                .padding(.horizontal, DS.Spacing.lg)
            }
            .scrollIndicators(.hidden)
            .padding(.horizontal, -DS.Spacing.lg)
        }
    }

    private func chips(_ options: [(String, SpeakerPromptAnswer)], _ prompt: SpeakerPrompt) -> some View {
        HStack(spacing: DS.Spacing.sm) {
            ForEach(Array(options.enumerated()), id: \.offset) { index, option in
                Button(option.0) { answer(prompt, option.1) }
                    .buttonStyle(OmiPillButtonStyle(prominent: index == 0))
            }
        }
    }

    private func playButton(_ prompt: SpeakerPrompt) -> some View {
        Button {
            Task {
                let played = await player.toggle(prompt.id) { await voices.clip(for: prompt) }
                if !played { unplayable.insert(prompt.id) }
            }
        } label: {
            Image(systemName: player.playingID == prompt.id ? "stop.circle.fill" : "play.circle.fill")
                .font(.system(size: 34))
                .foregroundStyle(unplayable.contains(prompt.id) ? DS.Palette.inkDisabled : DS.Palette.agent)
        }
        .buttonStyle(.plain)
        .disabled(unplayable.contains(prompt.id))
        .accessibilityLabel(L("speakerTagPromptPlayClip"))
    }

    private func answer(_ prompt: SpeakerPrompt, _ answer: SpeakerPromptAnswer) {
        DSHaptics.selection()
        player.stop()
        Task { await voices.answer(prompt, answer) }
    }
}
