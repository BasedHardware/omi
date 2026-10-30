import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// After an update: the changes since the last version, then pending feature tours and messages,
/// one sheet at a time and never while recording (Flutter's announcement flow). The app shell adds
/// it once.
public struct WhatsNewPresenter: ViewModifier {
    @Environment(SettingsStore.self) private var settings
    @Environment(CaptureStore.self) private var capture
    @Environment(\.openURL) private var openURL
    @State private var store: AnnouncementsStore?
    /// `X.Y.Z+build`, the format the backend compares.
    let appVersion: String

    public init(appVersion: String) {
        self.appVersion = appVersion
    }

    public func body(content: Content) -> some View {
        content
            .task {
                let store = settings.makeAnnouncementsStore()
                self.store = store
                await store.checkAfterLaunch(appVersion: appVersion)
            }
            .sheet(item: Binding(
                get: { capture.isLive ? nil : store?.current },
                set: { if $0 == nil, store?.current != nil { store?.later() } }
            )) { item in
                AnnouncementSheet(
                    announcement: item,
                    onDone: { Task { await store?.dismiss() } },
                    onButton: { url in
                        Task { await store?.dismiss(buttonTapped: true) }
                        openURL(url)
                    },
                    onLater: { store?.later() }
                )
                .presentationDetents([.medium, .large])
                .presentationBackground(DS.Palette.background)
            }
    }
}

/// One announcement: a version's changes, a feature tour (one page per step) or a message.
struct AnnouncementSheet: View {
    let announcement: Announcement
    let onDone: () -> Void
    let onButton: (URL) -> Void
    let onLater: () -> Void

    var body: some View {
        NavigationStack {
            Group {
                switch announcement.kind {
                case let .changelog(version, changes):
                    SettingsList { ChangesSection(version: version ?? announcement.title, changes: changes) }
                case let .feature(steps):
                    TabView {
                        ForEach(steps) { step in
                            VStack(spacing: DS.Spacing.md) {
                                if let url = step.imageURL {
                                    AsyncImage(url: url) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                                        .frame(maxHeight: 220)
                                }
                                Text(step.title).font(DS.Typography.title).multilineTextAlignment(.center)
                                Text(step.text).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                                    .multilineTextAlignment(.center)
                            }
                            .padding(DS.Spacing.xl)
                        }
                    }
                    .tabViewStyle(.page)
                case let .message(body, imageURL, buttonTitle, buttonURL):
                    ScrollView {
                        VStack(spacing: DS.Spacing.md) {
                            if let imageURL {
                                AsyncImage(url: imageURL) { $0.resizable().scaledToFit() } placeholder: { Color.clear }
                                    .frame(maxHeight: 180)
                            }
                            Text(body).font(DS.Typography.body)
                            if let buttonTitle, let buttonURL {
                                Button(buttonTitle) { onButton(buttonURL) }.buttonStyle(.omiPrimary)
                            }
                        }
                        .padding(DS.Spacing.xl)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if case .message = announcement.kind {
                    ToolbarItem(placement: .cancellationAction) { Button(L("notNow"), action: onLater) }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("gotIt"), action: onDone).accessibilityIdentifier("whatsNew.done")
                }
            }
        }
    }

    private var title: String {
        if case let .changelog(version, _) = announcement.kind { return L("whatsNewInVersion", version ?? announcement.title) }
        return announcement.title
    }
}

/// One version's changes: emoji, title and description per row.
struct ChangesSection: View {
    let version: String
    let changes: [Announcement.Change]

    var body: some View {
        Section {
            ForEach(changes) { change in
                HStack(alignment: .top, spacing: DS.Spacing.md) {
                    Text(change.emoji ?? "✨").font(.title3)
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(change.title).font(DS.Typography.cardTitle)
                        Text(change.text).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                    }
                }
                .padding(.vertical, DS.Spacing.xxs)
            }
        } footer: {
            Text(L("versionLabel", version))
        }
    }
}

/// Settings › Help › What's new: the latest versions' changes.
struct WhatsNewScreen: View {
    @State private var store: AnnouncementsStore

    init(store: AnnouncementsStore) {
        _store = State(initialValue: store)
    }

    var body: some View {
        SettingsList {
            if store.recentFailed, store.recent.isEmpty {
                ContentUnavailableView {
                    Label(L("couldNotLoadWhatsNew"), systemImage: "sparkles")
                } actions: {
                    Button(L("tryAgain")) { Task { await store.loadRecent() } }
                }
            } else if store.recent.isEmpty {
                Text(L("nativeNothingNewYet")).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(store.recent) { item in
                if case let .changelog(version, changes) = item.kind {
                    ChangesSection(version: version ?? item.title, changes: changes)
                }
            }
        }
        .omiPage(L("whatsNew"))
        .task { await store.loadRecent() }
        .refreshable { await store.loadRecent() }
    }
}
