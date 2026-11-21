import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// The summary's extras inside "More details": which app wrote it, the linked calendar event,
/// "Was this helpful?" and what was on screen.
struct SummaryExtrasSection: View {
    let store: ConversationDetailStore
    let extras: DetailExtras

    var body: some View {
        if let appID = store.detail?.summaryAppID {
            attribution(appID)
        }
        if let event = store.detail?.calendarEvent {
            LinkedEventCard(event: event) { extras.showsEvent = true }
        }
        if let feedback = extras.feedback { SummaryFeedbackRow(feedback: feedback) }
        if let screenshots = extras.screenshots, !screenshots.screenshots.isEmpty {
            ScreenshotsStrip(screenshots: screenshots)
        }
    }

    /// "Summarized by <app>"; tapping it opens the summary templates.
    private func attribution(_ appID: String) -> some View {
        Button { extras.showsTemplates = true } label: {
            Label(L("nativeSummarizedBy", extras.templates?.app(appID)?.name ?? L("unknownApp")), systemImage: "square.grid.2x2")
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkSecondary)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("summary.attribution")
    }
}

/// Creates and loads what the extras need (summary feedback, screenshots, the summarizing app's
/// name) once the conversation has loaded, whether or not "More details" is open.
struct SummaryExtrasLoader: ViewModifier {
    let store: ConversationDetailStore
    let extras: DetailExtras
    @Environment(ConversationsStore.self) private var conversations

    func body(content: Content) -> some View {
        content
            .task(id: store.phase) {
                guard store.phase == .loaded, let detail = store.detail else { return }
                if extras.feedback == nil {
                    let feedback = conversations.makeFeedbackStore(conversationID: detail.conversation.id)
                    extras.feedback = feedback
                    // Only Omi's own summary asks about a summary, a finished recording with audio about
                    // the recording; a discarded conversation never asks.
                    let kept = !detail.conversation.isDiscarded
                    feedback.start(
                        hasOwnSummary: kept && detail.summaryAppID == nil && !detail.summary.isEmpty,
                        hasRecording: kept && detail.conversation.status == .completed && detail.hasAudio
                    )
                }
                if extras.screenshots == nil, detail.conversation.status == .completed, !detail.conversation.isDiscarded {
                    let screenshots = conversations.makeScreenshotsStore(conversationID: detail.conversation.id)
                    extras.screenshots = screenshots
                    await screenshots.load()
                }
            }
            .task(id: store.detail?.summaryAppID) {
                // The app's name for the attribution line.
                if store.detail?.summaryAppID != nil { await extras.templates(conversations).load(conversationID: store.conversation.id) }
            }
    }
}

/// "You + 2 others": who took part. Opens the linked calendar event, if any.
struct ParticipantsRow: View {
    let store: ConversationDetailStore
    let onOpenEvent: () -> Void
    @Environment(SettingsStore.self) private var settings

    var body: some View {
        if let detail = store.detail {
            let people = detail.participants(you: L("you")) { id in settings.people.first { $0.id == id }?.name }
            if !people.isEmpty {
                let content = Label(Self.label(people), systemImage: people.names.count > 1 || people.others > 0 ? "person.2" : "person")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .lineLimit(1)
                if detail.calendarEvent != nil {
                    Button(action: onOpenEvent) { content }.buttonStyle(.plain)
                } else {
                    content.accessibilityElement(children: .combine)
                }
            }
        }
    }

    /// One name; "Anna + 2 others"; "Anna + others" when Omi could not count.
    static func label(_ people: Participants) -> String {
        guard let first = people.names.first else { return "" }
        if people.uncounted { return L("participantsSummaryUncounted", first) }
        switch people.others {
        case ..<1: return first
        case 1: return L("nativeParticipantsOneOther", first)
        default: return L("nativeParticipantsOthers", first, String(people.others))
        }
    }
}

/// A thin running bar and "Processing conversation…" under the title while Omi works on it; the
/// page reloads every few seconds until it is done (Flutter `conversation_activity_strip`).
struct ProcessingStrip: View {
    let store: ConversationDetailStore
    let conversation: Conversation
    @Environment(ConversationsStore.self) private var conversations

    var body: some View {
        Group {
            if store.isReprocessing || conversation.status == .processing {
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    ProgressView().progressViewStyle(.linear).tint(DS.Palette.agent)
                    Text(store.isReprocessing ? L("reprocessingConversationProgress") : L("processingConversationProgress"))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                .transition(.opacity)
                .accessibilityElement(children: .combine)
            }
        }
        .task(id: conversation.status) {
            if conversation.status == .processing, !store.isReprocessing { await store.followProcessing(in: conversations) }
        }
    }
}

/// Photos taken during the conversation, three across; Omi is still describing the ones with a
/// spinner, discarded ones are dimmed. Tap for the full picture and its description.
struct ConversationPhotosGrid: View {
    let store: ConversationDetailStore
    @State private var opened: ConversationPhoto?

    var body: some View {
        if let photos = store.detail?.photos, !photos.isEmpty {
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: DS.Spacing.xs), count: 3), spacing: DS.Spacing.xs) {
                ForEach(photos) { photo in
                    Button { opened = photo } label: {
                        Color.clear
                            .aspectRatio(4 / 3, contentMode: .fit)
                            .overlay { RemoteImage { await store.image(for: photo) } }
                            .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                            .opacity(photo.isDiscarded ? 0.4 : 1)
                            .overlay {
                                if photo.isDescribing { ProgressView().controlSize(.small) }
                                if photo.isDiscarded { Image(systemName: "eye.slash").foregroundStyle(DS.Palette.inkSecondary) }
                            }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(photo.description ?? L("nativePhoto"))
                }
            }
            .sheet(item: $opened) { photo in
                ImageViewer(caption: photo.description) { await store.image(for: photo) }
                    .presentationDetents([.medium, .large])
            }
        }
    }
}

/// "What was on screen": a meeting's screenshots in a row with their captions. Tap to open,
/// long-press to delete.
struct ScreenshotsStrip: View {
    let screenshots: ConversationScreenshotsStore
    @State private var opened: ConversationScreenshot?
    @State private var deleting: ConversationScreenshot?

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text(L("meetingScreenshotsTitle")).font(DS.Typography.sectionTitle)
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: DS.Spacing.sm) {
                    ForEach(screenshots.screenshots) { shot in
                        Button { opened = shot } label: {
                            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                                Color.clear
                                    .frame(width: 144, height: 90)
                                    .overlay { RemoteImage { await Self.load(shot.thumbnailURL ?? shot.imageURL) } }
                                    .clipShape(RoundedRectangle(cornerRadius: DS.Radius.sm, style: .continuous))
                                Text(caption(shot))
                                    .font(DS.Typography.caption)
                                    .foregroundStyle(DS.Palette.inkSecondary)
                                    .lineLimit(2)
                                    .frame(width: 144, alignment: .leading)
                            }
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button { opened = shot } label: { Label(L("open"), systemImage: "arrow.up.left.and.arrow.down.right") }
                            Button(role: .destructive) { deleting = shot } label: { Label(L("delete"), systemImage: "trash") }
                        }
                    }
                }
            }
            .scrollIndicators(.hidden)
        }
        .sheet(item: $opened) { shot in
            ImageViewer(caption: caption(shot)) { await Self.load(shot.imageURL ?? shot.thumbnailURL) }
                .presentationDetents([.medium, .large])
        }
        .alert(
            L("deleteMeetingScreenshotTitle"),
            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
            presenting: deleting
        ) { shot in
            Button(L("cancel"), role: .cancel) {}
            Button(L("delete"), role: .destructive) { Task { await screenshots.delete(shot) } }
        } message: { _ in
            Text(L("deleteMeetingScreenshotMessage"))
        }
    }

    private func caption(_ shot: ConversationScreenshot) -> String {
        shot.caption.isEmpty ? L("meetingScreenshotFallbackCaption") : shot.caption
    }

    /// Signed URLs load without auth headers.
    static func load(_ url: URL?) async -> Data? {
        guard let url else { return nil }
        return try? await URLSession.shared.data(from: url).0
    }
}

/// An image from bytes loaded on demand, a quiet tile meanwhile.
struct RemoteImage: View {
    let load: () async -> Data?
    /// Shows the whole picture instead of filling the frame.
    var fits = false
    @State private var data: Data?
    @State private var loaded = false

    var body: some View {
        ZStack {
            DS.Palette.cardRaised
            #if canImport(UIKit)
                if let data, let image = UIImage(data: data) {
                    Image(uiImage: image).resizable().aspectRatio(contentMode: fits ? .fit : .fill)
                } else if loaded {
                    Image(systemName: "photo").foregroundStyle(DS.Palette.inkTertiary)
                }
            #endif
        }
        .task {
            data = await load()
            loaded = true
        }
    }
}

/// One picture, full width, with its caption.
struct ImageViewer: View {
    let caption: String?
    let load: () async -> Data?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: DS.Spacing.md) {
                    Color.clear
                        .aspectRatio(4 / 3, contentMode: .fit)
                        .overlay { RemoteImage(load: load, fits: true) }
                        .clipShape(RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
                    if let caption, !caption.isEmpty {
                        Text(caption).font(DS.Typography.body).foregroundStyle(DS.Palette.inkSecondary)
                    }
                }
                .padding(DS.Spacing.gutter)
            }
            .background(DS.Palette.background)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } } }
        }
    }
}
