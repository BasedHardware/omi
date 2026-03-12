import Combine
import Foundation
import os.log

// MARK: - BLE Audio Processor

/// Processes audio data from BLE devices
/// Handles frame reassembly, codec decoding, and integration with transcription
/// Ported from: omi/app/lib/utils/audio/wav_bytes.dart (WavBytesUtil)
final class BleAudioProcessor {

    // MARK: - Types

    /// Audio frame with metadata
    struct AudioFrame {
        let pcmSamples: [Int16]
        let timestamp: Date
        let frameIndex: Int
    }

    /// Delegate for receiving decoded audio
    protocol Delegate: AnyObject {
        /// Called when PCM audio samples are ready
        func bleAudioProcessor(_ processor: BleAudioProcessor, didDecodeSamples samples: [Int16])

        /// Called when audio decoding fails
        func bleAudioProcessor(_ processor: BleAudioProcessor, didFailWithError error: Error)
    }

    // MARK: - Properties

    weak var delegate: Delegate?

    /// Publisher for decoded PCM samples (alternative to delegate)
    var pcmSamplesPublisher: AnyPublisher<[Int16], Never> {
        pcmSamplesSubject.eraseToAnyPublisher()
    }

    /// Publisher for raw PCM data (as bytes, for TranscriptionService)
    var pcmDataPublisher: AnyPublisher<Data, Never> {
        pcmSamplesSubject
            .map { samples in
                // Convert Int16 samples to Data (little-endian)
                var data = Data(capacity: samples.count * 2)
                for sample in samples {
                    var s = sample
                    data.append(Data(bytes: &s, count: 2))
                }
                return data
            }
            .eraseToAnyPublisher()
    }

    private let logger = Logger(subsystem: "me.omi.desktop", category: "BleAudioProcessor")
    private let pcmSamplesSubject = PassthroughSubject<[Int16], Never>()

    // Codec and decoder
    private var codec: BleAudioCodec
    private var decoder: AudioCodecDecoder?

    // Frame reassembly state (for multi-packet frames)
    private var lastPacketIndex: Int = -1
    private var lastFrameId: Int = -1
    private var pendingFrame: [UInt8] = []
    private var framesBuffer: [[UInt8]] = []

    // Statistics
    private var totalFramesProcessed: Int = 0
    private var totalBytesProcessed: Int = 0
    private var lostPackets: Int = 0

    // MARK: - Initialization

    init(codec: BleAudioCodec) {
        self.codec = codec
        self.decoder = AudioDecoderFactory.createDecoder(for: codec)

        if decoder == nil && codec != .unknown {
            logger.warning("No decoder available for codec: \(codec.name)")
        } else {
            logger.info("BleAudioProcessor initialized for codec: \(codec.name)")
        }
    }

    // MARK: - Public Methods

    /// Update the codec (e.g., after reading from device)
    func updateCodec(_ newCodec: BleAudioCodec) {
        guard newCodec != codec else { return }

        codec = newCodec
        decoder = AudioDecoderFactory.createDecoder(for: newCodec)
        reset()

        logger.info("Codec updated to: \(newCodec.name)")
    }

    /// Process raw audio bytes from BLE device
    /// Call this with each BLE notification data
    /// - Parameter data: Raw audio data from BLE characteristic
    func processAudioData(_ data: Data) {
        guard !data.isEmpty else { return }

        totalBytesProcessed += data.count

        // For devices that send pre-framed data (Fieldy, Friend Pendant),
        // process directly without reassembly
        if codec == .opusFS320 || codec == .lc3FS1030 {
            processFramedData(data)
            return
        }

        // For devices with packet framing (Omi/OpenGlass), use reassembly
        processPacketData(data)
    }

    /// Process a complete audio frame (already extracted from BLE packets)
    /// Use this for devices that pre-extract frames (Fieldy, Limitless)
    func processFrame(_ frame: Data) {
        guard !frame.isEmpty else { return }

        totalFramesProcessed += 1

        if let decoder = decoder {
            if let samples = decoder.decode(frame) {
                deliverSamples(samples)
                decodeFailures = 0 // Reset failure counter on success
            } else {
                handleDecodeFailure(frame)
            }
        } else {
            // No decoder - try to pass through as PCM
            if codec.isPCM {
                if let passthrough = PCMPassthroughDecoder(codec: codec).decode(frame) {
                    deliverSamples(passthrough)
                }
            } else {
                logger.warning("No decoder available for codec: \(self.codec.name)")
            }
        }
    }

    /// Track consecutive decode failures
    private var decodeFailures = 0
    private let maxDecodeFailures = 10

    /// Handle decode failure with logging and fallback
    private func handleDecodeFailure(_ frame: Data) {
        decodeFailures += 1

        if decodeFailures == 1 {
            // Log first failure with frame details
            let preview = frame.prefix(16).map { String(format: "%02x", $0) }.joined(separator: " ")
            logger.warning("Decode failed. Frame size: \(frame.count), preview: \(preview)")
        } else if decodeFailures == maxDecodeFailures {
            logger.error("Too many consecutive decode failures (\(self.decodeFailures)). Check codec compatibility.")
        }

        // For Opus, validate TOC byte
        if codec.isOpus && !frame.isEmpty {
            let toc = frame[0]
            if !isValidOpusToc(toc) {
                logger.debug("Invalid Opus TOC: 0x\(String(format: "%02x", toc))")
            }
        }
    }

    /// Check if byte is a valid Opus TOC byte
    private func isValidOpusToc(_ byte: UInt8) -> Bool {
        [0x78, 0xb8, 0xf8, 0x70, 0xb0, 0xf0].contains(byte)
    }

    /// Process multiple frames at once
    func processFrames(_ frames: [Data]) {
        for frame in frames {
            processFrame(frame)
        }
    }

    /// Reset processor state (call when starting new recording session)
    func reset() {
        lastPacketIndex = -1
        lastFrameId = -1
        pendingFrame = []
        framesBuffer = []
        decoder?.reset()
        logger.debug("Processor reset")
    }

    /// Get processing statistics
    func getStatistics() -> (frames: Int, bytes: Int, lostPackets: Int) {
        (totalFramesProcessed, totalBytesProcessed, lostPackets)
    }

    // MARK: - Private Methods

    /// Process pre-framed data (Fieldy uses 40-byte Opus frames, Friend Pendant uses 30-byte LC3 frames)
    private func processFramedData(_ data: Data) {
        // Determine frame size based on codec
        let frameSize: Int
        switch codec {
        case .opusFS320:
            frameSize = 40 // Fieldy Opus frames
        case .lc3FS1030:
            frameSize = 30 // Friend Pendant LC3 frames
        default:
            frameSize = data.count // Treat as single frame
        }

        // Extract frames from data
        var offset = 0
        while offset + frameSize <= data.count {
            let frameData = data.subdata(in: offset..<(offset + frameSize))
            processFrame(frameData)
            offset += frameSize
        }

        // Handle remaining bytes (partial frame)
        if offset < data.count {
            logger.debug("Partial frame: \(data.count - offset) bytes remaining")
        }
    }

    /// Process packet data with frame reassembly
    /// Ported from Flutter's WavBytesUtil.storeFramePacket()
    private func processPacketData(_ data: Data) {
        // Minimum packet structure: 2 bytes index + 1 byte frame ID + content
        guard data.count >= 3 else {
            logger.debug("Packet too small: \(data.count) bytes")
            return
        }

        // Parse packet header
        // Format: [index_low, index_high, frame_id, ...content...]
        let packetIndex = Int(data[0]) | (Int(data[1]) << 8)
        let frameId = Int(data[2])
        let content = Array(data.dropFirst(3))

        // Detect lost packets
        if lastPacketIndex >= 0 && packetIndex != lastPacketIndex + 1 {
            let lost = packetIndex - lastPacketIndex - 1
            if lost > 0 && lost < 100 { // Sanity check
                lostPackets += lost
                logger.debug("Lost \(lost) packets (index jump from \(self.lastPacketIndex) to \(packetIndex))")
            }
            // Reset state on packet loss
            pendingFrame = []
            lastFrameId = -1
        }

        lastPacketIndex = packetIndex

        // Frame reassembly logic
        if frameId == 0 {
            // Start of new frame
            if !pendingFrame.isEmpty {
                // Save previous frame
                completeFrame(pendingFrame)
            }
            pendingFrame = content
            lastFrameId = 0
        } else if frameId == lastFrameId + 1 {
            // Continuation of current frame
            pendingFrame.append(contentsOf: content)
            lastFrameId = frameId
        } else {
            // Frame ID mismatch - reset
            logger.debug("Frame ID mismatch: expected \(self.lastFrameId + 1), got \(frameId)")
            pendingFrame = []
            lastFrameId = -1
        }

        // Check if frame is complete based on expected size
        let expectedFrameSize = codec.frameLengthInBytes
        if pendingFrame.count >= expectedFrameSize {
            completeFrame(pendingFrame)
            pendingFrame = []
            lastFrameId = -1
        }
    }

    /// Complete a reassembled frame
    private func completeFrame(_ frameBytes: [UInt8]) {
        guard !frameBytes.isEmpty else { return }

        totalFramesProcessed += 1
        framesBuffer.append(frameBytes)

        // Decode and deliver
        let frameData = Data(frameBytes)
        if let decoder = decoder {
            if let samples = decoder.decode(frameData) {
                deliverSamples(samples)
            }
        }
    }

    /// Deliver decoded samples to delegate and publisher
    private func deliverSamples(_ samples: [Int16]) {
        guard !samples.isEmpty else { return }

        // Send to publisher
        pcmSamplesSubject.send(samples)

        // Send to delegate
        delegate?.bleAudioProcessor(self, didDecodeSamples: samples)
    }
}

// MARK: - Audio Data Utilities

extension BleAudioProcessor {

    /// Convert PCM samples to Data (little-endian Int16)
    static func samplesToData(_ samples: [Int16]) -> Data {
        var data = Data(capacity: samples.count * 2)
        for sample in samples {
            var s = sample
            data.append(Data(bytes: &s, count: 2))
        }
        return data
    }

    /// Convert Data to PCM samples (little-endian Int16)
    static func dataToSamples(_ data: Data) -> [Int16] {
        let count = data.count / 2
        var samples = [Int16](repeating: 0, count: count)
        data.withUnsafeBytes { bytes in
            let int16Ptr = bytes.bindMemory(to: Int16.self)
            for i in 0..<count {
                samples[i] = int16Ptr[i]
            }
        }
        return samples
    }

    /// Create WAV header for PCM data
    static func createWavHeader(dataLength: Int, sampleRate: Int = 16000, channels: Int = 1, bitsPerSample: Int = 16) -> Data {
        var header = Data(capacity: 44)

        let byteRate = sampleRate * channels * (bitsPerSample / 8)
        let blockAlign = channels * (bitsPerSample / 8)

        // RIFF header
        header.append(contentsOf: "RIFF".utf8)
        header.append(contentsOf: withUnsafeBytes(of: UInt32(36 + dataLength).littleEndian) { Array($0) })
        header.append(contentsOf: "WAVE".utf8)

        // fmt subchunk
        header.append(contentsOf: "fmt ".utf8)
        header.append(contentsOf: withUnsafeBytes(of: UInt32(16).littleEndian) { Array($0) }) // Subchunk1Size
        header.append(contentsOf: withUnsafeBytes(of: UInt16(1).littleEndian) { Array($0) }) // AudioFormat (PCM)
        header.append(contentsOf: withUnsafeBytes(of: UInt16(channels).littleEndian) { Array($0) })
        header.append(contentsOf: withUnsafeBytes(of: UInt32(sampleRate).littleEndian) { Array($0) })
        header.append(contentsOf: withUnsafeBytes(of: UInt32(byteRate).littleEndian) { Array($0) })
        header.append(contentsOf: withUnsafeBytes(of: UInt16(blockAlign).littleEndian) { Array($0) })
        header.append(contentsOf: withUnsafeBytes(of: UInt16(bitsPerSample).littleEndian) { Array($0) })

        // data subchunk
        header.append(contentsOf: "data".utf8)
        header.append(contentsOf: withUnsafeBytes(of: UInt32(dataLength).littleEndian) { Array($0) })

        return header
    }

    /// Create complete WAV file data from PCM samples
    static func createWavData(samples: [Int16], sampleRate: Int = 16000, channels: Int = 1) -> Data {
        let pcmData = samplesToData(samples)
        let header = createWavHeader(dataLength: pcmData.count, sampleRate: sampleRate, channels: channels)
        return header + pcmData
    }
}

// MARK: - Integration with Device Connections

extension BleAudioProcessor {

    /// Create a processor for a specific device type
    static func forDevice(_ deviceType: DeviceType) -> BleAudioProcessor {
        // Default codec based on device type
        let defaultCodec: BleAudioCodec
        switch deviceType {
        case .omi, .openglass:
            defaultCodec = .opus // Will be updated after reading from device
        case .plaud, .limitless:
            defaultCodec = .opusFS320
        case .bee:
            defaultCodec = .aac
        case .fieldy:
            defaultCodec = .opusFS320
        case .friendPendant:
            defaultCodec = .lc3FS1030
        case .frame, .appleWatch:
            defaultCodec = .pcm16
        }

        return BleAudioProcessor(codec: defaultCodec)
    }
}
