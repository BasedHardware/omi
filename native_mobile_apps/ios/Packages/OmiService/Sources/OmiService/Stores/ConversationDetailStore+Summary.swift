import Foundation
import OmiCore
import OmiNetwork

/// Why the summary on screen could not be saved. The screen turns each case into words.
public enum SummaryEditFailure: Equatable, Sendable {
    /// The conversation has no result from that app any more (`app_result_not_found`).
    case appResultGone
    /// More than one result from that app, so the backend cannot tell which one to edit
    /// (`app_result_ambiguous`).
    case appResultAmbiguous
    /// The conversation itself is gone: it was deleted while its summary was open.
    case conversationGone
    /// The device could not reach Omi.
    case offline
    /// Nobody is signed in.
    case signedOut
    /// Any other refusal, with the HTTP status when the response had one.
    case refused(status: Int?)
}

/// What one attempt at editing the summary did.
public enum SummaryEditOutcome: Equatable, Sendable {
    case saved
    /// Nothing was sent: the text is empty, it is what the summary already shows, or the summary
    /// cannot be edited.
    case unchanged
    case failed(SummaryEditFailure)
}

public extension ConversationDetailStore {
    /// Whether the summary on screen can be edited in place: Omi's own summary, or an app's result
    /// that carries the app id the PATCH addresses. A result from an app that sent no id stays
    /// read-only, because the request could not name it.
    var canEditSummary: Bool {
        guard let detail else { return false }
        return detail.summaryIsOmiOwn || detail.summaryAppID != nil
    }

    /// Edits the summary in place (`PATCH v1/conversations/{id}/summary`): the new text shows at
    /// once and the old one comes back when the backend refuses. Editing Omi's own summary drops
    /// the generated sections on the backend, so the gist goes with them.
    @discardableResult
    func editSummary(_ text: String) async -> SummaryEditOutcome {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let detail, !text.isEmpty, text != detail.summary, canEditSummary else { return .unchanged }
        let appID = detail.summaryIsOmiOwn ? nil : detail.summaryAppID
        let previous = (summary: detail.summary, gist: detail.gist)
        self.detail?.summary = text
        if appID == nil { self.detail?.gist = nil }
        do {
            try await api.updateConversationSummary(conversationID: conversation.id, appID: appID, content: text)
            return .saved
        } catch {
            self.detail?.summary = previous.summary
            self.detail?.gist = previous.gist
            return .failed(SummaryEditFailure(error, editingAppResult: appID != nil))
        }
    }
}

extension SummaryEditFailure {
    /// `editingAppResult` tells the backend's two 404s apart: it answers 404 both when the app's
    /// result is gone ("App summary not found for this conversation") and when the conversation
    /// itself is ("Conversation not found").
    init(_ error: any Error, editingAppResult: Bool) {
        switch error {
        case APIError.http(let status, let body) where status == 409 || body.contains("app_result_ambiguous"):
            self = .appResultAmbiguous
        case APIError.http(let status, let body) where status == 404 || body.contains("app_result_not_found"):
            self = editingAppResult ? .appResultGone : .conversationGone
        case APIError.http(let status, _):
            self = .refused(status: status)
        case APIError.transport:
            self = .offline
        case APIError.notSignedIn:
            self = .signedOut
        default:
            self = .refused(status: nil)
        }
    }
}
