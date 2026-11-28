import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// "Who is this?" for one transcript line (Flutter `name_speaker_sheet`): `SpeakerNamePicker` on
/// this conversation's `TranscriptSpeakersStore`.
struct NameSpeakerSheet: View {
    let line: ConversationDetail.Line
    let speakers: TranscriptSpeakersStore
    @Environment(SettingsStore.self) private var settings

    var body: some View {
        SpeakerNamePicker(
            line: .init(
                text: line.text, isUser: line.isUser, personID: line.personID, hasVoice: line.speakerID != nil,
                sameVoiceCount: speakers.lines(sameVoiceAs: line).count, offersNotAPerson: true
            ),
            isSaving: speakers.isSaving
        ) { choice, scope in
            let speakers = speakers
            let settings = settings
            let line = line
            Task {
                if await speakers.assign(line, to: choice, scope: scope) != nil { await settings.loadPeople() }
            }
        }
    }
}

/// "Is this also <name>?" for each earlier conversation where the same voice speaks
/// (Flutter `earlier_voice_matches_sheet`).
struct VoiceMatchesSheet: View {
    let speakers: TranscriptSpeakersStore
    @Environment(\.dismiss) private var dismiss
    @State private var player = AudioClipPlayer()
    @State private var unplayable: Set<String> = []

    var body: some View {
        NavigationStack {
            List {
                if let matches = speakers.matches {
                    Section {
                        ForEach(matches.items) { match in matchRow(match) }
                    } footer: {
                        Text(L("nativeVoiceMatchesFooter"))
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("nativeVoiceMatchesTitle", speakers.matches?.person.name ?? ""))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } }
            }
            .onChange(of: speakers.matches?.items.isEmpty ?? true) { _, empty in if empty { dismiss() } }
            .onDisappear { player.stop() }
        }
        .presentationDetents([.medium, .large])
    }

    private func matchRow(_ match: VoiceMatch) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(match.title.isEmpty ? L("untitledConversation") : match.title).font(DS.Typography.cardTitle)
                    Text(subtitle(match)).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                }
                Spacer()
                Button {
                    Task {
                        let played = await player.toggle(match.id) { await speakers.clip(for: match) }
                        if !played { unplayable.insert(match.id) }
                    }
                } label: {
                    Image(systemName: player.playingID == match.id ? "stop.circle.fill" : "play.circle.fill").font(.title2)
                }
                .buttonStyle(.plain)
                .disabled(unplayable.contains(match.id))
                .accessibilityLabel(L("speakerTagPromptPlayClip"))
            }
            if unplayable.contains(match.id) {
                Text(L("speakerTagPromptClipUnavailable")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
            }
            HStack(spacing: DS.Spacing.sm) {
                Button(L("yes")) { Task { await speakers.answer(match, same: true) } }.buttonStyle(.omiPill)
                Button(L("no")) { Task { await speakers.answer(match, same: false) } }.buttonStyle(.omiPillSubtle)
            }
        }
        .padding(.vertical, DS.Spacing.xs)
    }

    private func subtitle(_ match: VoiceMatch) -> String {
        let talk = L("speakerLabelTalkTime", Formatting.talkTime(match.talkSeconds))
        guard let date = match.startedAt else { return talk }
        return "\(date.formatted(.dateTime.month(.abbreviated).day())) · \(talk)"
    }
}
