import Foundation
import OmiNetwork
import OmiPersistence

/// Where phone audio goes when it cannot be streamed (the app: `SyncStore`, which keeps the file
/// across relaunches and uploads it to `v2/sync-local-files`).
@MainActor
public protocol PhoneAudioBuffering: AnyObject {
    /// Opens a file. `manual`: Transcribe later, uploaded only when the user asks.
    func beginPhoneAudio(manual: Bool)
    func appendPhoneAudio(_ pcm: Data)
    /// Closes the file; it joins the upload queue.
    func endPhoneAudio()
    /// Store audio on phone: a copy of what streams live, kept on the phone and never uploaded.
    func beginKeptCopy(_ source: KeptAudioSource)
    /// PCM16 from the phone, or one opus packet from the Omi.
    func appendKeptCopy(_ audio: Data)
    func endKeptCopy()
}

/// A recording that did not end the way it was meant to (Flutter `capture_recovery_banner`).
public enum CaptureRecovery: Equatable, Sendable {
    /// The app was closed while recording (crash, or iOS ended it). What reached the server or
    /// the phone is kept.
    case interrupted(since: Date)
    /// The connection dropped mid-recording: the rest was kept on the phone and uploads when
    /// the recording ends (or once the phone is online).
    case connectionLost
}

extension CaptureStore {
    /// The listen options every source shares: the server model and the developer VAD gate.
    func listenOptions(_ options: ListenSocket.Options) -> ListenSocket.Options {
        var options = options
        options.sttService = usesParakeet ? "parakeet" : nil
        options.vadGate = preferences.bool(.vadGateEnabled, default: false)
        return options
    }

    /// Live from now; the mark survives until the recording ends, so a relaunch can tell. Only
    /// the iPhone microphone loses audio when the app is closed: an Omi keeps recording to its own
    /// storage and syncs it on reconnect, so its recordings set no mark (no false alarm on every
    /// relaunch of an always-on wearable).
    func setLive() {
        phase = .live(since: .now)
        let mark = source == .device ? nil : String(Date.now.timeIntervalSince1970)
        preferences.set(mark, for: .captureActiveSince)
        log?.add(.info, "capture", "recording started (\(String(describing: source ?? .phone)))")
        startCaptureHealth()
    }

    func markEnded() {
        preferences.set(nil, for: .captureActiveSince)
    }

    static func recoveredInterruption(_ preferences: Preferences) -> CaptureRecovery? {
        guard let since = preferences.string(.captureActiveSince).flatMap(Double.init) else { return nil }
        preferences.set(nil, for: .captureActiveSince)
        return .interrupted(since: Date(timeIntervalSince1970: since))
    }

    func beginBuffering(manual: Bool) {
        guard !isBuffering, let phoneBuffer else { return }
        phoneBuffer.beginPhoneAudio(manual: manual)
        isBuffering = true
        log?.add(.info, "capture", manual ? "recording to the phone (transcribe later)" : "recording to the phone (offline)")
    }

    func endBuffering() {
        guard isBuffering else { return }
        phoneBuffer?.endPhoneAudio()
        isBuffering = false
    }

    /// The socket dropped while the phone mic records: keep going into a file.
    func connectionLost() {
        channel = nil
        beginBuffering(manual: false)
        recovery = .connectionLost
    }

    func routePhoneAudio(_ chunk: Data) {
        guard source == .phone else { return }
        if keepsCopy { phoneBuffer?.appendKeptCopy(chunk) }
        if isBuffering {
            phoneBuffer?.appendPhoneAudio(chunk)
        } else {
            channel?.send(audio: chunk)
            customTranscriber?.feed(chunk)
        }
    }
}

public extension CaptureStore {
    func dismissRecovery() {
        recovery = nil
    }
}
