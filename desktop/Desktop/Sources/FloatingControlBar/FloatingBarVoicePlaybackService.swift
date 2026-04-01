import AVFoundation
import Foundation

@MainActor
final class FloatingBarVoicePlaybackService: NSObject {
    static let shared = FloatingBarVoicePlaybackService()

    static let devAPIKeyDefaultsKey = "dev_elevenlabs_api_key"
    static let devVoiceIDDefaultsKey = "dev_elevenlabs_voice_id"

    nonisolated private static let defaultVoiceID = "21m00Tcm4TlvDq8ikWAM"  // Rachel
    nonisolated private static let defaultModelID = "eleven_multilingual_v2"

    private var playbackTask: Task<Void, Never>?
    private var audioPlayer: AVAudioPlayer?
    private let speechSynthesizer = AVSpeechSynthesizer()

    private override init() {}

    func playResponseIfEnabled(_ message: ChatMessage?) {
        guard AnalyticsManager.isDevBuild else { return }
        guard ShortcutSettings.shared.floatingBarVoiceAnswersEnabled else { return }

        let text = Self.cleanedPlaybackText(from: message)
        guard !text.isEmpty, Self.shouldSpeak(text) else { return }

        let defaults = UserDefaults.standard
        guard let apiKey = defaults.string(forKey: Self.devAPIKeyDefaultsKey)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !apiKey.isEmpty else {
            playSystemFallback(text)
            return
        }

        let voiceID = defaults.string(forKey: Self.devVoiceIDDefaultsKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedVoiceID = (voiceID?.isEmpty == false) ? voiceID! : Self.defaultVoiceID

        stop()
        playbackTask = Task { [weak self] in
            do {
                let audioData = try await Self.synthesizeSpeech(text: text, apiKey: apiKey, voiceID: resolvedVoiceID)
                try Task.checkCancellation()
                await MainActor.run {
                    self?.startPlayback(audioData)
                }
            } catch is CancellationError {
            } catch {
                await MainActor.run {
                    log("FloatingBarVoicePlaybackService: ElevenLabs playback failed, falling back to system voice: \(error.localizedDescription)")
                    self?.playSystemFallback(text)
                }
            }
        }
    }

    func stop() {
        playbackTask?.cancel()
        playbackTask = nil
        audioPlayer?.stop()
        audioPlayer = nil
        speechSynthesizer.stopSpeaking(at: .immediate)
    }

    private func startPlayback(_ data: Data) {
        do {
            let player = try AVAudioPlayer(data: data)
            player.prepareToPlay()
            player.play()
            audioPlayer = player
        } catch {
            log("FloatingBarVoicePlaybackService: could not start audio playback: \(error.localizedDescription)")
        }
    }

    private func playSystemFallback(_ text: String) {
        speechSynthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: text)
        utterance.rate = 0.47
        utterance.pitchMultiplier = 1.02
        utterance.volume = 1.0
        utterance.voice = preferredSystemVoice()
        speechSynthesizer.speak(utterance)
    }

    private func preferredSystemVoice() -> AVSpeechSynthesisVoice? {
        let preferredNames = ["Samantha", "Karen", "Moira"]
        for name in preferredNames {
            if let voice = AVSpeechSynthesisVoice.speechVoices().first(where: { $0.name.localizedCaseInsensitiveContains(name) }) {
                return voice
            }
        }
        return AVSpeechSynthesisVoice(language: "en-US")
    }

    private nonisolated static func synthesizeSpeech(text: String, apiKey: String, voiceID: String) async throws -> Data {
        var request = URLRequest(url: URL(string: "https://api.elevenlabs.io/v1/text-to-speech/\(voiceID)")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("audio/mpeg", forHTTPHeaderField: "Accept")
        request.setValue(apiKey, forHTTPHeaderField: "xi-api-key")
        request.timeoutInterval = 45

        let body = ElevenLabsSpeechRequest(
            text: text,
            modelID: defaultModelID,
            outputFormat: "mp3_44100_128",
            voiceSettings: .init(
                stability: 0.42,
                similarityBoost: 0.82,
                style: 0.22,
                useSpeakerBoost: true
            )
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw FloatingBarVoicePlaybackError.invalidResponse
        }
        guard (200 ..< 300).contains(httpResponse.statusCode) else {
            let errorBody = String(data: data.prefix(300), encoding: .utf8) ?? "Unknown error"
            throw FloatingBarVoicePlaybackError.requestFailed(statusCode: httpResponse.statusCode, body: errorBody)
        }
        return data
    }

    private nonisolated static func cleanedPlaybackText(from message: ChatMessage?) -> String {
        guard let message else { return "" }

        let baseText: String
        if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            baseText = message.text
        } else {
            baseText = message.contentBlocks.compactMap { block in
                switch block {
                case .text(_, let text):
                    return text
                case .discoveryCard(_, let title, let summary, _):
                    return "\(title). \(summary)"
                case .toolCall, .thinking:
                    return nil
                }
            }.joined(separator: "\n\n")
        }

        let collapsedWhitespace = baseText.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        return collapsedWhitespace.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private nonisolated static func shouldSpeak(_ text: String) -> Bool {
        let lowercased = text.lowercased()
        if lowercased == "failed to get a response. please try again." {
            return false
        }
        if lowercased.hasPrefix("⚠️") || lowercased.hasPrefix("warning:") {
            return false
        }
        return true
    }
}

private struct ElevenLabsSpeechRequest: Encodable {
    let text: String
    let modelID: String
    let outputFormat: String
    let voiceSettings: ElevenLabsVoiceSettings

    enum CodingKeys: String, CodingKey {
        case text
        case modelID = "model_id"
        case outputFormat = "output_format"
        case voiceSettings = "voice_settings"
    }
}

private struct ElevenLabsVoiceSettings: Encodable {
    let stability: Double
    let similarityBoost: Double
    let style: Double
    let useSpeakerBoost: Bool

    enum CodingKeys: String, CodingKey {
        case stability
        case similarityBoost = "similarity_boost"
        case style
        case useSpeakerBoost = "use_speaker_boost"
    }
}

private enum FloatingBarVoicePlaybackError: LocalizedError {
    case invalidResponse
    case requestFailed(statusCode: Int, body: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid ElevenLabs response"
        case .requestFailed(let statusCode, let body):
            return "ElevenLabs request failed (\(statusCode)): \(body)"
        }
    }
}
