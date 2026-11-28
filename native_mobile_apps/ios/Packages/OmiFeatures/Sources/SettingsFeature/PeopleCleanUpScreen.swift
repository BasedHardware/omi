import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Review before a bulk delete: everyone Omi is unsure about starts ticked; pinned people are never
/// listed (Flutter `people_clean_up_page`).
struct PeopleCleanUpScreen: View {
    @Environment(SettingsStore.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var ticked: Set<String>?
    @State private var confirms = false

    var body: some View {
        let candidates = settings.cleanUpCandidates
        let selected = (ticked ?? Set(candidates.map(\.id))).intersection(candidates.map(\.id))
        SettingsList {
            if candidates.isEmpty {
                ContentUnavailableView(
                    L("cleanUpNothingTitle"), systemImage: "checkmark.circle", description: Text(L("cleanUpNothingMessage"))
                )
            } else {
                Section {
                    ForEach(candidates) { person in
                        Button {
                            DSHaptics.selection()
                            var next = selected
                            if next.contains(person.id) { next.remove(person.id) } else { next.insert(person.id) }
                            ticked = next
                        } label: {
                            HStack {
                                Image(systemName: selected.contains(person.id) ? "checkmark.circle.fill" : "circle")
                                    .foregroundStyle(selected.contains(person.id) ? DS.Palette.ink : DS.Palette.inkTertiary)
                                PersonRow(person: person).foregroundStyle(DS.Palette.ink)
                            }
                        }
                    }
                } header: {
                    SettingsHeader(L("nativeCleanUpLead"))
                } footer: {
                    Text(L("cleanUpPinnedNote"))
                }
                Section {
                    Button(L("nativeDeleteSelectedPeople", String(selected.count)), role: .destructive) { confirms = true }
                        .disabled(selected.isEmpty)
                        .accessibilityIdentifier("people.cleanUp.delete")
                }
            }
        }
        .omiPage(L("cleanUpTitle"))
        .toolbar {
            if !candidates.isEmpty {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(selected.count == candidates.count ? L("deselectAll") : L("selectAll")) {
                        ticked = selected.count == candidates.count ? [] : Set(candidates.map(\.id))
                    }
                }
            }
        }
        .confirmationDialog(
            L("nativeDeletePeopleQuestion", String(selected.count)), isPresented: $confirms, titleVisibility: .visible
        ) {
            Button(L("nativeDeleteSelectedPeople", String(selected.count)), role: .destructive) {
                Task {
                    await settings.deletePeople(selected)
                    if settings.lastError == nil { dismiss() }
                }
            }
        } message: {
            Text(L("nativeDeletePersonMessage"))
        }
    }
}

/// Voices marked Not a Person (TV, podcasts); restoring one lets Omi ask about it again
/// (Flutter `ignored_voices_sheet`).
struct IgnoredVoicesScreen: View {
    @Environment(VoicesStore.self) private var voices

    var body: some View {
        SettingsList {
            if voices.ignoredLoaded, voices.ignored.isEmpty {
                ContentUnavailableView(L("ignoredVoicesEmpty"), systemImage: "speaker.slash")
            }
            Section {
                ForEach(voices.ignored) { voice in
                    HStack {
                        VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                            Text(voice.conversationTitle.isEmpty ? L("untitledConversation") : voice.conversationTitle).lineLimit(1)
                            Text(L("speakerWithId", String(voice.speakerID + 1)))
                                .font(DS.Typography.caption)
                                .foregroundStyle(DS.Palette.inkSecondary)
                        }
                        Spacer()
                        Button(L("restoreAction")) { Task { await voices.restore(voice) } }
                            .buttonStyle(.omiPillSubtle)
                    }
                }
            } footer: {
                if !voices.ignored.isEmpty { Text(L("voiceRestoredToast")) }
            }
        }
        .omiPage(L("ignoredVoicesTitle"))
        .task { await voices.loadIgnored() }
    }
}
