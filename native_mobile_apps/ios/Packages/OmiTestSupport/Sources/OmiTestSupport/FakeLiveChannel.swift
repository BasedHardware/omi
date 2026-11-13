import Foundation
import OmiCore
import OmiNetwork

/// Records what capture sends; tests push server events through `emit`.
public final class FakeLiveChannel: LiveTranscriptionChannel, @unchecked Sendable {
    public let events: AsyncStream<ListenEvent>
    private let continuation: AsyncStream<ListenEvent>.Continuation
    let lock = NSLock()
    public private(set) var audioBytes = 0
    public private(set) var audioMessages = 0
    public private(set) var suggested: [LiveSegment] = []
    /// `stt_provider` of each `suggested_transcript`.
    public private(set) var suggestedProviders: [String] = []
    public private(set) var closed = false
    public private(set) var closeReasons: [String] = []
    public internal(set) var speakerAssignments: [String] = [] // `speaker_assigned`, e.g. `1:p1:Anna:s1,s2`

    public init() {
        (events, continuation) = AsyncStream.makeStream(of: ListenEvent.self)
    }

    public func emit(_ event: ListenEvent) {
        continuation.yield(event)
    }

    public func send(audio: Data) {
        lock.withLock {
            audioBytes += audio.count
            audioMessages += 1
        }
    }

    public func sendSuggestedTranscript(_ segments: [LiveSegment], provider: String) {
        lock.withLock {
            suggested += segments
            suggestedProviders.append(provider)
        }
    }

    public func close(reason: String) {
        lock.withLock {
            closed = true
            closeReasons.append(reason)
        }
        continuation.finish()
    }
}
