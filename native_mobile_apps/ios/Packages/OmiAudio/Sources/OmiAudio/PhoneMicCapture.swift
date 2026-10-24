@preconcurrency import AVFoundation

/// Phone microphone capture. Emits PCM16/16 kHz chunks for the listen socket and, when asked,
/// the raw tap buffers for on-device speech recognition. Session setup mirrors the Flutter app's
/// `PhoneMicSessionConfigurator` (record while other audio plays, Bluetooth headsets allowed).
public final class PhoneMicCapture: @unchecked Sendable {
    public enum CaptureError: Error, Equatable {
        case permissionDenied
        case noInput
        case converterUnavailable
        case engine(String)
    }

    /// Buffers are deep copies handed off exactly once, hence unchecked.
    public struct Output: @unchecked Sendable {
        public let pcm16: AsyncStream<Data>
        public let buffers: AsyncStream<AVAudioPCMBuffer>
        /// 0…1 input level for the live UI.
        public let level: AsyncStream<Float>
    }

    /// Rebuilt on every stop: after a media-services reset the old engine object is dead and only
    /// a new one can see the microphone again.
    private var engine = AVAudioEngine()
    private let queue = DispatchQueue(label: "omi.phone-mic")
    private struct Continuations {
        let pcm: AsyncStream<Data>.Continuation
        let buffer: AsyncStream<AVAudioPCMBuffer>.Continuation
        let level: AsyncStream<Float>.Continuation
    }

    private var continuations: Continuations?

    public init() {}

    /// False when the tap is gone, which the OS can do without telling anyone (a route change, a
    /// competing recorder). The store watches this to take the microphone back.
    public var isRunning: Bool { engine.isRunning && continuations != nil }

    public static func requestPermission() async -> Bool {
        await AVAudioApplication.requestRecordPermission()
    }

    public func start() throws -> Output {
        if continuations != nil { stop() }
        #if os(iOS)
            let session = AVAudioSession.sharedInstance()
            do {
                try session.setCategory(.playAndRecord, mode: .default,
                                        options: [.mixWithOthers, .allowBluetoothHFP, .allowBluetoothA2DP, .defaultToSpeaker])
                try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
                try session.setActive(true)
            } catch {
                throw CaptureError.engine(error.localizedDescription)
            }
        #endif

        let input = engine.inputNode
        let format = input.inputFormat(forBus: 0)
        guard format.channelCount > 0, format.sampleRate > 0 else { throw CaptureError.noInput }
        guard let converter = PhoneMicConverter(inputFormat: format) else { throw CaptureError.converterUnavailable }

        let (pcm, pcmContinuation) = AsyncStream.makeStream(of: Data.self, bufferingPolicy: .bufferingNewest(512))
        let (buffers, bufferContinuation) = AsyncStream.makeStream(of: AVAudioPCMBuffer.self, bufferingPolicy: .bufferingNewest(64))
        let (level, levelContinuation) = AsyncStream.makeStream(of: Float.self, bufferingPolicy: .bufferingNewest(1))
        continuations = Continuations(pcm: pcmContinuation, buffer: bufferContinuation, level: levelContinuation)

        let queue = queue
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, _ in
            guard let copy = Self.deepCopy(buffer) else { return }
            levelContinuation.yield(Self.rms(copy))
            bufferContinuation.yield(copy)
            queue.async {
                for chunk in converter.convert(copy) {
                    pcmContinuation.yield(chunk)
                }
            }
        }
        do {
            engine.prepare()
            try engine.start()
        } catch {
            stop()
            throw CaptureError.engine(error.localizedDescription)
        }
        return Output(pcm16: pcm, buffers: buffers, level: level)
    }

    public func stop() {
        // A dead engine (media services reset) must not be touched at all: reading its input node
        // can raise. Dropping it is the only thing that helps, so a new one takes its place below.
        if engine.isRunning {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }
        continuations?.pcm.finish()
        continuations?.buffer.finish()
        continuations?.level.finish()
        continuations = nil
        engine = AVAudioEngine()
        #if os(iOS)
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        #endif
    }

    private static func deepCopy(_ buffer: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let copy = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: max(buffer.frameLength, 1)) else { return nil }
        copy.frameLength = buffer.frameLength
        let src = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: buffer.audioBufferList))
        let dst = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        guard src.count == dst.count else { return nil }
        for index in 0 ..< src.count {
            guard let from = src[index].mData, let to = dst[index].mData else { return nil }
            memcpy(to, from, Int(min(src[index].mDataByteSize, dst[index].mDataByteSize)))
        }
        return copy
    }

    private static func rms(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let samples = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return 0 }
        var sum: Float = 0
        for index in 0 ..< Int(buffer.frameLength) {
            sum += samples[index] * samples[index]
        }
        let rms = sqrt(sum / Float(buffer.frameLength))
        return min(1, rms * 8)
    }
}
