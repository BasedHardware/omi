import Foundation
import OmiNetwork

/// Where onboarding's live words come from: the iPhone's recognizer first, the server's
/// transcription-only socket when the iPhone cannot, and the watchdog's hand-over between them.
extension VoiceIntroStore {
    func startOnDevice() async -> Bool {
        guard let words = await recognizer.start(language: language) else {
            log.info("on-device recognition unavailable for \(self.language, privacy: .public)")
            return false
        }
        wordSource = .onDevice
        wordsTask = Task { [weak self] in
            for await segment in words {
                self?.merge([segment])
            }
        }
        return true
    }

    func startServer() async -> Bool {
        guard let channel = try? await api.openTranscribeStream(language: language) else {
            log.info("server transcription unavailable")
            return false
        }
        self.channel = channel
        wordSource = .server
        wordsTask = Task { [weak self] in
            for await event in channel.events {
                if case let .segments(new) = event { self?.merge(new) }
                if case let .status(status) = event, status == "stt_failed" || status.hasPrefix("disconnected") { break }
            }
            // The server stopped transcribing while we still listen: the other source takes over.
            guard let self, phase == .listening, self.channel === channel else { return }
            switchSource(failed: true)
        }
        return true
    }

    /// The current source produced no words for a while (or failed): try the other one, and
    /// replay the last seconds of audio into it. Over and back at most; after that the last
    /// source keeps listening (a working recognizer is never dropped for good), and only when
    /// none ever started do the sentences go by speech alone.
    func switchSource(failed: Bool = false) {
        guard !switching, wordSource != .none, phase == .listening else { return }
        speechWithoutWords = 0
        guard switches < Self.maximumSwitches else {
            // A source that failed outright cannot stay; a quiet one can.
            if failed { stopWords() }
            return
        }
        let from = wordSource
        log.notice("no words from \(String(describing: from), privacy: .public); switching")
        stopWords()
        switches += 1
        switching = true
        Task {
            defer { switching = false }
            let started = from == .onDevice ? await startServer() : await startOnDevice()
            guard started else { return }
            guard phase == .listening else { return stopWords() }
            replay(recent)
        }
    }

    func stopWords() {
        wordsTask?.cancel()
        wordsTask = nil
        channel?.close(reason: "onboarding")
        channel = nil
        recognizer.stop()
        wordSource = .none
        sourceGaveWords = false
    }

    func replay(_ audio: Data) {
        var offset = audio.startIndex
        while offset < audio.endIndex {
            let end = min(offset + 3200, audio.endIndex)
            send(audio.subdata(in: offset ..< end))
            offset = end
        }
    }

    func send(_ chunk: Data) {
        switch wordSource {
        case .onDevice: recognizer.feed(chunk)
        case .server: channel?.send(audio: chunk)
        case .none: break
        }
    }
}
