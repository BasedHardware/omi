@preconcurrency import AVFoundation
import Foundation
import OmiAudio
import OmiNetwork

/// Where onboarding hears the user: the iPhone microphone or the Omi. Both deliver 16 kHz mono PCM16.
public protocol VoiceInput: AnyObject, Sendable {
    func start() async throws -> AsyncStream<Data>
    func stop()
}

/// The iPhone microphone (or, for the simulator and CI, an audio file played in real time).
public final class PhoneVoiceInput: VoiceInput, @unchecked Sendable {
    private let microphone = PhoneMicCapture()
    private var file: AudioFileCapture?
    private let audioFile: URL?

    public init(audioFile: URL? = nil) {
        self.audioFile = audioFile
    }

    public func start() async throws -> AsyncStream<Data> {
        if let audioFile {
            let capture = AudioFileCapture(url: audioFile)
            file = capture
            return try capture.start().pcm16
        }
        guard await PhoneMicCapture.requestPermission() else { throw CaptureFailure.microphonePermission }
        return try microphone.start().pcm16
    }

    public func stop() {
        if let file {
            file.stop()
            self.file = nil
        } else {
            microphone.stop()
        }
    }
}

/// The Omi's opus audio, decoded on the iPhone. Reads frames through `DeviceStore.audioTap`.
@MainActor
public final class DeviceVoiceInput: VoiceInput, @unchecked Sendable {
    private let devices: DeviceStore

    public init(devices: DeviceStore) {
        self.devices = devices
    }

    public func start() async throws -> AsyncStream<Data> {
        let decoder = try OpusFrameDecoder()
        let (stream, continuation) = AsyncStream.makeStream(of: Data.self, bufferingPolicy: .bufferingNewest(512))
        devices.audioTap = { frame in
            if let buffer = decoder.decode(frame) { continuation.yield(PCM16.data(from: buffer)) }
        }
        return stream
    }

    public nonisolated func stop() {
        Task { @MainActor in devices.audioTap = nil }
    }
}

/// PCM16 helpers for onboarding's voice sample.
public enum PCM16 {
    /// Float samples (-1…1) to little-endian Int16.
    static func data(from buffer: AVAudioPCMBuffer) -> Data {
        guard let samples = buffer.floatChannelData?[0] else { return Data() }
        var data = Data(count: Int(buffer.frameLength) * 2)
        data.withUnsafeMutableBytes { raw in
            let out = raw.bindMemory(to: Int16.self)
            for index in 0 ..< Int(buffer.frameLength) {
                out[index] = Int16(max(-1, min(1, samples[index])) * Float(Int16.max))
            }
        }
        return data
    }

    /// Root mean square, 0…1.
    public static func level(_ chunk: Data) -> Float {
        let count = chunk.count / 2
        guard count > 0 else { return 0 }
        let sum = chunk.withUnsafeBytes { raw in
            raw.bindMemory(to: Int16.self).reduce(Float(0)) { $0 + pow(Float($1) / Float(Int16.max), 2) }
        }
        return sqrt(sum / Float(count))
    }

    /// A 16 kHz mono WAV around raw PCM16.
    public static func wav(_ pcm: Data, sampleRate: Int = 16000) -> Data {
        var header = Data()
        func append(_ value: some FixedWidthInteger) { withUnsafeBytes(of: value.littleEndian) { header.append(contentsOf: $0) } }
        header.append(Data("RIFF".utf8)); append(UInt32(36 + pcm.count)); header.append(Data("WAVE".utf8))
        header.append(Data("fmt ".utf8)); append(UInt32(16)); append(UInt16(1)); append(UInt16(1))
        append(UInt32(sampleRate)); append(UInt32(sampleRate * 2)); append(UInt16(2)); append(UInt16(16))
        header.append(Data("data".utf8)); append(UInt32(pcm.count))
        return header + pcm
    }
}

/// Live words on the iPhone itself: onboarding's first choice (instant, works offline).
public protocol LiveRecognizer: AnyObject, Sendable {
    /// Nil when recognition cannot run (no permission, language not supported).
    func start(language: String) async -> AsyncStream<LiveSegment>?
    func feed(_ pcm16: Data)
    /// What is said from now on arrives as a new segment (onboarding: one per sentence).
    func startNewUtterance()
    func stop()
}

/// Apple's speech recognizer (on device where the language allows it). Debug builds can hand it a
/// fixed transcript instead, since the simulator has no recognizer: its words then follow the
/// speech in the audio fed to it, one sentence per stretch of speech.
public final class AppleLiveRecognizer: LiveRecognizer, @unchecked Sendable {
    private let scripted: ScriptedSpeech?
    private var transcriber: OnDeviceTranscriber?
    private var buffers: AsyncStream<AVAudioPCMBuffer>.Continuation?
    private let format = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)

    public init(fixtureTranscript: String? = nil) {
        scripted = fixtureTranscript.map(ScriptedSpeech.init)
    }

    public func start(language: String) async -> AsyncStream<LiveSegment>? {
        if let scripted { return scripted.start() }
        // Strictly the user's language: a recognizer for another one would bring wrong words,
        // and wrong words keep the watchdog from handing over to the server.
        guard await OnDeviceTranscriber.requestAuthorization(),
              let transcriber = OnDeviceTranscriber(language: language) else { return nil }
        let (stream, continuation) = AsyncStream.makeStream(of: AVAudioPCMBuffer.self, bufferingPolicy: .bufferingNewest(256))
        self.transcriber = transcriber
        buffers = continuation
        let segments = transcriber.transcribe(stream)
        return AsyncStream { output in
            Task {
                for await segment in segments {
                    output.yield(LiveSegment(
                        id: segment.id, text: segment.text, speaker: "SPEAKER_00", speakerID: 0,
                        isUser: true, start: segment.start, end: segment.end
                    ))
                }
                output.finish()
            }
        }
    }

    public func feed(_ pcm16: Data) {
        if let scripted { return scripted.feed(pcm16) }
        guard let buffers, let format, let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(pcm16.count / 2)),
              let channel = buffer.floatChannelData?[0] else { return }
        buffer.frameLength = AVAudioFrameCount(pcm16.count / 2)
        pcm16.withUnsafeBytes { raw in
            for (index, sample) in raw.bindMemory(to: Int16.self).enumerated() {
                channel[index] = Float(sample) / Float(Int16.max)
            }
        }
        buffers.yield(buffer)
    }

    public func startNewUtterance() {
        transcriber?.startNewUtterance()
    }

    public func stop() {
        scripted?.stop()
        buffers?.finish()
        transcriber?.stop()
        buffers = nil
        transcriber = nil
    }
}

/// A stand-in recognizer for the simulator: says a fixed script, paced by the speech in the audio
/// it is fed. Words appear one by one while there is speech; a pause ends the sentence.
final class ScriptedSpeech: @unchecked Sendable {
    private let sentences: [[String]]
    private let lock = NSLock()
    private var continuation: AsyncStream<LiveSegment>.Continuation?
    private var sentence = 0
    private var speech: Double = 0
    private var quiet: Double = 0
    private var shown = 0

    init(_ script: String) {
        sentences = script.split(whereSeparator: { ".!?|".contains($0) })
            .map { $0.split(separator: " ").map(String.init) }
            .filter { !$0.isEmpty }
    }

    func start() -> AsyncStream<LiveSegment> {
        let (stream, continuation) = AsyncStream.makeStream(of: LiveSegment.self)
        lock.withLock { self.continuation = continuation }
        return stream
    }

    func feed(_ pcm16: Data) {
        let seconds = Double(pcm16.count) / 32000
        let speaking = PCM16.level(pcm16) > 0.008
        let segment: LiveSegment? = lock.withLock {
            guard sentence < sentences.count else { return nil }
            if speaking {
                speech += seconds
                quiet = 0
            } else {
                quiet += seconds
            }
            let words = sentences[sentence]
            func line(_ count: Int) -> LiveSegment {
                LiveSegment(
                    id: "scripted-\(sentence)", text: words.prefix(count).joined(separator: " "), speaker: "SPEAKER_00",
                    speakerID: 0, isUser: true, start: 0, end: speech
                )
            }
            // A pause after speech: the rest of the sentence, then on to the next one.
            if quiet >= 0.5, speech > 0 {
                let rest = shown < words.count ? line(words.count) : nil
                sentence += 1
                speech = 0
                shown = 0
                return rest
            }
            // About three words a second, as people speak.
            let count = min(words.count, Int(speech / 0.3) + 1)
            guard speaking, count > shown else { return nil }
            shown = count
            return line(count)
        }
        if let segment { lock.withLock { continuation }?.yield(segment) }
    }

    func stop() {
        lock.withLock {
            continuation?.finish()
            continuation = nil
        }
    }
}
