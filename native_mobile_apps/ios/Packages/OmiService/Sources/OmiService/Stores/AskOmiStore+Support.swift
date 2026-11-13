import Foundation
import OmiAudio
import OmiDevice
import OmiNetwork

/// Ask Omi's helpers: the question's words from a recognizer that already runs, the Omi's frames
/// as PCM for the recognizer, and a wait that always ends.
extension AskOmiStore {
    /// The capture already transcribes the Omi on the iPhone: the question is what its line says
    /// after the press (the rest of a line that was running, then the new ones).
    func readShared(from baseline: LiveSegment?) {
        recognition = .shared
        let session = session
        let before = baseline.map { Self.words($0.text).count } ?? 0
        wordsTask = Task { [weak self] in
            while let self, self.session == session {
                if var line = sharedLine()?.line {
                    if line.id == baseline?.id {
                        let words = Self.words(line.text)
                        line = LiveSegment(
                            id: line.id, text: words.dropFirst(before).joined(separator: " "), speaker: line.speaker,
                            speakerID: line.speakerID, isUser: line.isUser, start: line.start, end: line.end
                        )
                    }
                    merge(line)
                }
                try? await Task.sleep(for: .milliseconds(150))
            }
        }
    }

    static func words(_ text: String) -> [Substring] {
        text.split(whereSeparator: \.isWhitespace)
    }

    /// The recognizer re-sends a line while it grows (same id) and starts a new id per utterance.
    func merge(_ segment: LiveSegment) {
        guard !segment.text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        if let index = segments.firstIndex(where: { $0.id == segment.id }) {
            guard segments[index].text != segment.text else { return }
            segments[index] = segment
        } else {
            segments.append(segment)
        }
        question = segments.map(\.text).joined(separator: " ")
        lastWordsAt = .now
    }

    /// The answer, or nil when it did not come in time (the request is cancelled then).
    func within(
        _ limit: Duration, _ work: @escaping @MainActor () async -> ChatStore.VoiceAnswer
    ) async -> ChatStore.VoiceAnswer? {
        await withCheckedContinuation { continuation in
            let once = Once()
            let job = Task { @MainActor in
                let answer = await work()
                if once.claim() { continuation.resume(returning: answer) }
            }
            Task { @MainActor in
                try? await Task.sleep(for: limit)
                guard once.claim() else { return }
                job.cancel()
                continuation.resume(returning: nil)
            }
        }
    }

    /// The Omi's frames as 16 kHz PCM16 for the recognizer; nil for a codec it cannot use.
    public nonisolated static func pcmDecoder(_ codec: OmiGATT.Codec) -> ((Data) -> Data?)? {
        switch codec {
        case .opus, .opusFS320:
            guard let decoder = try? OpusFrameDecoder() else { return nil }
            return { frame in decoder.decode(frame).map(PCM16.data(from:)) }
        case .pcm16:
            return { $0 }
        case .pcm8:
            return nil
        }
    }
}

/// Lets exactly one of two racing tasks finish a continuation.
@MainActor
private final class Once {
    private var claimed = false

    func claim() -> Bool {
        defer { claimed = true }
        return !claimed
    }
}

/// A recognizer that already listens to the Omi: its newest line (nil while it has none yet).
public struct SharedLine: Sendable {
    public let line: LiveSegment?

    public init(line: LiveSegment?) {
        self.line = line
    }
}
