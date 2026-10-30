import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The "…" menu's entries for the newer actions, next to Reprocess.
extension ConversationDetailScreen {
    @ViewBuilder
    var extraMenuItems: some View {
        if !conversation.isDiscarded {
            Button { extras.showsTemplates = true } label: {
                Label(L("summaryTemplate"), systemImage: "square.grid.2x2")
            }
            .disabled(store.isReprocessing || conversation.status == .processing)
        }
        if store.detail?.calendarEvent == nil {
            Button { extras.linkEvent(store) } label: { Label(L("linkEvent"), systemImage: "calendar.badge.plus") }
        }
        if let recordings = store.detail?.recordings, !recordings.isEmpty {
            Button { extras.showsRecordings = true } label: {
                Label(L("nativeRecordingsCount", String(recordings.count)), systemImage: "square.stack.3d.up")
            }
        }
        // Where it happened is not on the page any more (the conversation map has it); it stays one tap away here.
        if let place = store.detail?.conversation.location ?? conversation.location {
            Link(destination: PlaceLinks.maps(place)) {
                Label(place.shortAddress.map { L("nativeOpenPlaceInMaps", $0) } ?? L("nativeOpenInMaps"), systemImage: "map")
            }
        }
    }

    /// "Send to my AI": the conversation as clean Markdown (title, date, summary, action items,
    /// transcript with times, link) in the share sheet, ready for Claude, ChatGPT or notes.
    func sendToMyAI() {
        let detail = store.detail
        let canonical = tasks.tasks(forConversation: conversation.id)
        let items: [ConversationDigest.ActionItemLine] = canonical.isEmpty
            ? (detail?.summaryActionItems ?? []).map { .init($0) }
            : canonical.map { .init($0.description, isDone: $0.isCompleted) }
        let export = ConversationDigest.Export(
            title: conversation.displayTitle,
            date: conversation.date,
            duration: conversation.duration,
            summary: detail?.summary ?? conversation.overview,
            actionItems: items,
            transcript: detail?.transcript ?? [],
            link: Conversation.shareURL(id: conversation.id)
        )
        let markdown = ConversationDigest.markdown(
            export,
            labels: .init(
                summary: L("summary"), actionItems: L("nativeActionItems"), transcript: L("transcript"), link: L("nativeLink")
            )
        )
        DSHaptics.tap()
        sharing = ShareRequest(items: [markdown])
    }
}
