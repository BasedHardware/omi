import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence

/// When a conversation ends. The backend finalizes a conversation on its silence timeout while
/// its socket lives, and when the app asks (`POST v1/conversations`). It does not when a phone or
/// Omi socket closes, and a new socket (a new recording id) never resumes the old conversation.
/// So the app remembers the conversation its socket records into, and one still open at the next
/// start (the app was closed, the Omi or the socket went away) is finalized before the new socket
/// opens. A dropped Omi socket reopens with the same recording id, which resumes the same
/// conversation (Flutter's reconnect keeps its recording id), and the Omi's audio meanwhile is held
/// and sent first.
extension CaptureStore {
    // MARK: The open conversation

    func rememberOpenConversation(_ id: String) {
        preferences.set(id, for: .captureOpenConversation)
    }

    /// Forgets `id` (or whatever is remembered when `nil`); a different remembered id stays.
    func forgetOpenConversation(_ id: String? = nil) {
        guard id == nil || preferences.string(.captureOpenConversation) == id else { return }
        preferences.set(nil, for: .captureOpenConversation)
    }

    /// The end of a recording: finalizes its conversation (`POST v1/conversations`). When that
    /// fails it stays remembered and the next start finalizes it.
    func finalizeOpenConversation() async -> String? {
        do {
            let id = try await api.finalizeInProgressConversation()
            forgetOpenConversation()
            return id
        } catch {
            log?.add(.warning, "capture", "finalizing failed, retried at the next start: \(error)")
            return nil
        }
    }

    /// Finalizes the conversation an earlier socket left open, when it has words (or photos). An
    /// empty one is left to the backend, which deletes it.
    func finalizeLeftoverConversation() async {
        guard let id = preferences.string(.captureOpenConversation) else { return }
        let detail: ConversationDetail
        do {
            detail = try await api.conversationDetail(id: id)
        } catch APIError.http(404, _) {
            forgetOpenConversation(id)
            return
        } catch {
            log?.add(.warning, "capture", "open conversation not checked: \(error)")
            return
        }
        forgetOpenConversation(id)
        guard detail.conversation.status == .inProgress, !detail.transcript.isEmpty || !detail.photos.isEmpty else { return }
        do {
            try await finalizeLeftover(id)
        } catch {
            log?.add(.warning, "capture", "finalizing the open conversation failed, retried at the next start: \(error)")
            rememberOpenConversation(id)
            return
        }
        log?.add(.info, "capture", "finalized a conversation left open")
        await onConversationFinished?()
    }

    private func finalizeLeftover(_ id: String) async throws {
        do {
            try await api.finalizeConversation(id: id)
        } catch APIError.http(503, _) {
            // No durable finalization worker (a local backend). The in-progress endpoint finalizes
            // the newest conversation in progress: only while that is this one, never another.
            guard try await api.inProgressConversationID() == id else {
                log?.add(.warning, "capture", "the open conversation is not the newest in progress: left to the backend")
                return
            }
            _ = try await api.finalizeInProgressConversation()
        }
    }

    // MARK: Omi audio without a socket

    /// About eight minutes of opus; the oldest goes first beyond it.
    static let heldDeviceAudioLimit = 2_000_000

    /// Holds a frame while a socket is on its way (never while muted).
    func holdDeviceAudio(_ frame: Data) {
        guard !isDeviceMuted, phase == .starting || phase == .finishing || reconnectingDevice else { return }
        heldDeviceAudio.append(frame)
        heldDeviceAudioBytes += frame.count
        while heldDeviceAudioBytes > Self.heldDeviceAudioLimit, !heldDeviceAudio.isEmpty {
            heldDeviceAudioBytes -= heldDeviceAudio.removeFirst().count
        }
    }

    /// The socket is open: what was held goes first, in order.
    func sendHeldDeviceAudio() {
        let frames = heldDeviceAudio
        discardHeldDeviceAudio()
        for frame in frames {
            ingestDeviceAudio(frame)
        }
    }

    func discardHeldDeviceAudio() {
        heldDeviceAudio = []
        heldDeviceAudioBytes = 0
    }

    // MARK: A dropped Omi socket

    /// The Omi's socket dropped while the Omi still streams: reopen it with the same options (and
    /// recording id) until it opens or the recording ends.
    func deviceSocketLost() {
        guard source == .device, case .live = phase, !reconnectingDevice, let options = listenOptionsInUse,
              let uid = userID() else { return }
        channel?.close(reason: "socket_lost")
        channel = nil
        reconnectingDevice = true
        log?.add(.warning, "stt", "socket lost: reconnecting")
        tasks.append(Task { [weak self] in await self?.reopenDeviceSocket(uid: uid, options: options) })
    }

    private func reopenDeviceSocket(uid: String, options: ListenSocket.Options) async {
        var attempt = 0
        while true {
            try? await Task.sleep(for: deviceReconnectDelays[min(attempt, deviceReconnectDelays.count - 1)])
            attempt += 1
            guard stillReconnecting else { return }
            guard let channel = try? await api.openListenSocket(uid: uid, options: options) else { continue }
            guard stillReconnecting else {
                channel.close(reason: "user_stop")
                return
            }
            self.channel = channel
            reconnectingDevice = false
            listen(to: channel, acceptServerSegments: transcriber == .omi)
            sendHeldDeviceAudio()
            log?.add(.info, "stt", "socket reopened after \(attempt) attempt(s)")
            return
        }
    }

    /// The recording did not end (stop, Omi gone) while the socket was away.
    private var stillReconnecting: Bool {
        guard reconnectingDevice, source == .device, case .live = phase, !Task.isCancelled else { return false }
        return true
    }
}
