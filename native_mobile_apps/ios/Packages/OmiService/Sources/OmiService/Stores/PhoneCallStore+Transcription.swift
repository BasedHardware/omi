import Foundation
import OmiNetwork

/// The call's transcription socket (Flutter `PhoneCallProvider._connectTranscriptionSocket` and
/// friends): opened when the call connects, both sides' audio as channel-tagged frames, frames
/// buffered while it reconnects (1 s, 2 s, 4 s … up to ten tries), a no-audio watchdog.
extension PhoneCallStore {
    func connectTranscription() {
        guard phase == .active, let callID else { return }
        guard let uid = userID() else {
            transcription = .failed
            return
        }
        reconnectTask?.cancel()
        reconnectTask = nil
        transcription = .connecting
        let callGeneration = generation
        let language = language()
        socketTask = Task { [weak self] in
            guard let self else { return }
            do {
                let channel = try await api.openPhoneCallSocket(uid: uid, callID: callID, language: language)
                guard callGeneration == generation, phase == .active else {
                    channel.close()
                    return
                }
                socket = channel
                reconnectAttempts = 0
                for await event in channel.events {
                    guard callGeneration == generation else { return }
                    received(event)
                }
            } catch {
                // Falls through to the reconnect below.
            }
            // Closed by the server or the network; our own close happens once the call is over.
            guard callGeneration == generation, phase == .active else { return }
            socket = nil
            scheduleReconnect()
        }
    }

    func received(_ event: PhoneCallSocketEvent) {
        if case .closed = event { return }
        if transcription != .active {
            transcription = .active
            socketAccepted = true
            armNoAudioWatchdog()
        }
        switch event {
        case let .segments(segments): transcript.merge(segments)
        case let .translations(translations): transcript.applyTranslations(translations)
        case .status, .closed: break
        }
    }

    func scheduleReconnect() {
        guard phase == .active else { return }
        guard reconnectAttempts < Self.maxReconnectAttempts else {
            transcription = .failed
            return
        }
        transcription = .reconnecting
        let delay = timing.reconnectBase * (1 << reconnectAttempts)
        reconnectAttempts += 1
        let callGeneration = generation
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard let self, !Task.isCancelled, callGeneration == generation, phase == .active else { return }
            connectTranscription()
        }
    }

    /// One side's audio as `[channel byte] + PCM16`, the backend's two-channel frame.
    func forward(_ audio: PhoneCallAudio) {
        guard isInProgress else { return }
        // Start-of-call only: the first frame disarms the watchdog for the rest of the call.
        watchdogTask?.cancel()
        watchdogTask = nil
        var frame = Data([audio.channel.rawValue])
        frame.append(audio.pcm16)
        guard let socket else {
            if pendingFrames.count < Self.maxPendingFrames { pendingFrames.append(frame) }
            return
        }
        for pending in pendingFrames {
            socket.send(frame: pending)
        }
        framesSent += pendingFrames.count + 1
        pendingFrames = []
        socket.send(frame: frame)
        if transcription == .noAudio { transcription = .active }
    }

    /// Armed once the server answered; says so when no call audio arrives.
    func armNoAudioWatchdog() {
        watchdogTask?.cancel()
        let timeout = timing.noAudioTimeout
        watchdogTask = Task { [weak self] in
            try? await Task.sleep(for: timeout)
            guard let self, !Task.isCancelled, phase == .active, socketAccepted, socket != nil, framesSent == 0 else { return }
            transcription = .noAudio
        }
    }

    func disconnectTranscription() {
        watchdogTask?.cancel()
        watchdogTask = nil
        reconnectTask?.cancel()
        reconnectTask = nil
        socketTask?.cancel()
        socketTask = nil
        reconnectAttempts = 0
        socket?.close()
        socket = nil
    }
}
