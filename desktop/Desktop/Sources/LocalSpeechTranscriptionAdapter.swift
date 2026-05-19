import AVFoundation
import Foundation
import Speech

/// Live transcription using Apple's Speech framework (buffer-based recognition).
/// Emits consolidated segments compatible with `TranscriptionService.BackendSegment`.
final class LocalSpeechTranscriptionAdapter: @unchecked Sendable {

    /// Stable pseudo backend ID so SQLite upserts update the rolling transcript row.
    static let pseudoBackendSegmentId = "apple-hybrid-live"

    private let languageCode: String
    private let audioSerialQueue = DispatchQueue(label: "omi.hybrid.localspeech.audio")
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?

    /// Samples captured before authorization / task creation land here, then replay.
    private var pendingPCM = Data()

    private var terminated = false
    private let sessionWallClockBegin = CFAbsoluteTimeGetCurrent()

    init(languageCode: String) {
        self.languageCode = languageCode
    }

    /// Hybrid capability probe: whether Apple's Speech engine reports availability for the given assistant language code.
    static func isRecognitionEngineAvailable(forAssistantLanguageCode code: String) -> Bool {
        let primary = normalizedLocaleIdentifier(forAssistantLanguageCode: code)
        if let r = SFSpeechRecognizer(locale: Locale(identifier: primary)), r.isAvailable {
            return true
        }
        return SFSpeechRecognizer(locale: Locale(identifier: "en-US"))?.isAvailable == true
    }

    /// Uses the user's preferred macOS language list (fallback `en-US`).
    static func isRecognitionEngineAvailableForPreferredSystemLanguages() -> Bool {
        let code = Locale.preferredLanguages.first ?? "en-US"
        return isRecognitionEngineAvailable(forAssistantLanguageCode: code)
    }

    /// Normalize assistant language tokens (matches `effectiveTranscriptionLanguage`) to `Locale` identifiers Speech accepts.
    static func normalizedLocaleIdentifier(forAssistantLanguageCode code: String) -> String {
        let trimmed = code.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        switch lower {
        case "", "multi", "auto":
            return Locale.preferredLanguages.first ?? "en-US"
        case "zh", "cn":
            return "zh-CN"
        case _ where trimmed.contains("_"):
            let parts = trimmed.split(separator: "_", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { return lower }
            return bcp47Locale(language: parts[0], region: parts[1])
        case _ where trimmed.contains("-"):
            let parts = trimmed.split(separator: "-", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { return lower }
            return bcp47Locale(language: parts[0], region: parts[1])
        default:
            return "\(lower)-\(Locale.current.region?.identifier ?? "US")"
        }
    }

    private static func bcp47Locale(language: String, region: String) -> String {
        let lang = language.lowercased()
        let regionPart: String
        if region.count == 2, region == region.lowercased() {
            regionPart = region.lowercased()
        } else if region.count == 2 {
            regionPart = region.uppercased()
        } else {
            regionPart = region
        }
        return "\(lang)-\(regionPart)"
    }

    /// Start Speech authorization then begin buffer recognition. `onReady` runs when PCM may be appended.
    func start(
        onSegments: @escaping ([TranscriptionService.BackendSegment]) -> Void,
        onError: ((Error) -> Void)?,
        onReady: @escaping () -> Void
    ) {
        terminated = false
        pendingPCM = Data()

        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard let self else { return }
            switch status {
            case .authorized:
                self.audioSerialQueue.async {
                    self.beginRecognitionLocked(onSegments: onSegments, onError: onError, onReady: onReady)
                }
            case .denied, .restricted, .notDetermined:
                onError?(
                    TranscriptionService.TranscriptionError.webSocketError(
                        "Speech recognition authorization denied"))
            @unknown default:
                onError?(
                    TranscriptionService.TranscriptionError.webSocketError(
                        "Speech recognition authorization unavailable"))
            }
        }
    }

    /// Append microphone linear16 PCM (16 kHz, mono — same codec as `/v4/listen` streaming input).
    func appendLinear16PCMSamples(_ pcm: Data) {
        guard !pcm.isEmpty else { return }
        audioSerialQueue.async { [weak self] in
            guard let self, !self.terminated else { return }
            guard let rr = recognitionRequest else {
                self.pendingPCM.append(pcm)
                return
            }
            guard let buf = Self.makePCMBuffer(fromLinear16PCM: pcm) else { return }
            rr.append(buf)
        }
    }

    /// Tell Speech there will be no more audio (allows final results — used on PTT `finishStream` and on `stop`).
    func endAudioInput() {
        audioSerialQueue.async { [weak self] in
            guard let self, !self.terminated else { return }
            self.flushPendingPCMSamplesLocked()
            self.recognitionRequest?.endAudio()
        }
    }

    /// Tear down streaming recognition immediately.
    func cancel() {
        audioSerialQueue.async { [weak self] in
            guard let self else { return }
            self.terminated = true
            self.recognitionTask?.cancel()
            self.recognitionTask = nil
            self.recognitionRequest = nil
            self.pendingPCM = Data()
        }
    }

    // MARK: - Private

    private func beginRecognitionLocked(
        onSegments: @escaping ([TranscriptionService.BackendSegment]) -> Void,
        onError: ((Error) -> Void)?,
        onReady: @escaping () -> Void
    ) {
        terminated = false
        let localeIdentifier = Self.normalizedLocaleIdentifier(forAssistantLanguageCode: languageCode)
        let locale = Locale(identifier: localeIdentifier)
        guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
            DispatchQueue.main.async {
                onError?(
                    TranscriptionService.TranscriptionError.webSocketError(
                        "Speech recognition unavailable for locale \(localeIdentifier)"
                    ))
            }
            return
        }

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()

        guard let request = recognitionRequest else { return }

        request.shouldReportPartialResults = true
        request.taskHint = .dictation

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }

            self.audioSerialQueue.async {
                guard !self.terminated else { return }
                if let error {
                    DispatchQueue.main.async {
                        guard !self.terminated else { return }
                        onError?(
                            TranscriptionService.TranscriptionError.webSocketError(
                                error.localizedDescription))
                    }
                    return
                }

                guard let transcription = result?.bestTranscription else { return }
                let trimmed = transcription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmed.isEmpty else { return }

                let elapsedSeconds = CFAbsoluteTimeGetCurrent() - self.sessionWallClockBegin
                let segments = Self.makeHybridRollingSegments(text: trimmed, elapsedSeconds: elapsedSeconds)

                DispatchQueue.main.async {
                    onSegments(segments)
                }
            }
        }

        flushPendingPCMSamplesLocked()
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.terminated else { return }
            onReady()
        }
    }

    private func flushPendingPCMSamplesLocked() {
        guard let rr = recognitionRequest, !pendingPCM.isEmpty else { return }
        let chunk = pendingPCM
        pendingPCM = Data()
        guard let buf = Self.makePCMBuffer(fromLinear16PCM: chunk) else { return }
        rr.append(buf)
    }

    private static func makePCMBuffer(fromLinear16PCM pcm: Data) -> AVAudioPCMBuffer? {
        let frameCount = pcm.count / MemoryLayout<Int16>.size
        guard frameCount > 0 else { return nil }

        guard
            let format = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: 16_000,
                channels: 1,
                interleaved: false
            ),
            let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frameCount))
        else { return nil }

        buffer.frameLength = AVAudioFrameCount(frameCount)
        pcm.withUnsafeBytes { raw in
            guard let base = raw.baseAddress?.assumingMemoryBound(to: Int16.self),
                let channel = buffer.int16ChannelData?[0]
            else { return }
            channel.update(from: base, count: frameCount)
        }
        return buffer
    }

    /// Single rolling segment with a stable pseudo backend id — `TranscriptionStorage.upsertSegment` updates one row per session.
    static func makeHybridRollingSegments(text: String, elapsedSeconds: TimeInterval)
        -> [TranscriptionService.BackendSegment]
    {
        let end = max(0, elapsedSeconds)
        let seg = TranscriptionService.BackendSegment(
            id: pseudoBackendSegmentId,
            text: text,
            speaker: "SPEAKER_00",
            speaker_id: 0,
            is_user: true,
            person_id: nil,
            start: 0,
            end: end,
            translations: nil
        )
        return [seg]
    }
}
