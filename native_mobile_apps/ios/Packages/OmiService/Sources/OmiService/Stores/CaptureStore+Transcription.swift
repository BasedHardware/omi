import Foundation
import OmiAudio
import OmiNetwork
import OmiPersistence

/// Who transcribes a live recording.
public enum Transcriber: Equatable, Sendable {
    /// Omi's servers (the managed transcription the plan's minutes pay for).
    case omi
    /// The iPhone's own recognizer: the user chose it, or the plan's minutes are used up.
    case iPhone
    /// The user's own provider (its name).
    case custom(String)
}

/// Something about this recording's transcription the person should know (Flutter's freemium
/// threshold and its on-device switch).
public enum TranscriptionNotice: Equatable, Sendable {
    /// The plan's transcription minutes run out soon (Flutter shows Plus users the plans).
    case minutesRunningLow(seconds: Int)
    /// The minutes are used up: the iPhone transcribes instead (Flutter "Switched to on-device").
    case switchedToIPhone
    /// Transcription is not allowed on this account right now: the audio is kept on the phone.
    case recordingOnly
}

/// Which transcriber a recording starts with, the plan's fallback when its minutes run out, the
/// backend's translations, and Store audio on phone. An extension in its own file; the state it
/// needs is internal in `CaptureStore.swift`.
extension CaptureStore {
    /// What the iPhone's recognizer hears from the Omi right now (the live preview, or on-device
    /// transcription). Ask Omi reads a question from it instead of starting a second recognizer
    /// on the same audio. Nil while the iPhone does not listen to the Omi.
    public var iPhoneLineFromOmi: SharedLine? {
        guard isLive, source == .device, deviceFeed != nil else { return nil }
        return SharedLine(line: previewOnly ? preview : partial ?? segments.last)
    }

    enum Plan: Equatable {
        case omi
        case iPhone
        case custom(CustomSTTConfig)
        /// Record to a file on the phone, transcribe when asked (Transcribe later, or nothing may transcribe).
        case later
    }

    /// The order Flutter's `SttModeResolver` uses: Transcribe later, the user's own provider, then the
    /// plan (`transcription_allowance`): `on_device` falls back to the iPhone (always available on
    /// iOS, so no billed socket opens), `blocked` keeps the audio on the phone. `opus`: the source can
    /// feed the iPhone and custom providers (the phone mic always can).
    func transcriptionPlan(laterRequested: Bool, opus: Bool) -> Plan {
        if laterRequested { return .later }
        if opus, let config = customSTT?.config, config.isComplete, makeCustomTranscriber != nil { return .custom(config) }
        switch transcriptionAllowance {
        case .onDevice where opus:
            transcriptionNotice = .switchedToIPhone
            log?.add(.info, "stt", "no transcription minutes left: the iPhone transcribes")
            return .iPhone
        case .blocked where source == .phone && phoneBuffer != nil:
            transcriptionNotice = .recordingOnly
            log?.add(.warning, "stt", "transcription not available on this plan: recording to the phone")
            return .later
        default:
            return transcribesOnDevice && opus ? .iPhone : .omi
        }
    }

    /// The phone engine for a plan. The plan's own switch to the iPhone needs speech permission;
    /// without it the recording still runs on Omi's socket (the audio is kept, the transcript waits).
    func startPhoneStreams(_ plan: inout Plan) async throws -> PhoneCaptureStreams {
        do {
            return try await startPhoneEngine(onDevice: plan == .iPhone, preview: plan == .omi)
        } catch where plan == .iPhone && !transcribesOnDevice {
            engine.stop()
            plan = .omi
            transcriptionNotice = .minutesRunningLow(seconds: 0)
            return try await startPhoneEngine(onDevice: false, preview: false)
        }
    }

    /// The live session is on: the chosen transcriber starts, and the plan is checked again for the
    /// next recording.
    func beginTranscriber(_ plan: Plan) {
        switch plan {
        case .omi, .later: transcriber = .omi
        case .iPhone: transcriber = .iPhone
        case let .custom(config):
            guard let transcriber = makeCustomTranscriber?(config) else { return }
            customTranscriber = transcriber
            self.transcriber = .custom(transcriber.providerName)
            let name = transcriber.providerName
            tasks.append(Task { [weak self] in
                for await segment in transcriber.start() {
                    self?.upsert(segment)
                    self?.channel?.sendSuggestedTranscript([segment], provider: name)
                }
            })
        }
        Task { await refreshTranscriptionAllowance() }
    }

    func endTranscriber() {
        customTranscriber?.stop()
        customTranscriber = nil
        opusToPCM = nil
    }

    // MARK: Plan

    /// The backend's last word on who may transcribe (kept across launches, Flutter's
    /// `TranscriptionAllowanceCache`): a failed refresh does not put an account without minutes
    /// back on Omi's transcription.
    var transcriptionAllowance: TranscriptionAllowance? {
        guard let text = preferences.string(.transcriptionAllowanceLastKnown),
              let object = (try? JSONSerialization.jsonObject(with: Data(text.utf8))) as? [String: Any] else { return nil }
        return (object["mode"] as? String).flatMap(TranscriptionAllowance.init(rawValue:))
    }

    func setTranscriptionAllowance(_ allowance: TranscriptionAllowance?) {
        let text = allowance.flatMap { try? JSONSerialization.data(withJSONObject: ["mode": $0.rawValue]) }
            .flatMap { String(data: $0, encoding: .utf8) }
        preferences.set(text, for: .transcriptionAllowanceLastKnown)
    }

    /// `GET v1/users/me/subscription`. A backend without `transcription_allowance` still says when the
    /// minutes are used up (the managed socket then sends no transcript at all).
    public func refreshTranscriptionAllowance() async {
        guard let subscription = try? await api.subscription() else { return }
        setTranscriptionAllowance(subscription.transcriptionAllowance ?? (subscription.isOutOfMinutes ? .onDevice : .managed))
    }

    /// `freemium_threshold_reached`: low (a notice) or out (`remaining` 0, the iPhone takes over).
    func freemiumThresholdReached(remainingSeconds: Int, requiresOnDevice: Bool) async {
        log?.add(.warning, "stt", "transcription minutes: \(remainingSeconds) s left")
        guard remainingSeconds <= 0, requiresOnDevice else {
            transcriptionNotice = .minutesRunningLow(seconds: remainingSeconds)
            return
        }
        setTranscriptionAllowance(.onDevice)
        await switchToIPhoneTranscription()
    }

    /// Mid-recording: the iPhone's recognizer, already running as the live preview, becomes the
    /// transcript, and the socket reopens with `custom_stt` (the conversation stays open on the
    /// server until its silence timeout, so nothing is finalized).
    func switchToIPhoneTranscription() async {
        guard case .live = phase, transcriber == .omi, previewOnly, var options = listenOptionsInUse, let uid = userID() else {
            if transcriber == .omi { transcriptionNotice = .minutesRunningLow(seconds: 0) }
            return
        }
        previewOnly = false
        transcriber = .iPhone
        transcriptionNotice = .switchedToIPhone
        log?.add(.info, "stt", "no transcription minutes left: switching to the iPhone")
        channel?.close(reason: "retry")
        channel = nil
        options.clientTranscription = true
        do {
            let channel = try await api.openListenSocket(uid: uid, options: options)
            guard case .live = phase else {
                channel.close(reason: "user_stop")
                return
            }
            self.channel = channel
            listenOptionsInUse = options
            listen(to: channel, acceptServerSegments: false)
        } catch {
            log?.add(.warning, "stt", "listen socket failed: \(error)")
            if source == .phone, phoneBuffer != nil { connectionLost() }
        }
    }

    // MARK: Translation

    /// `translating`: the backend's translations join the segments already shown (by id).
    func applyTranslations(_ incoming: [LiveSegment]) {
        for segment in incoming where !segment.translations.isEmpty {
            guard let index = segments.firstIndex(where: { $0.id == segment.id }) else { continue }
            segments[index].translations = segment.translations
        }
    }

    // MARK: Store audio on phone

    /// Settings › Privacy › Store audio on phone (Flutter `unlimitedLocalStorageEnabled`): every
    /// recording also stays on the phone, not only the ones that could not be sent.
    var keepsAudioOnPhone: Bool {
        preferences.bool(.unlimitedLocalStorageEnabled)
    }

    func beginKeptCopy(_ source: KeptAudioSource) {
        guard keepsAudioOnPhone, !keepsCopy, let phoneBuffer else { return }
        phoneBuffer.beginKeptCopy(source)
        keepsCopy = true
    }

    func endKeptCopy() {
        guard keepsCopy else { return }
        keepsCopy = false
        phoneBuffer?.endKeptCopy()
    }
}
