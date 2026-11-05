import Foundation
import Observation
import OmiCore
import OmiNetwork

/// One conversation's summary, transcript and recording. Created per detail screen; changes that
/// concern the whole conversation (star, folder, delete) go through `ConversationsStore`.
@MainActor
@Observable
public final class ConversationDetailStore {
    public enum Phase: Equatable, Sendable { case loading, loaded, failed(String) }

    public enum AudioState: Equatable, Sendable {
        /// Not asked for yet (no recording, or the transcript tab was never opened).
        case idle
        case preparing
        case ready(URL, duration: TimeInterval?)
        case unavailable
    }

    public private(set) var phase: Phase = .loading
    public internal(set) var detail: ConversationDetail?
    public private(set) var isReprocessing = false
    public private(set) var audio: AudioState = .idle
    /// Shown immediately from the list while the detail loads.
    public let preview: Conversation

    let api: any APIClientProtocol

    public init(preview: Conversation, api: any APIClientProtocol) {
        self.preview = preview
        self.api = api
    }

    public var conversation: Conversation {
        detail?.conversation ?? preview
    }

    public func load() async {
        do {
            detail = try await api.conversationDetail(id: preview.id)
            phase = .loaded
        } catch {
            phase = .failed(String(describing: error))
        }
    }

    /// Summarizes again through the list (which shows "processing" meanwhile), with one summary
    /// app when `appID` is given. Returns success.
    @discardableResult
    public func reprocess(in list: ConversationsStore, appID: String? = nil) async -> Bool {
        guard !isReprocessing else { return false }
        isReprocessing = true
        defer { isReprocessing = false }
        guard let fresh = await list.reprocess(conversation.id, appID: appID) else { return false }
        detail = fresh
        return true
    }

    /// Optimistic edit of one transcript line; the old words come back if the backend refuses.
    @discardableResult
    public func editLine(_ lineID: ConversationDetail.Line.ID, text: String) async -> Bool {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let index = detail?.transcript.firstIndex(where: { $0.id == lineID }),
              let line = detail?.transcript[index], let segmentID = line.segmentID, line.text != text else { return false }
        detail?.transcript[index].text = text
        do {
            try await api.editTranscriptSegment(conversationID: conversation.id, segmentID: segmentID, text: text)
            return true
        } catch {
            if let index = detail?.transcript.firstIndex(where: { $0.id == lineID }) { detail?.transcript[index].text = line.text }
            return false
        }
    }

    /// Finds the recording's playback file, waiting while the backend builds it (`attempts` polls).
    public func loadAudio(attempts: Int = 6) async {
        guard detail?.hasAudio == true, audio == .idle || audio == .unavailable else { return }
        audio = .preparing
        // Asks the backend to build the playback files (Flutter does this when the page opens).
        try? await api.precacheConversationAudio(id: conversation.id)
        for _ in 0 ..< max(1, attempts) {
            switch try? await api.conversationAudio(id: conversation.id) {
            case let .ready(url, duration):
                audio = .ready(url, duration: duration)
                return
            case let .parts(parts):
                // Several parts: downloaded and joined into one file that plays and shares as one.
                if let joined = await AudioJoiner.join(ordered(parts), name: audioFileName) {
                    audio = .ready(joined, duration: parts.reduce(0) { $0 + $1.duration })
                } else {
                    audio = .unavailable
                }
                return
            case let .pending(retryAfter):
                try? await Task.sleep(for: .seconds(min(max(retryAfter, 0), 5)))
                if Task.isCancelled {
                    audio = .idle
                    return
                }
            case .unavailable, nil:
                audio = .unavailable
                return
            }
        }
        audio = .unavailable
    }

    /// Downloads the recording to a temporary file for the share sheet (parts are joined already).
    public func exportAudio() async -> URL? {
        guard case let .ready(remote, _) = audio else { return nil }
        if remote.isFileURL { return remote }
        guard let (downloaded, response) = try? await URLSession.shared.download(from: remote) else { return nil }
        let ext = response.mimeType == "audio/mpeg" || remote.pathExtension == "mp3" ? "mp3" : "wav"
        let target = FileManager.default.temporaryDirectory.appending(path: "\(audioFileName).\(ext)")
        try? FileManager.default.removeItem(at: target)
        do {
            try FileManager.default.moveItem(at: downloaded, to: target)
            return target
        } catch {
            return nil
        }
    }

    /// The file name shared audio gets: the title, else "Omi".
    var audioFileName: String {
        (conversation.title.isEmpty ? "Omi" : conversation.title).replacingOccurrences(of: "/", with: "-")
    }

    /// Parts by when they started (`audio_files[].started_at`), unknown starts last.
    func ordered(_ parts: [AudioPart]) -> [AudioPart] {
        let starts = Dictionary((detail?.audioParts ?? []).map { ($0.id, $0.startedAt) }, uniquingKeysWith: { first, _ in first })
        return parts.enumerated().sorted { lhs, rhs in
            switch (starts[lhs.element.id] ?? nil, starts[rhs.element.id] ?? nil) {
            case let (left?, right?) where left != right: left < right
            case (.some, nil): true
            case (nil, .some): false
            default: lhs.offset < rhs.offset
            }
        }
        .map(\.element)
    }

    /// The summary as plain Markdown: summary, key points, other apps' results (copy and share).
    public var summaryText: String {
        guard let detail else { return conversation.overview }
        var parts = [detail.summary]
        if !detail.keyPoints.isEmpty { parts.append(detail.keyPoints.map { "- \($0)" }.joined(separator: "\n")) }
        parts += detail.otherSummaries.map(\.content)
        return parts.filter { !$0.isEmpty }.joined(separator: "\n\n")
    }
}
