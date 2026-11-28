@preconcurrency import AVFoundation
import OSLog
@preconcurrency import Speech

/// Apple speech recognition on the captured audio, for Omi's on-device transcription mode
/// (`custom_stt=enabled` on the listen socket: the client sends `suggested_transcript`).
/// Recognition tasks are rolled every ~50 s because Apple caps a single request near one minute.
public final class OnDeviceTranscriber: @unchecked Sendable {
    public struct Segment: Sendable, Equatable {
        public let id: String
        public let text: String
        public let start: Double
        public let end: Double
        public let isFinal: Bool
    }

    public enum TranscriberError: Error { case notAuthorized, unavailable }

    private let recognizer: SFSpeechRecognizer
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var segmentStart: Double = 0
    private var segmentIndex = 0
    private var elapsed: Double = 0
    private let lock = NSLock()
    private var continuation: AsyncStream<Segment>.Continuation?
    /// Strictly on-device first; Apple's server recognizer if the device has no model for the
    /// language (e.g. assets not downloaded).
    private var prefersOnDevice = true
    /// Set by `stop()`: a request that ends on its own is no longer replaced.
    private var stopped = false
    /// Requests that failed in a row without a word; a few are replaced, then recognition rests.
    private var failuresInARow = 0
    static let maximumFailuresInARow = 4
    private let log = Logger(subsystem: "com.omi.native", category: "transcriber")

    public init?(locale: Locale = .current) {
        guard let recognizer = SFSpeechRecognizer(locale: locale) ?? SFSpeechRecognizer(locale: Locale(identifier: "en-US")) else {
            return nil
        }
        self.recognizer = recognizer
    }

    /// For the language the user speaks (`de`, `en-GB`, …), not the iPhone's own: a German
    /// recognizer hearing English is slow and wrong. Nil when Apple has no recognizer for it.
    public convenience init?(language: String) {
        guard let locale = Self.locale(for: language) else { return nil }
        self.init(locale: locale)
    }

    /// A supported locale for a language code: the exact one, else the iPhone's region for that
    /// language (`de` on a Swiss iPhone is `de-CH`), else the usual region, else any.
    public static func locale(
        for language: String,
        supported: Set<Locale> = SFSpeechRecognizer.supportedLocales(),
        region: String? = Locale.current.region?.identifier
    ) -> Locale? {
        let wanted = language.replacingOccurrences(of: "_", with: "-")
        let ids = supported.map { $0.identifier.replacingOccurrences(of: "_", with: "-") }.sorted()
        if let exact = ids.first(where: { $0.caseInsensitiveCompare(wanted) == .orderedSame }) { return Locale(identifier: exact) }
        let base = String(wanted.split(separator: "-").first ?? Substring(wanted)).lowercased()
        let same = ids.filter { $0.lowercased() == base || $0.lowercased().hasPrefix(base + "-") }
        if let region, let local = same.first(where: { $0.uppercased().hasSuffix("-" + region.uppercased()) }) {
            return Locale(identifier: local)
        }
        let usual = ["en": "en-US", "de": "de-DE", "es": "es-ES", "fr": "fr-FR", "pt": "pt-BR", "it": "it-IT", "nl": "nl-NL"][base]
        if let usual, same.contains(usual) { return Locale(identifier: usual) }
        return same.first.map { Locale(identifier: $0) }
    }

    public static func requestAuthorization() async -> Bool {
        await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
    }

    /// Feeds buffers in, yields segments out (partial ones repeat the same id until final).
    public func transcribe(_ buffers: AsyncStream<AVAudioPCMBuffer>) -> AsyncStream<Segment> {
        let (stream, continuation) = AsyncStream.makeStream(of: Segment.self)
        self.continuation = continuation
        // The buffer stream has exactly one consumer: this task.
        let input = UncheckedBox(buffers)
        Task.detached { [self, input, continuation] in
            startRequest()
            for await buffer in input.value {
                let seconds = Double(buffer.frameLength) / buffer.format.sampleRate
                let (shouldRoll, current) = lock.withLock { () -> (Bool, SFSpeechAudioBufferRecognitionRequest?) in
                    elapsed += seconds
                    return (elapsed - segmentStart > 50, request)
                }
                current?.append(buffer)
                if shouldRoll { rollRequest() }
            }
            lock.withLock { request?.endAudio() }
            try? await Task.sleep(for: .seconds(1.5))
            continuation.finish()
        }
        return stream
    }

    public func stop() {
        lock.withLock {
            stopped = true
            request?.endAudio()
            task?.finish()
        }
    }

    /// Ends the current request and starts a fresh one: what is said from now on arrives under a
    /// new segment id (onboarding: one per sentence).
    public func startNewUtterance() {
        rollRequest()
    }

    private func rollRequest() {
        lock.withLock { request?.endAudio() }
        startRequest()
    }

    private func startRequest() {
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        let onDevice = lock.withLock { prefersOnDevice } && recognizer.supportsOnDeviceRecognition
        request.requiresOnDeviceRecognition = onDevice
        let (start, index) = lock.withLock { () -> (Double, Int) in
            segmentStart = elapsed
            segmentIndex += 1
            self.request = request
            return (elapsed, segmentIndex)
        }
        let id = "ondevice-\(UUID().uuidString.prefix(8))-\(index)"
        let continuation = continuation
        let parts = PartsBox(start: start)
        let task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let error, result == nil {
                log.error("recognition failed (onDevice=\(onDevice)): \(error.localizedDescription, privacy: .public)")
                let canFallBack = lock.withLock { () -> Bool in
                    guard onDevice, prefersOnDevice, self.request === request else { return false }
                    prefersOnDevice = false
                    return true
                }
                if canFallBack {
                    startRequest()
                } else {
                    // "No speech detected" and the like end the request: listen on with a new one.
                    continueListening(after: request, failed: true)
                }
                return
            }
            guard let result else { return }
            let text = result.bestTranscription.formattedString
            if !text.isEmpty {
                let end = lock.withLock { () -> Double in
                    failuresInARow = 0
                    return elapsed
                }
                // A part starts when its words do: the capture lines the server's words up by time.
                let (part, partStart) = parts.next(text, endsUtterance: result.speechRecognitionMetadata != nil, now: end)
                let partID = part == 0 ? id : "\(id).\(part)"
                continuation?.yield(Segment(id: partID, text: text, start: partStart, end: end, isFinal: result.isFinal))
            }
            // A request ends after a long pause (or its own limit) while the user may go on talking.
            if result.isFinal { continueListening(after: request, failed: false) }
        }
        lock.withLock { self.task = task }
    }

    /// The current request ended by itself: start the next one unless recognition was stopped,
    /// rolled over already, or keeps failing.
    private func continueListening(after ended: SFSpeechAudioBufferRecognitionRequest, failed: Bool) {
        let restart = lock.withLock { () -> Bool in
            guard !stopped, request === ended else { return false }
            if failed { failuresInARow += 1 }
            return failuresInARow <= Self.maximumFailuresInARow
        }
        guard restart else { return }
        if failed {
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.3) { [weak self] in
                guard let self, lock.withLock({ !self.stopped && self.request === ended }) else { return }
                startRequest()
            }
        } else {
            startRequest()
        }
    }
}

/// Apple's recognizer keeps one request running across pauses, but after a pause its text can
/// start over with only the new words (the result before it carries `speechRecognitionMetadata`).
/// Each restart becomes a new part with its own segment id, so what was said before is kept
/// instead of replaced by the next sentence.
public struct UtteranceParts: Sendable {
    public private(set) var part = 0
    private var last: [String] = []
    private var ended = false

    public init() {}

    /// The part `text` belongs to.
    public mutating func next(_ text: String, endsUtterance: Bool) -> Int {
        let words = Self.words(text)
        if !last.isEmpty, ended || Self.startsOver(previous: last, next: words) { part += 1 }
        ended = endsUtterance
        last = words
        return part
    }

    /// A revision keeps the start of the line and its length; a restart is shorter and begins
    /// differently. One or two words are too few to tell (the first word is often revised).
    static func startsOver(previous: [String], next: [String]) -> Bool {
        guard previous.count >= 3, !next.isEmpty, next.count < previous.count else { return false }
        let keep = min(2, next.count)
        return Array(next.prefix(keep)) != Array(previous.prefix(keep))
    }

    static func words(_ text: String) -> [String] {
        text.lowercased().split(whereSeparator: { $0.isWhitespace }).map { $0.trimmingCharacters(in: .punctuationCharacters) }
    }
}

/// The parts of one request, read and written only from its result handler (one at a time).
private final class PartsBox: @unchecked Sendable {
    private var parts = UtteranceParts()
    private var start: Double

    init(start: Double) {
        self.start = start
    }

    /// The part `text` belongs to and when that part began.
    func next(_ text: String, endsUtterance: Bool, now: Double) -> (part: Int, start: Double) {
        let previous = parts.part
        let part = parts.next(text, endsUtterance: endsUtterance)
        // The first words of a part arrive about a second after they were said.
        if part != previous { start = max(start, now - 1) }
        return (part, start)
    }
}

/// Hands a value with a single consumer across a concurrency boundary.
struct UncheckedBox<Value>: @unchecked Sendable {
    let value: Value
    init(_ value: Value) {
        self.value = value
    }
}
