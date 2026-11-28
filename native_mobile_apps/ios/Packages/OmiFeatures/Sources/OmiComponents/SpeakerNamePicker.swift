import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Who is this?" for one transcript line: you, one of your people, a new name, or (finished
/// conversations only) not a person (Flutter `name_speaker_sheet`). The search field doubles as the
/// new-name field. Shared by the conversation page and the live transcript.
public struct SpeakerNamePicker: View {
    public typealias Choice = TranscriptSpeakersStore.Choice
    public typealias Scope = TranscriptSpeakersStore.Scope

    /// The line being named.
    public struct Line: Sendable {
        public let text: String
        public let isUser: Bool
        public let personID: String?
        /// The line has a voice (speaker number): naming can cover all of its lines.
        public let hasVoice: Bool
        /// How many lines share its voice.
        public let sameVoiceCount: Int
        /// "Not a person" is offered (finished conversations).
        public let offersNotAPerson: Bool

        public init(text: String, isUser: Bool, personID: String?, hasVoice: Bool, sameVoiceCount: Int, offersNotAPerson: Bool) {
            self.text = text
            self.isUser = isUser
            self.personID = personID
            self.hasVoice = hasVoice
            self.sameVoiceCount = sameVoiceCount
            self.offersNotAPerson = offersNotAPerson && hasVoice
        }
    }

    let line: Line
    let isSaving: Bool
    let onChoose: (Choice, Scope) -> Void
    @Environment(SettingsStore.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var scope = Scope.voice

    /// `onChoose` runs as the sheet closes; the scope is `.line` for a line without a voice.
    public init(line: Line, isSaving: Bool, onChoose: @escaping (Choice, Scope) -> Void) {
        self.line = line
        self.isSaving = isSaving
        self.onChoose = onChoose
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("“\(line.text)”")
                        .font(DS.Typography.callout.italic())
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .lineLimit(3)
                    if line.sameVoiceCount > 1 {
                        Picker(L("nativeSpeakerScope"), selection: $scope) {
                            Text(L("nativeSpeakerAllLines", String(line.sameVoiceCount))).tag(Scope.voice)
                            Text(L("nativeSpeakerOnlyThisLine")).tag(Scope.line)
                        }
                        .pickerStyle(.segmented)
                        .accessibilityIdentifier("nameSpeaker.scope")
                    }
                }
                Section {
                    row(L("speakerTagPromptThatsMeAction"), systemImage: "person.crop.circle", selected: line.isUser) { choose(.me) }
                        .accessibilityIdentifier("nameSpeaker.me")
                }
                people
                if line.offersNotAPerson {
                    Section {
                        Button(L("speakerTagPromptNotAPerson"), role: .destructive) { choose(.notAPerson) }
                            .accessibilityIdentifier("nameSpeaker.notAPerson")
                    } footer: {
                        Text(L("nativeNotAPersonFooter"))
                    }
                }
            }
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: L("nativeSpeakerSearchOrName"))
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("speakerTagPromptWhoIsThis"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private var people: some View {
        Section {
            ForEach(settings.people(matching: query)) { person in
                row(person.name, systemImage: "person", selected: !line.isUser && line.personID == person.id) {
                    choose(.person(person))
                }
            }
            if let newName {
                row(L("addNamedPersonAction", newName), systemImage: "plus.circle", selected: false) { choose(.newPerson(newName)) }
                    .accessibilityIdentifier("nameSpeaker.add")
            } else if settings.people.isEmpty {
                Text(L("nativeSpeakerTypeName"))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
        } header: {
            if !settings.people.isEmpty { Text(L("people")) }
        }
    }

    /// The typed text when it is not already one of your people (or your own name).
    private var newName: String? {
        let name = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard name.count >= 2, name.count <= 40 else { return nil }
        let taken = settings.people.contains { $0.name.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame }
        return taken ? nil : name.prefix(1).uppercased() + name.dropFirst()
    }

    private func row(_ title: String, systemImage: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Label(title, systemImage: systemImage).foregroundStyle(DS.Palette.ink)
                Spacer()
                if selected { Image(systemName: "checkmark").foregroundStyle(DS.Palette.agent) }
            }
        }
        .disabled(isSaving)
    }

    /// The transcript changes at once; the sheet closes without waiting for the server.
    private func choose(_ choice: Choice) {
        DSHaptics.selection()
        let scope = line.hasVoice ? scope : .line
        dismiss()
        onChoose(choice, scope)
    }
}
