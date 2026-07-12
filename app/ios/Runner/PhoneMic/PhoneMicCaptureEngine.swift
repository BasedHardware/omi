import AVFoundation

/// Owns one AVAudioEngine and its input-node tap. The tap block does the
/// absolute minimum on CoreAudio's tap-dispatch thread: deep-copy the buffer
/// and hop to the audio queue, where the converter runs. Control-plane methods
/// (build/start/teardown) are called from the controller's control queue.
///
/// One instance per bring-up: the controller discards the whole engine on
/// every rebuild (interruption resume, route change, media-services reset), so
/// no stale engine or converter state can survive a route generation.
final class PhoneMicCaptureEngine {
    enum EngineError: Error {
        case formatInvalid
        case converterInitFailed
    }

    /// Sized for ASR streaming: throughput over latency (~85ms @48k).
    static let tapBufferSize: AVAudioFrameCount = 4096

    let engine = AVAudioEngine()

    private let audioQueue: DispatchQueue
    /// Called on audioQueue with converted PCM16 data and the capture epoch the
    /// tap was installed under.
    private let onConvertedData: (Data, UInt64) -> Void
    /// Called on audioQueue when conversion fails.
    private let onConvertError: (PhoneMicConverterPipeline.ConvertError, UInt64) -> Void
    private var tapInstalled = false

    init(
        audioQueue: DispatchQueue,
        onConvertedData: @escaping (Data, UInt64) -> Void,
        onConvertError: @escaping (PhoneMicConverterPipeline.ConvertError, UInt64) -> Void
    ) {
        self.audioQueue = audioQueue
        self.onConvertedData = onConvertedData
        self.onConvertError = onConvertError
    }

    /// Validates the negotiated input format, builds the converter, and
    /// installs the tap with `epoch` baked into its closure — stale frames from
    /// a previous epoch are dropped by the emitter, which is what guarantees no
    /// frame outlives a stop() or crosses a rebuild.
    func buildAndInstallTap(epoch: UInt64) throws {
        let input = engine.inputNode
        let inputFormat = input.inputFormat(forBus: 0)
        guard inputFormat.channelCount > 0, inputFormat.sampleRate > 0, inputFormat.sampleRate.isFinite else {
            throw EngineError.formatInvalid
        }
        guard let pipeline = PhoneMicConverterPipeline(inputFormat: inputFormat) else {
            throw EngineError.converterInitFailed
        }

        // Defensive: installing over an existing tap crashes.
        input.removeTap(onBus: 0)
        let audioQueue = self.audioQueue
        let onConvertedData = self.onConvertedData
        let onConvertError = self.onConvertError
        input.installTap(onBus: 0, bufferSize: Self.tapBufferSize, format: inputFormat) { buffer, _ in
            // CoreAudio may reuse this buffer the moment the block returns —
            // deep-copy before any asynchronous work.
            guard let copy = Self.deepCopy(buffer) else { return }
            audioQueue.async {
                switch pipeline.convert(copy) {
                case .success(let chunks):
                    for chunk in chunks {
                        onConvertedData(chunk, epoch)
                    }
                case .failure(let error):
                    onConvertError(error, epoch)
                }
            }
        }
        tapInstalled = true
    }

    func startEngine() throws {
        engine.prepare()
        try engine.start()
    }

    func teardown() {
        if tapInstalled {
            engine.inputNode.removeTap(onBus: 0)
            tapInstalled = false
        }
        if engine.isRunning {
            engine.stop()
        }
    }

    private static func deepCopy(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let copy = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: max(buffer.frameLength, 1)) else {
            return nil
        }
        copy.frameLength = buffer.frameLength
        // Copy via the buffer lists so interleaved and deinterleaved layouts are
        // both handled without format-specific channel-pointer arithmetic.
        let src = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: buffer.audioBufferList))
        let dst = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        guard src.count == dst.count else { return nil }
        for i in 0..<src.count {
            guard let srcData = src[i].mData, let dstData = dst[i].mData else { return nil }
            memcpy(dstData, srcData, Int(min(src[i].mDataByteSize, dst[i].mDataByteSize)))
        }
        return copy
    }
}
