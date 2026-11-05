@preconcurrency import AVFoundation
import Foundation
import OmiAudio
import OmiNetwork

/// Phone microphone plus optional on-device transcription, as the capture store sees it.
public protocol PhoneCaptureEngine: AnyObject, Sendable {
    func start(transcribeOnDevice: Bool) async throws -> PhoneCaptureStreams
    func stop()
    /// False while a recording is live means the OS took the capture away without saying so.
    var isRunning: Bool { get }
}

public struct PhoneCaptureStreams: Sendable {
    public let pcm16: AsyncStream<Data>
    public let level: AsyncStream<Float>
    /// Present in on-device mode: partial and final transcript segments.
    public let transcript: AsyncStream<(segment: LiveSegment, isFinal: Bool)>?

    public init(pcm16: AsyncStream<Data>, level: AsyncStream<Float>, transcript: AsyncStream<(segment: LiveSegment, isFinal: Bool)>?) {
        self.pcm16 = pcm16
        self.level = level
        self.transcript = transcript
    }
}

public enum CaptureFailure: Error, Equatable {
    case microphonePermission
    case speechPermission
    case speechUnavailable
    case engine(String)
}

/// The real engine: AVAudioEngine capture + Apple speech recognition.
public final class LivePhoneCaptureEngine: PhoneCaptureEngine, @unchecked Sendable {
    private let microphone = PhoneMicCapture()
    private var fileCapture: AudioFileCapture?
    private var transcriber: OnDeviceTranscriber?
    /// Debug/CI: play this file instead of the microphone.
    private let audioFile: URL?
    /// Debug/CI: stand-in for the recognizer where Apple speech cannot run (the simulator).
    private let fixtureTranscript: String?
    /// The language the user speaks, read at each start (Settings can change it).
    private let language: @Sendable () -> String?

    public init(audioFile: URL? = nil, fixtureTranscript: String? = nil, language: @escaping @Sendable () -> String? = { nil }) {
        self.audioFile = audioFile
        self.fixtureTranscript = fixtureTranscript
        self.language = language
    }

    public func start(transcribeOnDevice: Bool) async throws -> PhoneCaptureStreams {
        if audioFile == nil { guard await PhoneMicCapture.requestPermission() else { throw CaptureFailure.microphonePermission } }
        var transcriber: OnDeviceTranscriber?
        if transcribeOnDevice, fixtureTranscript == nil {
            guard await OnDeviceTranscriber.requestAuthorization() else { throw CaptureFailure.speechPermission }
            guard let created = OnDeviceTranscriber.forLanguage(language()) else { throw CaptureFailure.speechUnavailable }
            transcriber = created
        }
        let output: PhoneMicCapture.Output
        do {
            if let audioFile {
                let capture = AudioFileCapture(url: audioFile)
                fileCapture = capture
                output = try capture.start()
            } else {
                output = try microphone.start()
            }
        } catch {
            throw CaptureFailure.engine(String(describing: error))
        }
        self.transcriber = transcriber
        if transcribeOnDevice, let fixtureTranscript {
            return PhoneCaptureStreams(pcm16: output.pcm16, level: output.level, transcript: Self.fixture(fixtureTranscript))
        }
        let transcript = transcriber.map { transcriber in
            let segments = transcriber.transcribe(output.buffers)
            return AsyncStream<(segment: LiveSegment, isFinal: Bool)> { continuation in
                Task {
                    for await segment in segments {
                        let live = LiveSegment(
                            id: segment.id, text: segment.text, speaker: "SPEAKER_00", speakerID: 0,
                            isUser: true, start: segment.start, end: segment.end
                        )
                        continuation.yield((live, segment.isFinal))
                    }
                    continuation.finish()
                }
            }
        }
        return PhoneCaptureStreams(pcm16: output.pcm16, level: output.level, transcript: transcript)
    }

    /// Emits each sentence as a final segment, about as fast as it would be spoken.
    static func fixture(_ text: String) -> AsyncStream<(segment: LiveSegment, isFinal: Bool)> {
        let sentences = text.split(whereSeparator: { ".!?".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return AsyncStream { continuation in
            Task {
                var start = 0.0
                for (index, sentence) in sentences.enumerated() {
                    let seconds = Double(sentence.split(separator: " ").count) * 0.35
                    try? await Task.sleep(for: .seconds(seconds))
                    let segment = LiveSegment(
                        id: "fixture-\(index)", text: sentence + ".", speaker: "SPEAKER_00", speakerID: 0,
                        isUser: true, start: start, end: start + seconds
                    )
                    continuation.yield((segment, true))
                    start += seconds
                }
            }
        }
    }

    public var isRunning: Bool {
        if let fileCapture { return fileCapture.isRunning }
        return microphone.isRunning
    }

    public func stop() {
        transcriber?.stop()
        if let fileCapture {
            fileCapture.stop()
            self.fileCapture = nil
        } else {
            microphone.stop()
        }
        transcriber = nil
    }
}

/// On-device transcription of the Omi wearable's opus audio (no cloud speech-to-text needed).
public protocol DeviceTranscriptionEngine: AnyObject, Sendable {
    func start() async throws -> DeviceTranscription
    func stop()
}

public struct DeviceTranscription: Sendable {
    /// Hands one opus frame (header already stripped) to the decoder.
    public let feed: @Sendable (Data) -> Void
    public let transcript: AsyncStream<(segment: LiveSegment, isFinal: Bool)>

    public init(feed: @escaping @Sendable (Data) -> Void, transcript: AsyncStream<(segment: LiveSegment, isFinal: Bool)>) {
        self.feed = feed
        self.transcript = transcript
    }
}

public final class LiveDeviceTranscriptionEngine: DeviceTranscriptionEngine, @unchecked Sendable {
    private var transcriber: OnDeviceTranscriber?
    private var buffers: AsyncStream<AVAudioPCMBuffer>.Continuation?
    private let language: @Sendable () -> String?

    public init(language: @escaping @Sendable () -> String? = { nil }) {
        self.language = language
    }

    public func start() async throws -> DeviceTranscription {
        guard await OnDeviceTranscriber.requestAuthorization() else { throw CaptureFailure.speechPermission }
        guard let transcriber = OnDeviceTranscriber.forLanguage(language()) else { throw CaptureFailure.speechUnavailable }
        let decoder = try OpusFrameDecoder()
        let (stream, continuation) = AsyncStream.makeStream(of: AVAudioPCMBuffer.self, bufferingPolicy: .bufferingNewest(256))
        self.transcriber = transcriber
        buffers = continuation
        let segments = transcriber.transcribe(stream)
        let transcript = AsyncStream<(segment: LiveSegment, isFinal: Bool)> { output in
            Task {
                for await segment in segments {
                    output.yield((LiveSegment(
                        id: segment.id, text: segment.text, speaker: "SPEAKER_00", speakerID: 0,
                        isUser: true, start: segment.start, end: segment.end
                    ), segment.isFinal))
                }
                output.finish()
            }
        }
        let box = UncheckedSendable(decoder)
        return DeviceTranscription(
            feed: { frame in if let pcm = box.value.decode(frame) { continuation.yield(pcm) } },
            transcript: transcript
        )
    }

    public func stop() {
        buffers?.finish()
        transcriber?.stop()
        buffers = nil
        transcriber = nil
    }
}

extension OnDeviceTranscriber {
    /// The user's language when Apple can recognize it, else the iPhone's own.
    static func forLanguage(_ language: String?) -> OnDeviceTranscriber? {
        language.flatMap { OnDeviceTranscriber(language: $0) } ?? OnDeviceTranscriber()
    }
}

struct UncheckedSendable<Value>: @unchecked Sendable {
    let value: Value
    init(_ value: Value) {
        self.value = value
    }
}
