import Foundation
import SwiftWhisper

/// Local Whisper wrapper. Default uses bundled `ggml-tiny.en` like FriendManager.
public final class OmiWhisperTranscriber {
    private let whisper: Whisper?

    public init(modelURL: URL? = nil) {
        let url = modelURL ?? Bundle.module.url(forResource: "ggml-tiny.en", withExtension: "bin")
        if let url {
            whisper = Whisper(fromFileURL: url)
        } else {
            whisper = nil
        }
    }

    public func transcribe(audioFrames: [Float]) async throws -> String {
        guard let whisper else {
            throw NSError(domain: "omi.stt.whisper", code: 1, userInfo: [NSLocalizedDescriptionKey: "Whisper model not loaded"])
        }
        let segments = try await whisper.transcribe(audioFrames: audioFrames)
        return segments.map(\.text).joined()
    }
}
