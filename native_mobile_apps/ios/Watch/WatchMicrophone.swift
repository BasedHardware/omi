import AVFoundation
import Foundation

/// The watch microphone as 16 kHz mono PCM16, in 1.5 s chunks (`WatchAudioChunk`), the Flutter
/// watch app's format. Chunks are handed over on the audio thread.
final class WatchMicrophone: @unchecked Sendable {
    enum Failure: Error { case noInput }

    private let engine = AVAudioEngine()
    private let output = AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: WatchAudioChunk.sampleRate, channels: 1, interleaved: true
    )!
    private let onChunk: @Sendable (WatchAudioChunk) -> Void
    private let lock = NSLock()
    private var converter: AVAudioConverter?
    private var pending = Data()
    private var index = 0

    init(onChunk: @escaping @Sendable (WatchAudioChunk) -> Void) {
        self.onChunk = onChunk
    }

    func start() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .default)
        try session.setActive(true)
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, let converter = AVAudioConverter(from: format, to: output) else { throw Failure.noInput }
        lock.withLock {
            self.converter = converter
            pending = Data()
            index = 0
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.convert(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            throw error
        }
    }

    /// Stops and hands over what is left, then the empty last chunk.
    func stop() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        let (rest, next) = lock.withLock {
            converter = nil
            defer {
                pending = Data()
                index = 0
            }
            return (pending, index)
        }
        var last = next
        if !rest.isEmpty {
            onChunk(WatchAudioChunk(data: rest, index: last, isLast: false))
            last += 1
        }
        onChunk(WatchAudioChunk(data: Data(), index: last, isLast: true))
    }

    private func convert(_ buffer: AVAudioPCMBuffer) {
        guard let converter = lock.withLock({ converter }), buffer.frameLength > 0 else { return }
        let ratio = output.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount((Double(buffer.frameLength) * ratio).rounded(.up)) + 32
        guard let converted = AVAudioPCMBuffer(pcmFormat: output, frameCapacity: capacity) else { return }
        // The input is handed over once per call; asking again means "no more for now".
        let feed = OneShot(buffer)
        var error: NSError?
        converter.convert(to: converted, error: &error) { _, status in
            guard let next = feed.take() else {
                status.pointee = .noDataNow
                return nil
            }
            status.pointee = .haveData
            return next
        }
        guard error == nil, converted.frameLength > 0, let samples = converted.int16ChannelData else { return }
        append(Data(bytes: samples[0], count: Int(converted.frameLength) * MemoryLayout<Int16>.size))
    }

    private func append(_ pcm: Data) {
        let ready: [WatchAudioChunk] = lock.withLock {
            pending.append(pcm)
            var chunks: [WatchAudioChunk] = []
            while pending.count >= WatchAudioChunk.bytesPerChunk {
                chunks.append(WatchAudioChunk(data: Data(pending.prefix(WatchAudioChunk.bytesPerChunk)), index: index, isLast: false))
                pending = Data(pending.dropFirst(WatchAudioChunk.bytesPerChunk))
                index += 1
            }
            return chunks
        }
        ready.forEach(onChunk)
    }
}

/// The tap's buffer for the converter's input block, given out exactly once.
private final class OneShot: @unchecked Sendable {
    private var buffer: AVAudioPCMBuffer?

    init(_ buffer: AVAudioPCMBuffer) {
        self.buffer = buffer
    }

    func take() -> AVAudioPCMBuffer? {
        defer { buffer = nil }
        return buffer
    }
}
