@preconcurrency import AVFoundation

/// Converts the input route's format to PCM16 mono 16 kHz, the wire format of `/v4/listen`
/// (`codec=pcm16&sample_rate=16000`). Ported unchanged in behavior from the Flutter app's
/// `app/ios/Runner/PhoneMic/PhoneMicConverterPipeline.swift`.
final class PhoneMicConverter: @unchecked Sendable {
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
        if inputFormat.channelCount > 1 { converter.channelMap = [0] }
        self.converter = converter
        expectedInputFormat = inputFormat
        self.outputFormat = outputFormat
    }

    /// PCM16 chunks for one tap buffer; empty on format drift or converter failure.
    func convert(_ input: AVAudioPCMBuffer) -> [Data] {
        guard input.format == expectedInputFormat else { return [] }
        var pending: AVAudioPCMBuffer? = input
        var chunks: [Data] = []
        let ratio = Self.outputSampleRate / input.format.sampleRate
        let capacity = AVAudioFrameCount((Double(input.frameLength) * ratio).rounded(.up)) + 64
        while true {
            guard let out = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else { return chunks }
            var conversionError: NSError?
            let status = converter.convert(to: out, error: &conversionError) { _, inputStatus in
                if let buffer = pending {
                    pending = nil
                    inputStatus.pointee = .haveData
                    return buffer
                }
                inputStatus.pointee = .noDataNow
                return nil
            }
            if status == .error { return chunks }
            if out.frameLength > 0, let samples = out.int16ChannelData?[0] {
                chunks.append(Data(bytes: samples, count: Int(out.frameLength) * MemoryLayout<Int16>.size))
            }
            if status != .haveData || out.frameLength < capacity { break }
        }
        return chunks
    }
}
