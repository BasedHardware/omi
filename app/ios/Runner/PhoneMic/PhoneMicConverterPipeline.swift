import AVFoundation

/// Incremental conversion of tap buffers (whatever format the input route
/// negotiated) to PCM16 little-endian mono @16kHz.
///
/// One instance per tap install, reused for every buffer: AVAudioConverter's
/// resampler carries fractional-phase state between calls, which is what keeps
/// non-integer ratios (44.1k -> 16k) artifact- and drift-free. Recreating the
/// converter per buffer resets that state and produces clicks and cumulative
/// timing error.
///
/// Must only be used from a single serial queue (the owner's audio queue) —
/// AVAudioConverter is stateful and not thread-safe.
final class PhoneMicConverterPipeline {
    enum ConvertError: Error {
        /// A buffer arrived in a different format than the converter was built
        /// for — a route/config change beat the rebuild. Drop the buffer and
        /// rebuild; never feed a stale-format buffer to the resampler.
        case formatDrift
        case allocationFailed
        case converter(Error?)
    }

    static let outputSampleRate: Double = 16000

    private let converter: AVAudioConverter
    private let expectedInputFormat: AVAudioFormat
    private let outputFormat: AVAudioFormat

    init?(inputFormat: AVAudioFormat) {
        guard
            let outputFormat = AVAudioFormat(
                commonFormat: .pcmFormatInt16,
                sampleRate: Self.outputSampleRate,
                channels: 1,
                interleaved: true
            ),
            let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else { return nil }
        if inputFormat.channelCount > 1 {
            // Deterministically take channel 0 for speech instead of the
            // converter's unspecified default mixdown.
            converter.channelMap = [0]
        }
        self.converter = converter
        self.expectedInputFormat = inputFormat
        self.outputFormat = outputFormat
    }

    func convert(_ input: AVAudioPCMBuffer) -> Result<[Data], ConvertError> {
        guard input.format == expectedInputFormat else { return .failure(.formatDrift) }

        var pending: AVAudioPCMBuffer? = input
        var chunks: [Data] = []
        let ratio = Self.outputSampleRate / input.format.sampleRate
        // +64 frames of headroom absorbs the resampler's internal-buffer flush
        // so a single iteration suffices in the common case; the loop below is
        // the correctness net, not the hot path.
        let capacity = AVAudioFrameCount((Double(input.frameLength) * ratio).rounded(.up)) + 64

        while true {
            guard let out = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
                return .failure(.allocationFailed)
            }
            var conversionError: NSError?
            let status = converter.convert(to: out, error: &conversionError) { _, inputStatus in
                if let buffer = pending {
                    // Hand the buffer to the converter exactly once — the input
                    // block can be called multiple times per convert(), and
                    // re-returning the same buffer duplicates audio.
                    pending = nil
                    inputStatus.pointee = .haveData
                    return buffer
                }
                // .noDataNow, never .endOfStream: endOfStream permanently
                // finalizes the converter mid-stream.
                inputStatus.pointee = .noDataNow
                return nil
            }
            if status == .error {
                return .failure(.converter(conversionError))
            }
            if out.frameLength > 0, let samples = out.int16ChannelData?[0] {
                chunks.append(Data(bytes: samples, count: Int(out.frameLength) * MemoryLayout<Int16>.size))
            }
            // Output frame counts legitimately vary call-to-call at non-integer
            // ratios; a full output buffer with .haveData means more is pending.
            if status != .haveData || out.frameLength < capacity {
                break
            }
        }
        return .success(chunks)
    }
}
