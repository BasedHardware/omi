@preconcurrency import AVFoundation

/// Plays an audio file through the capture pipeline in real time, as if it came from the
/// microphone. For simulator and CI runs (no microphone), never used in release builds.
public final class AudioFileCapture: @unchecked Sendable {
    private let url: URL
    private var task: Task<Void, Never>?

    public init(url: URL) {
        self.url = url
    }

    /// Alive until stopped, like a microphone in a quiet room (the file's end is silence, not a stop).
    public var isRunning: Bool { stopHandler != nil }

    public func start() throws -> PhoneMicCapture.Output {
        let file = try AVAudioFile(forReading: url)
        let format = file.processingFormat
        guard let converter = PhoneMicConverter(inputFormat: format) else { throw PhoneMicCapture.CaptureError.converterUnavailable }
        let (pcm, pcmContinuation) = AsyncStream.makeStream(of: Data.self, bufferingPolicy: .bufferingNewest(512))
        let (buffers, bufferContinuation) = AsyncStream.makeStream(of: AVAudioPCMBuffer.self, bufferingPolicy: .bufferingNewest(64))
        let (level, levelContinuation) = AsyncStream.makeStream(of: Float.self, bufferingPolicy: .bufferingNewest(1))
        let box = UncheckedBox(file)
        task = Task.detached {
            let frames: AVAudioFrameCount = 4096
            while !Task.isCancelled {
                guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frames) else { break }
                do { try box.value.read(into: buffer, frameCount: frames) } catch { break }
                if buffer.frameLength == 0 { break }
                levelContinuation.yield(0.5)
                bufferContinuation.yield(buffer)
                for chunk in converter.convert(buffer) {
                    pcmContinuation.yield(chunk)
                }
                try? await Task.sleep(for: .seconds(Double(buffer.frameLength) / format.sampleRate))
            }
            levelContinuation.yield(0)
            // Keep the streams open (silence) until stopped, like a quiet room.
        }
        stopHandler = {
            pcmContinuation.finish()
            bufferContinuation.finish()
            levelContinuation.finish()
        }
        return PhoneMicCapture.Output(pcm16: pcm, buffers: buffers, level: level)
    }

    private var stopHandler: (() -> Void)?

    public func stop() {
        task?.cancel()
        stopHandler?()
        stopHandler = nil
    }
}
