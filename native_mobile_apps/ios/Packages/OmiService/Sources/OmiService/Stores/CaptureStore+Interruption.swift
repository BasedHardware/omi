import Foundation
import OmiAudio
import OmiNetwork

/// Why phone capture is not running, when the reason came from outside the app.
public enum CaptureNotice: Equatable, Sendable {
    /// A call, Siri or another recorder has the microphone; `since` is when capture stopped.
    case microphoneTaken(since: Date)
    /// The audio route has no input at all (the microphone itself went away).
    case inputGone
}

@MainActor
extension CaptureStore {
    /// Watches the session for as long as the phone records. Only the phone: the Omi's audio arrives
    /// over Bluetooth and does not use the app's audio session.
    func startCaptureHealth() {
        guard source == .phone else { return }
        audioSession.start { [weak self] event in self?.handleAudioSession(event) }
        healthTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                try? await Task.sleep(for: self.healthTick)
                guard !Task.isCancelled, self.source == .phone, self.isLive else { return }
                // Either the system took the microphone, or the engine died without saying so.
                if self.suspendedBySystem || (!self.isPaused && !self.engine.isRunning) {
                    await self.takeMicrophoneBack()
                }
            }
        }
    }

    func stopCaptureHealth() {
        healthTask?.cancel()
        healthTask = nil
        audioSession.stop()
        notice = nil
        suspendedBySystem = false
    }

    /// What the phone capture does about one OS signal.
    func handleAudioSession(_ event: AudioSessionEvent) {
        guard source == .phone, isLive else { return }
        switch event {
        case .interrupted:
            log?.add(.warning, "capture", "microphone taken by a call or another app: capture paused")
            suspendCapture(.microphoneTaken(since: .now))
        case let .interruptionEnded(shouldResume):
            // Probing even without iOS's blessing: other apps' audio often ends without it, and
            // waiting for a signal that never comes left recordings stopped for good.
            log?.add(.info, "capture", "interruption ended (shouldResume: \(shouldResume))")
            Task { await takeMicrophoneBack() }
        case let .routeChanged(input):
            guard let input else {
                log?.add(.warning, "capture", "audio route has no input: capture paused")
                suspendCapture(.inputGone)
                return
            }
            log?.add(.info, "capture", "audio route is now \(input): rebuilding capture")
            Task { await takeMicrophoneBack() }
        case .mediaServicesReset:
            log?.add(.warning, "capture", "audio services were reset: rebuilding capture")
            Task { await takeMicrophoneBack() }
        case .appBecameActive:
            guard suspendedBySystem else { return }
            Task { await takeMicrophoneBack() }
        }
    }

    /// Pauses capture because the system took the microphone, keeping the recording alive: the
    /// socket, the file and the conversation all stay, and the health loop keeps asking for the mic.
    func suspendCapture(_ reason: CaptureNotice) {
        guard !suspendedBySystem, isLive else { return }
        suspendedBySystem = true
        notice = reason
        isPaused = true
        engine.stop()
        phoneTasks.forEach { $0.cancel() }
        phoneTasks = []
        level = 0
        if let partial { flushFinal(partial) }
    }

    /// Starts the phone microphone again, after the system stopped it or a route change pulled the
    /// tap out from under it.
    ///
    /// A failure here is not a failed recording: the words so far are already sent or on disk, so
    /// capture stays live, `notice` says why, and the health loop tries again.
    func takeMicrophoneBack() async {
        // One at a time: the OS event, the health loop and the user's own resume all ask for this,
        // and two overlapping starts would leave a second engine (and a second pipe) behind.
        guard source == .phone, isLive, !takingMicrophoneBack else { return }
        takingMicrophoneBack = true
        defer { takingMicrophoneBack = false }
        engine.stop()
        phoneTasks.forEach { $0.cancel() }
        phoneTasks = []
        do {
            let streams = try await engine.start(transcribeOnDevice: transcribesOnDevice && channel != nil)
            // Still wanted? The user may have paused (or stopped) while the microphone was starting
            // up; a pause is theirs to keep, so the fresh engine goes away again.
            guard source == .phone, isLive, suspendedBySystem || !isPaused else {
                engine.stop()
                return
            }
            suspendedBySystem = false
            isPaused = false
            notice = nil
            pipe(streams)
        } catch {
            suspendedBySystem = true
            isPaused = true
            if notice == nil { notice = .microphoneTaken(since: .now) }
            log?.add(.warning, "capture", "microphone not available yet (\(Self.describe(error))): still trying")
        }
    }

    /// Fails the live capture, and stops the health watch so nothing restarts the microphone after it.
    func fail(_ reason: String) {
        stopCaptureHealth()
        phase = .failed(reason)
        markEnded()
    }

    // MARK: A dropped phone socket

    /// The phone's socket dropped while the phone still records. The recording stays live: the
    /// audio of the gap goes to the phone's file (nothing is lost), and the socket is reopened
    /// with the same options and recording id, so the rest of the conversation is transcribed
    /// live again instead of waiting for an upload at the end.
    ///
    /// Without the options or a user to open a socket for, it falls back to the plain file
    /// recording (`connectionLost`), which is what the phone did before there was a reconnect.
    func phoneSocketLost() {
        guard source == .phone, case .live = phase, !reconnectingPhone, let options = listenOptionsInUse,
              let uid = userID() else {
            connectionLost()
            return
        }
        channel?.close(reason: "socket_lost")
        channel = nil
        beginBuffering(manual: false)
        recovery = .connectionLost
        reconnectingPhone = true
        log?.add(.warning, "stt", "phone socket lost: recording to the phone while reconnecting")
        tasks.append(Task { [weak self] in await self?.reopenPhoneSocket(uid: uid, options: options) })
    }

    private func reopenPhoneSocket(uid: String, options: ListenSocket.Options) async {
        var attempt = 0
        while true {
            try? await Task.sleep(for: phoneReconnectDelays[min(attempt, phoneReconnectDelays.count - 1)])
            attempt += 1
            guard stillReconnectingPhone else { return }
            guard let channel = try? await api.openListenSocket(uid: uid, options: options) else { continue }
            guard stillReconnectingPhone else {
                channel.close(reason: "user_stop")
                return
            }
            self.channel = channel
            reconnectingPhone = false
            // The file closes into the upload queue; the socket carries the recording from here.
            endBuffering()
            recovery = nil
            listen(to: channel, acceptServerSegments: transcriber == .omi)
            log?.add(.info, "stt", "phone socket reopened after \(attempt) attempt(s)")
            return
        }
    }

    /// The recording did not end (stop, user paused for good) while the phone's socket was away.
    private var stillReconnectingPhone: Bool {
        guard reconnectingPhone, source == .phone, case .live = phase, !Task.isCancelled else { return false }
        return true
    }
}

public extension CaptureStore {
    /// Clears the "the system stopped this" banner. The recording itself stays paused.
    func dismissNotice() {
        notice = nil
    }
}
