import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// Omi's answers read aloud with the backend voice (`POST v2/tts/synthesize`), as Flutter's
/// `OmiVoicePlaybackService`: finished answers on their own when the reply mode allows (in the chat
/// and for questions asked with the Omi's button), any answer from its speaker button, the voice
/// preview in Settings › Assistant and the spoken-reply preview in onboarding.
@MainActor
@Observable
public final class VoicePlaybackStore {
    /// Settings › Assistant › Spoken replies (Flutter `voiceResponseMode`).
    public enum ReplyMode: Int, Sendable { case off = 0, headphonesOnly = 1, always = 2 }

    /// What is playing: a message id, or `preview:<voice>`.
    public private(set) var playingID: String?
    /// Waiting for the first audio.
    public private(set) var isLoading = false
    /// The last preview could not be played (no system-voice stand-in for a voice preview).
    public private(set) var previewFailed = false

    private let api: any APIClientProtocol
    private let preferences: Preferences
    private let player: any SpeechAudioPlaying
    private let headphonesConnected: @MainActor () -> Bool
    private var task: Task<Void, Never>?
    /// One request stays well under the backend's 5,000 characters, and short first audio starts sooner.
    static let chunkLimit = 600

    public init(
        api: any APIClientProtocol,
        preferences: Preferences,
        player: any SpeechAudioPlaying = SystemSpeechPlayer(),
        headphonesConnected: @escaping @MainActor () -> Bool = { AudioRoute.isPrivate }
    ) {
        self.api = api
        self.preferences = preferences
        self.player = player
        self.headphonesConnected = headphonesConnected
    }

    public var replyMode: ReplyMode {
        ReplyMode(rawValue: preferences.integer(.voiceResponseMode, default: 1)) ?? .headphonesOnly
    }

    /// The same preference as Settings › Assistant › Spoken replies.
    public func setReplyMode(_ mode: ReplyMode) {
        preferences.set(mode.rawValue, for: .voiceResponseMode)
    }

    /// Off never speaks, headphones only speaks into private listening (AirPods, wired, CarPlay is not private).
    public static func readsAloud(mode: ReplyMode, headphones: Bool) -> Bool {
        switch mode {
        case .off: false
        case .headphonesOnly: headphones
        case .always: true
        }
    }

    /// A finished answer arrived (chat on screen, or a question from the Omi's button). Returns
    /// whether it is being read aloud; an answer already playing is not started twice.
    @discardableResult
    public func answerArrived(_ message: ChatMessage) -> Bool {
        if playingID == message.id { return true }
        guard Self.isSpeakable(message), Self.readsAloud(mode: replyMode, headphones: headphonesConnected()) else { return false }
        play(message)
        return true
    }

    /// What `previewReply` plays under.
    public static let replyPreviewID = "preview:reply"

    /// Onboarding's spoken-reply preview: `text` in the chosen voice whatever the reply mode, with
    /// the system voice standing in when the backend voice is unavailable (Flutter `playPreview`).
    public func previewReply(_ text: String) {
        if playingID == Self.replyPreviewID { return stop() }
        start(id: Self.replyPreviewID, text: Self.speakableText(text), voiceID: nil, systemFallback: true)
    }

    /// The speaker button: plays this answer, or stops it when it is the one playing.
    public func toggle(_ message: ChatMessage) {
        if playingID == message.id {
            stop()
        } else if Self.isSpeakable(message) {
            play(message)
        }
    }

    /// Settings › Assistant: a sample in `voiceID`, or stop when that preview is playing.
    public func preview(voiceID: String, sample: String) {
        let id = "preview:\(voiceID)"
        if playingID == id { return stop() }
        previewFailed = false
        start(id: id, text: sample, voiceID: voiceID, systemFallback: false)
    }

    public func stop() {
        task?.cancel()
        task = nil
        player.stop()
        playingID = nil
        isLoading = false
    }

    private func play(_ message: ChatMessage) {
        start(id: message.id, text: Self.speakableText(message.text), voiceID: nil, systemFallback: true)
    }

    private func start(id: String, text: String, voiceID: String?, systemFallback: Bool) {
        stop()
        let chunks = Self.chunks(text)
        guard !chunks.isEmpty else { return }
        playingID = id
        isLoading = true
        task = Task { [weak self] in
            guard let self else { return }
            await speak(chunks, voiceID: voiceID, systemFallback: systemFallback)
            guard !Task.isCancelled else { return }
            playingID = nil
            isLoading = false
        }
    }

    /// Fetches the next piece while the current one plays. When the backend voice is unavailable
    /// (quota, rate limit, offline) the rest of an answer is read by the system voice.
    private func speak(_ chunks: [String], voiceID: String?, systemFallback: Bool) async {
        let api = api
        var next: Task<Data, any Error>? = Task { try await api.synthesizeSpeech(text: chunks[0], voiceID: voiceID) }
        defer { next?.cancel() }
        for index in chunks.indices {
            guard let pending = next, !Task.isCancelled else { return }
            let audio: Data
            do {
                audio = try await pending.value
            } catch {
                guard !Task.isCancelled else { return }
                isLoading = false
                if systemFallback {
                    await player.speak(chunks[index...].joined(separator: " "))
                } else {
                    previewFailed = true
                }
                return
            }
            guard !Task.isCancelled else { return }
            let following = index + 1
            next = following < chunks.count ? Task { try await api.synthesizeSpeech(text: chunks[following], voiceID: voiceID) } : nil
            isLoading = false
            do {
                try await player.play(audio)
            } catch {
                if systemFallback { await player.speak(chunks[index...].joined(separator: " ")) }
                return
            }
        }
    }

    static func isSpeakable(_ message: ChatMessage) -> Bool {
        message.sender == .omi && message.failure == nil && !message.isServiceFailure
            && !speakableText(message.text).isEmpty
    }

    /// The words of a Markdown answer: no code, link targets, URLs or emphasis markers (Flutter
    /// `_cleanedPlaybackText`).
    public static func speakableText(_ markdown: String) -> String {
        var text = markdown
        let rules: [(String, String)] = [
            ("```[\\s\\S]*?```", " "),
            ("`[^`]*`", " "),
            ("\\[([^\\]]+)\\]\\([^)]+\\)", "$1"),
            ("https?://\\S+", " "),
            ("\\*\\*|__", ""),
            ("(?<!\\*)\\*(?!\\*)", ""),
            ("(?m)^\\s*(#+|>|[-•]\\s)", " "),
            ("\\|", " "),
            ("\\s+", " "),
        ]
        for (pattern, template) in rules {
            text = text.replacingOccurrences(of: pattern, with: template, options: .regularExpression)
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Sentence-sized pieces of at most `limit` characters.
    static func chunks(_ text: String, limit: Int = chunkLimit) -> [String] {
        var chunks: [String] = []
        var current = ""
        text.enumerateSubstrings(in: text.startIndex..., options: .bySentences) { sentence, _, _, _ in
            guard let sentence = sentence?.trimmingCharacters(in: .whitespaces), !sentence.isEmpty else { return }
            if !current.isEmpty, current.count + sentence.count + 1 > limit {
                chunks.append(current)
                current = ""
            }
            var rest = Substring(sentence)
            while rest.count > limit {
                chunks.append(String(rest.prefix(limit)))
                rest = rest.dropFirst(limit)
            }
            current = current.isEmpty ? String(rest) : current + " " + rest
        }
        if !current.isEmpty { chunks.append(current) }
        return chunks
    }
}
