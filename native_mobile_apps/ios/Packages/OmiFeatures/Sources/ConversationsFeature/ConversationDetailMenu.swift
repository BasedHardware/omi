import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// The detail page's two toolbar buttons: Share (link, text, audio) and "…" (everything else).
extension ConversationDetailScreen {
    @ToolbarContentBuilder
    var toolbarItems: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Menu {
                Button { requestShareLink() } label: { Label(L("sharePublicLink"), systemImage: "link") }
                Button { shareText() } label: { Label(L("nativeShareAsText"), systemImage: "text.alignleft") }
                Button { extras.sharesBySMS = true } label: { Label(L("shareViaSms"), systemImage: "message") }
                if store.detail?.hasAudio == true {
                    Button { shareAudio() } label: { Label(L("shareAudio"), systemImage: "waveform") }
                }
            } label: {
                Image(systemName: "square.and.arrow.up")
            }
            .accessibilityLabel(L("share"))
            .accessibilityIdentifier("conversation.share")
        }
        ToolbarItem(placement: .topBarTrailing) {
            Menu { menuItems } label: { Image(systemName: "ellipsis") }
                .accessibilityIdentifier("conversation.menu")
        }
    }

    @ViewBuilder
    private var menuItems: some View {
        Button { askOmi() } label: { Label(L("nativeAskOmiAboutThis"), systemImage: "sparkles") }
        if store.detail?.transcript.isEmpty == false {
            Button {
                withAnimation(DS.Motion.standard) {
                    page = .transcript
                    searchesTranscript = true
                }
            } label: { Label(L("nativeSearchTranscript"), systemImage: "magnifyingglass") }
        }
        Section {
            Button { Task { await conversations.setStarred(conversation.id, !conversation.isStarred) } } label: {
                conversation.isStarred
                    ? Label(L("unstarConversation"), systemImage: "star.slash")
                    : Label(L("starConversation"), systemImage: "star")
            }
            Button { moving = true } label: { Label(L("moveToFolder"), systemImage: "folder") }
            Button {
                newTitle = conversation.title
                renaming = true
            } label: { Label(L("renameConversation"), systemImage: "pencil") }
        }
        Section {
            Button { reprocess() } label: { Label(L("reprocessConversation"), systemImage: "arrow.clockwise") }
                .disabled(store.isReprocessing || conversation.status == .processing)
            extraMenuItems
            Button { copy(store.summaryText, notice: L("summaryCopiedToClipboard")) } label: {
                Label(L("copySummary"), systemImage: "doc.on.doc")
            }
            Button { copy(store.detail?.transcriptText ?? "", notice: L("transcriptCopiedToClipboard")) } label: {
                Label(L("copyTranscript"), systemImage: "text.quote")
            }
            .disabled(store.detail?.transcript.isEmpty ?? true)
            if developer.showsConversationTools {
                Button { copy(conversation.id, notice: L("nativeConversationIDCopied")) } label: {
                    Label(L("nativeCopyConversationID"), systemImage: "number")
                }
                Button { extras.testsPrompt = true } label: { Label(L("testPrompt"), systemImage: "text.badge.checkmark") }
            }
            if conversation.visibility != .private {
                Button { Task { await conversations.setVisibility(conversation.id, .private) } } label: {
                    Label(L("makePrivate"), systemImage: "lock")
                }
            }
        }
        Button(role: .destructive) {
            // No dialog: Home shows "Conversation deleted · Undo" for a few seconds.
            let id = conversation.id
            dismiss()
            conversations.deleteWithUndo([id])
        } label: {
            Label(L("deleteConversation"), systemImage: "trash")
        }
    }

    func reprocess() {
        DSHaptics.tap()
        Task { await store.reprocess(in: conversations) }
    }

    /// Points the chat at this conversation, then the shell opens it.
    func askOmi() {
        chat.context = ChatContext(
            kind: .conversation, id: conversation.id,
            title: conversation.title.isEmpty ? L("untitledConversation") : conversation.title
        )
        onAskOmi()
    }

    func copy(_ text: String, notice: String) {
        guard !text.isEmpty else { return }
        #if canImport(UIKit)
            UIPasteboard.general.string = text
        #endif
        DSHaptics.success()
        show(notice)
    }

    func show(_ message: String) {
        notice = message
        Task {
            try? await Task.sleep(for: .seconds(2))
            if notice == message { notice = nil }
        }
    }

    // MARK: Sharing

    /// A private conversation asks first ("Anyone with the link can view").
    func requestShareLink() {
        if conversation.visibility == .private {
            confirmsShareLink = true
        } else {
            Task { await shareLink() }
        }
    }

    /// Makes the link work, opens the share sheet, and goes back to private if nothing was shared.
    func shareLink() async {
        let id = conversation.id
        let wasPrivate = conversation.visibility == .private
        if wasPrivate, await !(conversations.setVisibility(id, .shared)) {
            show(L("conversationUrlNotShared"))
            return
        }
        let list = conversations
        sharing = ShareRequest(items: [Conversation.shareURL(id: id)]) { shared in
            if wasPrivate, !shared { Task { await list.setVisibility(id, .private) } }
        }
    }

    func shareText() {
        let text = [conversation.title, store.summaryText].filter { !$0.isEmpty }.joined(separator: "\n\n")
        sharing = ShareRequest(items: [text])
    }

    func shareAudio() {
        Task {
            if store.audio == .idle {
                show(L("preparingAudio"))
                await store.loadAudio()
            }
            guard let file = await store.exportAudio() else { return show(L("audioDownloadFailed")) }
            sharing = ShareRequest(items: [file])
        }
    }

    @ViewBuilder
    func shareSheet(_ request: ShareRequest) -> some View {
        #if canImport(UIKit)
            ShareSheet(request: request).presentationDetents([.medium, .large]).ignoresSafeArea()
        #else
            EmptyView()
        #endif
    }
}
