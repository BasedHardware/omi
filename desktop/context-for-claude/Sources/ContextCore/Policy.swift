import ContextCoreCxx
import Foundation

// MARK: - Session boundaries

/// Decides when one conversation ends and the next begins.
///
/// Context for Claude never asks the user to press record, so a session boundary has to be inferred from
/// silence alone. A single gap threshold is the whole model on purpose: no meeting detection, no
/// calendar lookup, nothing that can be wrong in a way the user then has to correct.
public struct SessionPolicy {
    /// Five minutes of silence ends a conversation.
    ///
    /// Short enough that two unrelated conversations an hour apart do not merge into one
    /// unreadable transcript; long enough that thinking, typing, or walking to the kitchen in the
    /// middle of one conversation does not shatter it into fragments. The asymmetry is deliberate:
    /// recall degrades far more from a session that was split (the line that gave an earlier line
    /// its meaning is now in a different session) than from two that were joined.
    public static let gapSeconds = ctx_session_default_gap_seconds()

    /// The threshold this instance applies. Injectable so tests can express minutes without sleeping.
    public let gapSeconds: Double

    public init(gapSeconds: Double = SessionPolicy.gapSeconds) {
        self.gapSeconds = gapSeconds
    }

    /// Given the end of the last stored segment and the start of a new one, should a new session open?
    ///
    /// `nil` means nothing has been stored yet, which is always a new session — the alternative is
    /// a segment with no parent row.
    ///
    /// A gap that comes out negative means the wall clock moved backwards on us: an NTP correction,
    /// a sleep/wake transition, or a segment finishing out of order because two transcribers run
    /// concurrently. Comparing that against the threshold would open a spurious session in the
    /// middle of a live conversation for a reason the user can never see, so a backwards clock
    /// continues the current session instead. Continuing costs one over-long session; splitting
    /// costs context that recall can never put back.
    public func shouldOpenNewSession(lastSegmentEndedAt: Double?, nextSegmentStartedAt: Double) -> Bool {
        ctx_should_open_new_session(
            lastSegmentEndedAt == nil ? 0 : 1,
            lastSegmentEndedAt ?? 0,
            nextSegmentStartedAt,
            gapSeconds
        ) == 1
    }
}

// MARK: - Capture admission

/// The one gate every screen capture passes through.
///
/// There were two halves of this decision before there was a Settings pane: the credential-surface
/// rules in ``Redaction/isSensitiveWindow(app:title:)``, which are not negotiable, and nothing else.
/// User exclusions are the second half, and they are composed here rather than filtered in the UI —
/// a privacy control the capture path does not consult is a checkbox, not a control.
///
/// Both halves are asked with the same ``CaptureSubject`` so a caller cannot accidentally apply one
/// and not the other, and both are pure: no clock, no disk, no window server. What the app has to do
/// is call it — twice per tick, as `ScreenWatcher` already does, once before the window is resolved
/// and once with the title in hand.
public enum CapturePolicy {

    /// Why this capture must not be read or stored, or nil if it may be.
    ///
    /// User exclusions are asked first because they carry the more specific answer: a locked password
    /// manager should be reported as an excluded app and not as "a credential surface", which is what
    /// the Settings pane has to be able to explain.
    ///
    /// ``Redaction`` is asked with both identifier forms because the display name catches the vendors
    /// whose bundle id says nothing, and because a queued frame has only the display name left.
    public static func exclusion(
        for subject: CaptureSubject, using exclusions: ExclusionSet
    ) -> ExclusionReason? {
        if let reason = exclusions.reason(for: subject) { return reason }
        if isCredentialSurface(subject) { return .credentialSurface }
        return nil
    }

    private static func isCredentialSurface(_ subject: CaptureSubject) -> Bool {
        Redaction.isSensitiveWindow(app: subject.bundleID, title: subject.windowTitle)
            || Redaction.isSensitiveWindow(app: subject.appName, title: subject.windowTitle)
    }
}

// MARK: - Transcript hygiene

/// Rejects the noise a streaming transducer emits when nobody is talking.
///
/// Parakeet TDT is a streaming model with no notion of "nothing was said": handed a window of room
/// tone it will confidently emit *something*. Left unfiltered those artifacts outnumber real speech
/// in an always-on capture, and because every line is indexed into FTS they poison recall — a search
/// for "and" would return a thousand hallucinated windows. This filter is what keeps the database
/// worth searching, so it runs on every line before it is stored.
public enum TranscriptFilter {
    /// A run this long is a decoder loop rather than emphasis.
    ///
    /// Three is a real speech pattern ("no no no", "very very very"); at four the transducer has
    /// stopped advancing through the audio and is re-emitting its own last token.
    private static let repeatRunThreshold = 4

    /// What makes a line worth storing: at least one letter or digit somewhere.
    private static let contentCharacters = CharacterSet.letters.union(.decimalDigits)

    /// Characters stripped from a word before comparing it to its neighbour.
    ///
    /// A loop often terminates with punctuation attached ("and and and and."), and the repeat is
    /// still a repeat.
    private static let edgeNoise = CharacterSet.punctuationCharacters.union(.symbols)

    /// Trimmed text, or nil if the line should not be stored.
    ///
    /// The rejections, and the reason each exists:
    ///
    /// - Empty or whitespace-only: the model emitted nothing but padding.
    /// - No letter and no digit: a silent window makes Parakeet emit "…", "." or "-". These read as
    ///   real rows in the transcript and match nothing useful in search.
    /// - A dominant repeated run: the transducer looping on one token ("AND AND AND AND").
    /// - A single character: no single character is ever a useful transcript line, and it is a shape
    ///   only truncation and hallucination produce.
    ///
    /// Internal whitespace runs collapse to a single space so that stored text, FTS tokens, and the
    /// Markdown the MCP tools render all agree on what the line was.
    public static func clean(_ raw: String) -> String? {
        // Splitting on whitespace trims both ends and collapses internal runs in one pass.
        let words = raw.split(whereSeparator: { $0.isWhitespace })
        guard !words.isEmpty else { return nil }

        guard let kept = collapsingRepeatedRuns(words) else { return nil }
        let text = kept.joined(separator: " ")

        guard text.count > 1 else { return nil }
        guard text.unicodeScalars.contains(where: { contentCharacters.contains($0) }) else { return nil }

        return text
    }

    /// True when a window is below the speech floor and should never reach the model.
    ///
    /// The floor is tuned against what Parakeet TDT does with dead air rather than against any
    /// acoustic definition of silence. Room tone on a built-in mic sits around 0.001–0.003 RMS and
    /// the model reliably hallucinates on it; quiet speech across a room lands above 0.01. 0.004
    /// sits in that gap, biased low: skipping a window is unrecoverable (that speech is gone
    /// forever), whereas letting a marginal window through only risks one line that
    /// ``clean(_:)`` will most likely reject anyway. Raise it and real speech starts disappearing,
    /// which is the one failure mode an always-on recorder cannot have.
    ///
    /// Gating here also matters for cost: an inference on a silent window is pure battery.
    public static func isSilent(rms: Float, floor: Float = 0.004) -> Bool {
        rms < floor
    }

    /// Returns the words with decoder loops collapsed, or nil when the loop *is* the line.
    ///
    /// The judgement call: a run of four or more identical words is always an artifact, but the rest
    /// of the line around it may be perfectly good speech. Dropping "we should ship it and and and
    /// and then review it" would throw away a real sentence to remove one stutter, so a run inside
    /// an otherwise substantial line is stripped down to a single occurrence and the line is kept.
    /// Only when the repetition is the dominant content — half or more of the words — is there
    /// nothing left worth storing, and the line is dropped whole.
    ///
    /// The surviving occurrence is the first one, so a sentence-initial capital ("The the the the
    /// cat") survives; punctuation that happened to be attached to a later repeat is dropped along
    /// with it, which is the right trade for text the model never meant to emit.
    private static func collapsingRepeatedRuns(_ words: [Substring]) -> [Substring]? {
        let keys = words.map(repetitionKey)
        var kept: [Substring] = []
        kept.reserveCapacity(words.count)
        var repeatedWords = 0

        var index = 0
        while index < words.count {
            var end = index + 1
            while end < words.count, keys[end] == keys[index] { end += 1 }
            let runLength = end - index

            if runLength >= repeatRunThreshold {
                repeatedWords += runLength
                kept.append(words[index])
            } else {
                kept.append(contentsOf: words[index..<end])
            }
            index = end
        }

        guard repeatedWords > 0 else { return words }
        guard repeatedWords * 2 < words.count else { return nil }
        return kept
    }

    /// Comparison key for "is this the same word again".
    ///
    /// Case-insensitive because the loop Title-Cases inconsistently once the decoder state has gone
    /// bad, and edge punctuation is ignored because the same artifact appears as both "and" and
    /// "and,".
    private static func repetitionKey(_ word: Substring) -> String {
        word.lowercased().trimmingCharacters(in: edgeNoise)
    }
}

// MARK: - PCM

/// 16-bit PCM helpers, pure and unit-testable.
///
/// Every capture source in the app converts to the same wire format — 16 kHz mono Int16
/// little-endian — before anything downstream sees it, so the transcriber, the level meter, and the
/// silence gate all agree on what a sample is. These functions are the only place that format is
/// interpreted.
///
/// All of them read `Data` through `withUnsafeBytes` and never through integer subscripts. A `Data`
/// produced by slicing another `Data` keeps the parent's indices, so `data[0]` on a slice is a trap
/// waiting to happen — and audio buffers arrive as slices constantly. `withUnsafeBytes` hands back a
/// buffer that always starts at the slice's own first byte. The buffer is also not guaranteed to be
/// two-byte aligned, so every 16-bit read goes through `loadUnaligned`.
public enum PCM {
    /// Root-mean-square level of a chunk, normalised to 0...1.
    ///
    /// This is the number the silence gate and the menu-bar level meter both read, which is why it
    /// is normalised rather than expressed in dB: it has to be comparable against a fixed floor and
    /// drawable as a fraction without either caller re-deriving a scale.
    ///
    /// Empty data is silence, not an error — a capture callback firing with nothing in it is normal
    /// during device changes. An odd byte count means a chunk was split mid-sample somewhere
    /// upstream; the trailing byte is ignored rather than treated as a fatal condition, because
    /// dropping half a millisecond of audio is always better than tearing down the capture stack.
    public static func rms(int16LE data: Data) -> Float {
        data.withUnsafeBytes { raw in
            guard let bytes = raw.baseAddress?.assumingMemoryBound(to: UInt8.self) else { return 0 }
            return Float(ctx_pcm_rms_int16le(bytes, raw.count))
        }
    }

    /// Averages interleaved channels down to mono.
    ///
    /// Averaging rather than taking the first channel: USB interfaces and headsets routinely put the
    /// microphone on one channel and silence on the other, and picking a channel would lose that
    /// input entirely on half of them. Averaging keeps it at -6 dB, which the transcriber handles and
    /// a missing channel is not.
    ///
    /// `channels <= 1` returns the input untouched, which also keeps a zero from reaching the
    /// division. A sample count that is not a whole number of frames truncates the partial frame:
    /// device format changes produce ragged buffers, and losing one frame is not worth a crash.
    public static func downmixToMono(interleaved samples: [Float], channels: Int) -> [Float] {
        guard channels > 1 else { return samples }

        let frameCount = samples.count / channels
        guard frameCount > 0 else { return [] }

        var mono = [Float](repeating: 0, count: frameCount)
        let written = samples.withUnsafeBufferPointer { input in
            mono.withUnsafeMutableBufferPointer { output in
                ctx_pcm_downmix_mono(input.baseAddress, samples.count, Int32(channels), output.baseAddress)
            }
        }
        if written < mono.count { mono.removeLast(mono.count - written) }
        return mono
    }

    /// Encodes normalised float samples into the 16-bit little-endian wire format.
    ///
    /// Bytes are assembled by hand rather than by copying the machine's own representation of an
    /// `Int16`, so the output is little-endian on any host — this data is written to disk and passed
    /// between processes, and it must not silently depend on the byte order of the machine that
    /// produced it.
    ///
    /// Values outside -1...1 are clamped rather than allowed to wrap, because a wrapped sample is a
    /// full-scale sign flip: an audible click that also drags the RMS of its window over the silence
    /// floor and wakes the model for nothing.
    public static func int16LE(from samples: [Float]) -> Data {
        var bytes = [UInt8](repeating: 0, count: samples.count * 2)
        let written = samples.withUnsafeBufferPointer { input in
            bytes.withUnsafeMutableBufferPointer { output in
                ctx_pcm_encode_int16le(input.baseAddress, samples.count, output.baseAddress)
            }
        }
        if written < bytes.count { bytes.removeLast(bytes.count - written) }
        return Data(bytes)
    }

    /// Decodes the wire format back into normalised float samples.
    ///
    /// The inverse of ``int16LE(from:)`` up to one LSB, and the entry point for anything that has to
    /// do arithmetic on captured audio — resampling, mixing, or feeding the model — without
    /// re-deriving the endianness and scaling rules. A trailing odd byte is ignored for the same
    /// reason as in ``rms(int16LE:)``.
    public static func floatSamples(int16LE data: Data) -> [Float] {
        guard data.count >= 2 else { return [] }

        return data.withUnsafeBytes { raw -> [Float] in
            let count = raw.count / 2
            var samples = [Float](repeating: 0, count: count)
            let written = samples.withUnsafeMutableBufferPointer { output in
                ctx_pcm_decode_int16le(
                    raw.baseAddress?.assumingMemoryBound(to: UInt8.self),
                    raw.count,
                    output.baseAddress
                )
            }
            if written < samples.count { samples.removeLast(samples.count - written) }
            return samples
        }
    }
}
