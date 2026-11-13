import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Wire keys the backend stores for a "not helpful" rating (Flutter `FeedbackReason`).
private let feedbackReasons: [(key: String, label: String)] = [
    ("too_verbose", "feedbackReasonTooVerbose"),
    ("incorrect_or_hallucination", "feedbackReasonIncorrect"),
    ("not_helpful_or_irrelevant", "feedbackReasonNotHelpful"),
    ("didnt_follow_instructions", "feedbackReasonIgnoredInstructions"),
    ("other", "cancelReasonOther"),
]

/// An answer's long-press menu, everything Flutter's `MessageActionBar` offered and more, so the
/// thread carries no rows of icons: reply, copy, share, read aloud, the rating with its reasons,
/// and delete on this iPhone. `title` (when it was sent) heads the menu.
struct AnswerMenu: View {
    let message: ChatMessage
    let onReply: () -> Void
    let onDelete: () -> Void
    let title: String
    @Environment(ChatStore.self) private var chat
    @Environment(VoicePlaybackStore.self) private var voice

    var body: some View {
        Section(title) {
            Button(action: onReply) { Label(L("reply"), systemImage: "arrowshape.turn.up.left") }
            Button {
                UIPasteboard.general.string = message.text
                DSHaptics.success()
            } label: {
                Label(L("copy"), systemImage: "doc.on.doc")
            }
            ShareLink(item: message.text) { Label(L("share"), systemImage: "square.and.arrow.up") }
            readAloudButton
        }
        if message.serverID != nil {
            Section {
                Button { rate(message.rating == 1 ? 0 : 1) } label: {
                    Label(L("helpful"), systemImage: message.rating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
                }
                if message.rating == -1 {
                    Button { rate(0) } label: { Label(L("notHelpful"), systemImage: "hand.thumbsdown.fill") }
                } else {
                    Menu {
                        ForEach(feedbackReasons, id: \.key) { reason in
                            Button(L(reason.label)) { rate(-1, reason: reason.key) }
                        }
                    } label: {
                        Label(L("notHelpful"), systemImage: "hand.thumbsdown")
                    }
                }
            }
        }
        Button(action: onDelete) { Label(L("nativeChatHide"), systemImage: "eye.slash") }
    }

    /// Read aloud, or stop while this answer is being read.
    private var readAloudButton: some View {
        let playing = voice.playingID == message.id
        return Button {
            DSHaptics.selection()
            voice.toggle(message)
        } label: {
            Label(playing ? L("nativeStopReading") : L("nativeReadAloud"), systemImage: playing ? "stop.fill" : "speaker.wave.2")
        }
    }

    private func rate(_ value: Int, reason: String? = nil) {
        Task {
            if await chat.rate(message.id, value: value, reason: reason), value != 0 { DSHaptics.success() }
        }
    }
}
