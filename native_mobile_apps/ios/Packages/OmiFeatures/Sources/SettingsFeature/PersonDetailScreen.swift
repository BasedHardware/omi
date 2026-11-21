import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// One person: talk time, when Omi last heard them, their voice samples and conversations
/// (Flutter `person_detail_page`).
struct PersonDetailScreen: View {
    let personID: String
    /// Opens a conversation (the shell closes Settings first); rows are plain without it.
    var onOpenConversation: ((Conversation) -> Void)?
    @Environment(SettingsStore.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var player = AudioClipPlayer()
    @State private var conversations: [Conversation] = []
    @State private var page = 0
    @State private var hasMore = true
    @State private var loadFailed = false
    @State private var isLoading = false
    @State private var renaming = false
    @State private var renameText = ""
    @State private var confirmsDelete = false
    @State private var deletingSample: Int?

    var body: some View {
        SettingsList {
            if let person = settings.person(personID) {
                stats(person)
                samples(person)
                conversationSection
            }
        }
        .omiPage(settings.person(personID)?.name ?? "")
        .toolbar {
            if let person = settings.person(personID) {
                ToolbarItem(placement: .topBarTrailing) { menu(person) }
            }
        }
        .task { if settings.person(personID) == nil { await settings.loadPeopleWithStats() } }
        .task { await loadMore() }
        .onDisappear { player.stop() }
        .alert(L("nativeRename"), isPresented: $renaming) {
            TextField(L("nativeYourName"), text: $renameText)
            Button(L("cancel"), role: .cancel) {}
            Button(L("save")) { Task { await settings.renamePerson(personID, to: renameText) } }
        }
        .confirmationDialog(
            L("nativeDeletePersonQuestion", settings.person(personID)?.name ?? ""),
            isPresented: $confirmsDelete, titleVisibility: .visible
        ) {
            Button(L("deletePersonLabel"), role: .destructive) {
                let id = personID
                dismiss()
                Task { await settings.deletePerson(id) }
            }
        } message: {
            Text(L("nativeDeletePersonMessage"))
        }
        .confirmationDialog(
            L("deleteSampleQuestion"),
            isPresented: Binding(get: { deletingSample != nil }, set: { if !$0 { deletingSample = nil } }),
            titleVisibility: .visible
        ) {
            Button(L("deleteSample"), role: .destructive) {
                if let index = deletingSample {
                    player.stop()
                    Task { await settings.deleteSample(of: personID, at: index) }
                }
            }
        } message: {
            Text(L("deleteSampleConfirmation", settings.person(personID)?.name ?? ""))
        }
    }

    /// Pin, rename and delete: the rarer actions, in the one menu.
    private func menu(_ person: Person) -> some View {
        Menu {
            Toggle(isOn: Binding(
                get: { person.isPinned },
                set: { value in Task { await settings.setPinned(person.id, value) } }
            )) {
                Label(L("pinAction"), systemImage: "pin")
            }
            .accessibilityIdentifier("person.pin")
            Button(L("nativeRename"), systemImage: "pencil") {
                renameText = person.name
                renaming = true
            }
            Button(L("deletePersonLabel"), systemImage: "trash", role: .destructive) { confirmsDelete = true }
                .accessibilityIdentifier("person.delete")
        } label: {
            Image(systemName: "ellipsis")
        }
        .accessibilityLabel(L("nativeMore"))
        .accessibilityIdentifier("person.menu")
    }

    private func stats(_ person: Person) -> some View {
        Section {
            HStack {
                stat(person.conversationCount.map(String.init) ?? "–", L("conversations"))
                stat(person.talkSeconds.map(Formatting.talkTime) ?? "–", L("personTalkTime"))
                stat(person.lastHeardAt.map { $0.formatted(.relative(presentation: .named)) } ?? "–", L("personLastHeard"))
            }
        }
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(spacing: DS.Spacing.xxs) {
            Text(value).font(DS.Typography.cardTitle.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.7)
            Text(label).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private func samples(_ person: Person) -> some View {
        Section {
            if person.sampleURLs.isEmpty {
                Text(L("nativeNoVoiceSamples")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(Array(person.sampleURLs.enumerated()), id: \.element) { index, url in
                let id = url.absoluteString
                Button {
                    player.toggle(id, url: url)
                } label: {
                    HStack {
                        Image(systemName: player.playingID == id ? "stop.circle" : "play.circle")
                            .font(.title2)
                            .foregroundStyle(DS.Palette.ink)
                        Text(L("nativeSampleNumber", String(index + 1))).foregroundStyle(DS.Palette.ink)
                    }
                }
                .accessibilityLabel(player.playingID == id ? L("pausePlayback") : L("play"))
                .swipeActions {
                    Button(role: .destructive) { deletingSample = index } label: { Label(L("delete"), systemImage: "trash") }
                }
            }
        } header: {
            SettingsHeader(L("nativeVoiceProfile"))
        } footer: {
            Text(L("voiceSettingsSaveOthersSubtitle"))
        }
    }

    private var conversationSection: some View {
        Section(L("conversations")) {
            if conversations.isEmpty, loadFailed {
                Button(L("tryAgain")) { Task { await loadMore() } }
            } else if conversations.isEmpty, !hasMore {
                Text(L("noConversationsYet")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(conversations) { conversation in
                Button { onOpenConversation?(conversation) } label: {
                    HStack(spacing: DS.Spacing.md) {
                        EmojiBadge(conversation.emoji)
                        VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                            Text(conversation.title.isEmpty ? L("untitledConversation") : conversation.title)
                                .foregroundStyle(DS.Palette.ink)
                                .lineLimit(1)
                            Text(conversation.date.formatted(.dateTime.month(.abbreviated).day().hour().minute()))
                                .font(DS.Typography.caption)
                                .foregroundStyle(DS.Palette.inkSecondary)
                        }
                        Spacer(minLength: 0)
                        if onOpenConversation != nil {
                            Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
                        }
                    }
                }
                .disabled(onOpenConversation == nil)
                .accessibilityIdentifier("person.conversation")
                .onAppear { if conversation.id == conversations.last?.id { Task { await loadMore() } } }
            }
            if hasMore, !conversations.isEmpty { ProgressView().frame(maxWidth: .infinity) }
        }
    }

    private func loadMore() async {
        guard hasMore, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        guard let next = await settings.conversations(with: personID, page: page + 1) else {
            loadFailed = true
            return
        }
        loadFailed = false
        page += 1
        let known = Set(conversations.map(\.id))
        conversations += next.filter { !known.contains($0.id) }
        hasMore = next.count == 20
    }
}
