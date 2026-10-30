import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// How Omi helps › Voices & people: your own voice, the people Omi tells apart, and how it learns
/// voices (asking to tag, remembering named voices, ignored voices, clean up).
struct PeopleScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(VoicesStore.self) private var voices
    var voiceScreen: AnyView?
    var onOpenConversation: ((Conversation) -> Void)?
    @State private var query = ""
    @State private var adding = false
    @State private var newName = ""
    @State private var renaming: Person?
    @State private var renameText = ""

    /// Past this many people a search field helps; below it, it is only clutter.
    static let searchThreshold = 8

    var body: some View {
        let people = settings.people(matching: query)
        SettingsList {
            if let voiceScreen, query.isEmpty {
                Section {
                    NavigationLink {
                        voiceScreen
                    } label: {
                        SettingsRowLabel(title: L("nativeRecordYourVoiceAgain"), systemImage: "waveform")
                    }
                } header: {
                    SettingsHeader(L("nativeKickerYourVoice"))
                }
            }
            Section {
                if people.isEmpty, query.isEmpty {
                    Text(L("nativePeopleFooter")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                }
                ForEach(people) { person in
                    NavigationLink {
                        PersonDetailScreen(personID: person.id, onOpenConversation: onOpenConversation)
                    } label: {
                        PersonRow(person: person)
                    }
                    .swipeActions {
                        Button(role: .destructive) { Task { await settings.deletePerson(person.id) } } label: {
                            Label(L("delete"), systemImage: "trash")
                        }
                        Button {
                            renameText = person.name
                            renaming = person
                        } label: {
                            Label(L("nativeRename"), systemImage: "pencil")
                        }
                    }
                }
                if query.isEmpty {
                    Button {
                        newName = ""
                        adding = true
                    } label: {
                        Label(L("nativeAddPerson"), systemImage: "plus")
                    }
                    .accessibilityIdentifier("people.add")
                }
            } header: {
                SettingsHeader(L("people"))
            }
            if query.isEmpty { voiceSettings }
        }
        .modifier(PeopleSearch(query: $query, isOn: settings.people(matching: "").count >= Self.searchThreshold))
        .omiPage(L("nativeSettingsVoices"))
        .task { await settings.loadPeopleWithStats() }
        .task { await voices.loadSettings() }
        .alert(L("nativeAddPerson"), isPresented: $adding) {
            TextField(L("name"), text: $newName).textContentType(.name)
            Button(L("cancel"), role: .cancel) {}
            Button(L("nativeAdd")) {
                let name = newName
                Task { await settings.addPerson(name) }
            }
            .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .alert(L("nativeRename"), isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField(L("name"), text: $renameText)
            Button(L("nativeDone")) {
                if let person = renaming { Task { await settings.renamePerson(person.id, to: renameText) } }
            }
            Button(L("cancel"), role: .cancel) {}
        }
    }

    /// The two voice-learning switches (Flutter `voice_profile_settings_section`), ignored voices
    /// and clean up.
    private var voiceSettings: some View {
        Section {
            Toggle(isOn: Binding(
                get: { voices.settings?.asksToTag ?? true },
                set: { value in Task { await voices.setAsksToTag(value) } }
            )) {
                Text(L("nativeSettingsAskWhoSpoke"))
            }
            .disabled(voices.settings == nil)
            .accessibilityIdentifier("people.askToTag")
            Toggle(isOn: Binding(
                get: { voices.settings?.savesOtherVoices ?? true },
                set: { value in Task { await voices.setSavesOtherVoices(value) } }
            )) {
                Text(L("nativeSettingsRememberVoices"))
            }
            .disabled(voices.settings == nil)
            .accessibilityIdentifier("people.saveOthers")
            NavigationLink(L("nativeSettingsIgnoredVoices")) { IgnoredVoicesScreen() }
            if !settings.cleanUpCandidates.isEmpty {
                NavigationLink {
                    PeopleCleanUpScreen()
                } label: {
                    LabeledContent(L("nativeSettingsCleanUp"), value: String(settings.cleanUpCandidates.count))
                }
                .accessibilityIdentifier("people.cleanUp")
            }
        } header: {
            SettingsHeader(L("nativeSettingsRecognition"))
        } footer: {
            Text(L("voiceSettingsSaveOthersSubtitle"))
        }
    }
}

/// The people search, only once there are enough people to need it.
private struct PeopleSearch: ViewModifier {
    @Binding var query: String
    let isOn: Bool

    func body(content: Content) -> some View {
        if isOn {
            content.searchable(text: $query, placement: .navigationBarDrawer(displayMode: .automatic), prompt: L("peopleSearchPlaceholder"))
        } else {
            content
        }
    }
}

/// Name, pin, and what Omi knows about the voice.
struct PersonRow: View {
    let person: Person

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            Monogram(name: person.name, size: 32)
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                HStack(spacing: DS.Spacing.xs) {
                    Text(person.name).lineLimit(1)
                    if person.isPinned {
                        Image(systemName: "pin.fill").font(.caption2).foregroundStyle(DS.Palette.inkTertiary)
                            .accessibilityLabel(L("pinAction"))
                    }
                }
                Text(details)
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
            }
        }
    }

    private var details: String {
        var parts = [L("nativeVoiceSamples", String(person.sampleCount))]
        if let heard = person.lastHeardAt {
            parts.append(L("nativePersonLastHeardAgo", heard.formatted(.relative(presentation: .named))))
        }
        return parts.joined(separator: " · ")
    }
}
