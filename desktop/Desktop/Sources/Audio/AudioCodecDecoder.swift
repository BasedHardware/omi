import AudioToolbox
import AVFoundation
import Foundation
import os.log

// MARK: - Audio Decoder Protocol

/// Protocol for audio codec decoders
/// Converts encoded audio data to PCM samples
protocol AudioCodecDecoder: AnyObject {
    /// The codec this decoder handles
    var codec: BleAudioCodec { get }

    /// Output sample rate in Hz
    var outputSampleRate: Int { get }

    /// Output channels (1 = mono, 2 = stereo)
    var outputChannels: Int { get }

    /// Decode a single frame of audio data
    /// - Parameter data: Encoded audio frame
    /// - Returns: PCM samples as Int16 array, or nil if decoding failed
    func decode(_ data: Data) -> [Int16]?

    /// Decode multiple frames of audio data
    /// - Parameter frames: Array of encoded audio frames
    /// - Returns: Combined PCM samples as Int16 array
    func decodeFrames(_ frames: [Data]) -> [Int16]

    /// Reset decoder state (call when starting new audio stream)
    func reset()
}

// MARK: - Default Implementation

extension AudioCodecDecoder {
    func decodeFrames(_ frames: [Data]) -> [Int16] {
        var allSamples = [Int16]()
        for frame in frames {
            if let samples = decode(frame) {
                allSamples.append(contentsOf: samples)
            }
        }
        return allSamples
    }
}

// MARK: - PCM Passthrough Decoder

/// Passthrough decoder for PCM audio (no decoding needed)
final class PCMPassthroughDecoder: AudioCodecDecoder {
    let codec: BleAudioCodec
    let outputSampleRate: Int
    let outputChannels: Int

    private let logger = Logger(subsystem: "me.omi.desktop", category: "PCMPassthroughDecoder")
    private let bitDepth: Int

    init(codec: BleAudioCodec) {
        self.codec = codec
        self.outputSampleRate = codec.sampleRate
        self.outputChannels = 1
        self.bitDepth = codec.bitDepth
    }

    func decode(_ data: Data) -> [Int16]? {
        guard !data.isEmpty else { return nil }

        if bitDepth == 16 {
            // 16-bit PCM: direct conversion
            let count = data.count / 2
            var samples = [Int16](repeating: 0, count: count)
            data.withUnsafeBytes { bytes in
                let int16Ptr = bytes.bindMemory(to: Int16.self)
                for i in 0..<count {
                    samples[i] = int16Ptr[i]
                }
            }
            return samples
        } else {
            // 8-bit PCM: convert to 16-bit
            var samples = [Int16](repeating: 0, count: data.count)
            for (i, byte) in data.enumerated() {
                // Convert unsigned 8-bit to signed 16-bit
                let signed = Int16(byte) - 128
                samples[i] = signed * 256
            }
            return samples
        }
    }

    func reset() {
        // No state to reset for PCM passthrough
    }
}

// MARK: - Opus Decoder

/// Opus audio decoder using AudioToolbox
/// Supports both standard Opus (100fps) and OpusFS320 (50fps)
final class OpusAudioDecoder: AudioCodecDecoder {
    let codec: BleAudioCodec
    let outputSampleRate: Int = 16000
    let outputChannels: Int = 1

    private let logger = Logger(subsystem: "me.omi.desktop", category: "OpusAudioDecoder")
    private var audioConverter: AudioConverterRef?
    private var inputBuffer: Data = Data()
    private var isInitialized = false

    // Opus frame parameters
    private let frameSize: Int
    private let frameDuration: Double // in seconds

    init(codec: BleAudioCodec) {
        self.codec = codec

        // OpusFS320 uses 320-sample frames (20ms at 16kHz), standard uses 160-sample frames (10ms)
        if codec == .opusFS320 {
            self.frameSize = 320
            self.frameDuration = 0.02 // 20ms
        } else {
            self.frameSize = 160
            self.frameDuration = 0.01 // 10ms
        }

        setupDecoder()
    }

    deinit {
        if let converter = audioConverter {
            AudioConverterDispose(converter)
        }
    }

    private func setupDecoder() {
        // Input format: Opus
        var inputFormat = AudioStreamBasicDescription(
            mSampleRate: Float64(outputSampleRate),
            mFormatID: kAudioFormatOpus,
            mFormatFlags: 0,
            mBytesPerPacket: 0, // Variable
            mFramesPerPacket: UInt32(frameSize),
            mBytesPerFrame: 0,
            mChannelsPerFrame: UInt32(outputChannels),
            mBitsPerChannel: 0,
            mReserved: 0
        )

        // Output format: Linear PCM 16-bit
        var outputFormat = AudioStreamBasicDescription(
            mSampleRate: Float64(outputSampleRate),
            mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
            mBytesPerPacket: 2 * UInt32(outputChannels),
            mFramesPerPacket: 1,
            mBytesPerFrame: 2 * UInt32(outputChannels),
            mChannelsPerFrame: UInt32(outputChannels),
            mBitsPerChannel: 16,
            mReserved: 0
        )

        let status = AudioConverterNew(&inputFormat, &outputFormat, &audioConverter)
        if status != noErr {
            logger.error("Failed to create Opus audio converter: \(status)")
            return
        }

        isInitialized = true
        logger.debug("Opus decoder initialized for \(self.codec.name)")
    }

    func decode(_ data: Data) -> [Int16]? {
        guard isInitialized, let converter = audioConverter else {
            logger.warning("Opus decoder not initialized")
            return nil
        }

        guard !data.isEmpty else { return nil }

        // Validate Opus TOC byte
        let tocByte = data[0]
        if !isValidOpusToc(tocByte) {
            logger.debug("Invalid Opus TOC byte: 0x\(String(format: "%02x", tocByte))")
            // Still try to decode - might be valid
        }

        // Prepare output buffer
        var outputSamples = [Int16](repeating: 0, count: frameSize * outputChannels)
        let outputSize = UInt32(outputSamples.count * 2)

        // Prepare input packet description
        var packetDescription = AudioStreamPacketDescription(
            mStartOffset: 0,
            mVariableFramesInPacket: UInt32(frameSize),
            mDataByteSize: UInt32(data.count)
        )

        // Decode using withUnsafeMutableBytes for proper pointer lifetime
        var ioOutputDataPacketSize = UInt32(frameSize)
        var decodedByteSize: UInt32 = 0

        let status = outputSamples.withUnsafeMutableBytes { outputBuffer -> OSStatus in
            var outputBufferList = AudioBufferList(
                mNumberBuffers: 1,
                mBuffers: AudioBuffer(
                    mNumberChannels: UInt32(outputChannels),
                    mDataByteSize: outputSize,
                    mData: outputBuffer.baseAddress
                )
            )

            let result = data.withUnsafeBytes { inputBytes -> OSStatus in
                return withUnsafeMutablePointer(to: &packetDescription) { packetDescPtr in
                    var context = (inputBytes.baseAddress, UInt32(data.count), packetDescPtr)

                    return withUnsafeMutablePointer(to: &context) { contextPtr in
                        AudioConverterFillComplexBuffer(
                            converter,
                            { (_, ioNumberDataPackets, ioData, outDataPacketDescription, inUserData) -> OSStatus in
                                // This callback provides input data to the converter
                                guard let userData = inUserData else { return -1 }
                                let context = userData.assumingMemoryBound(to: (UnsafeRawPointer?, UInt32, UnsafeMutablePointer<AudioStreamPacketDescription>).self)

                                ioData.pointee.mBuffers.mData = UnsafeMutableRawPointer(mutating: context.pointee.0)
                                ioData.pointee.mBuffers.mDataByteSize = context.pointee.1
                                ioData.pointee.mBuffers.mNumberChannels = 1
                                ioNumberDataPackets.pointee = 1

                                if let outDesc = outDataPacketDescription {
                                    outDesc.pointee = context.pointee.2
                                }

                                return noErr
                            },
                            contextPtr,
                            &ioOutputDataPacketSize,
                            &outputBufferList,
                            nil
                        )
                    }
                }
            }
            decodedByteSize = outputBufferList.mBuffers.mDataByteSize
            return result
        }

        if status != noErr && status != kAudioConverterErr_InvalidInputSize {
            logger.debug("Opus decode failed with status: \(status)")
            return nil
        }

        // Return only the decoded samples
        let decodedCount = Int(decodedByteSize) / 2
        return Array(outputSamples.prefix(decodedCount))
    }

    func reset() {
        if let converter = audioConverter {
            AudioConverterReset(converter)
        }
        inputBuffer = Data()
    }

    /// Check if byte is a valid Opus TOC byte
    private func isValidOpusToc(_ byte: UInt8) -> Bool {
        // Common Opus TOC bytes for speech at 16kHz
        // 0x78, 0xb8, 0xf8 = SILK mode
        // 0x70, 0xb0, 0xf0 = Hybrid mode
        return [0x78, 0xb8, 0xf8, 0x70, 0xb0, 0xf0].contains(byte)
    }
}

// MARK: - AAC Decoder

/// AAC audio decoder using AudioToolbox
/// Handles ADTS-framed AAC audio from Bee devices
final class AACAudioDecoder: AudioCodecDecoder {
    let codec: BleAudioCodec = .aac
    let outputSampleRate: Int = 16000
    let outputChannels: Int = 1

    private let logger = Logger(subsystem: "me.omi.desktop", category: "AACAudioDecoder")
    private var audioConverter: AudioConverterRef?
    private var isInitialized = false

    init() {
        setupDecoder()
    }

    deinit {
        if let converter = audioConverter {
            AudioConverterDispose(converter)
        }
    }

    private func setupDecoder() {
        // Input format: AAC
        var inputFormat = AudioStreamBasicDescription(
            mSampleRate: Float64(outputSampleRate),
            mFormatID: kAudioFormatMPEG4AAC,
            mFormatFlags: 0,
            mBytesPerPacket: 0, // Variable
            mFramesPerPacket: 1024, // AAC frame size
            mBytesPerFrame: 0,
            mChannelsPerFrame: UInt32(outputChannels),
            mBitsPerChannel: 0,
            mReserved: 0
        )

        // Output format: Linear PCM 16-bit
        var outputFormat = AudioStreamBasicDescription(
            mSampleRate: Float64(outputSampleRate),
            mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
            mBytesPerPacket: 2 * UInt32(outputChannels),
            mFramesPerPacket: 1,
            mBytesPerFrame: 2 * UInt32(outputChannels),
            mChannelsPerFrame: UInt32(outputChannels),
            mBitsPerChannel: 16,
            mReserved: 0
        )

        let status = AudioConverterNew(&inputFormat, &outputFormat, &audioConverter)
        if status != noErr {
            logger.error("Failed to create AAC audio converter: \(status)")
            return
        }

        isInitialized = true
        logger.debug("AAC decoder initialized")
    }

    func decode(_ data: Data) -> [Int16]? {
        guard isInitialized, let converter = audioConverter else {
            logger.warning("AAC decoder not initialized")
            return nil
        }

        guard data.count >= 7 else { return nil }

        // Validate ADTS sync word
        guard data[0] == 0xFF, (data[1] & 0xF0) == 0xF0 else {
            logger.debug("Invalid ADTS sync word")
            return nil
        }

        // Extract frame length from ADTS header
        let frameLength = (Int(data[3] & 0x03) << 11) |
                         (Int(data[4]) << 3) |
                         (Int(data[5] & 0xE0) >> 5)

        guard data.count >= frameLength else {
            logger.debug("Incomplete ADTS frame: have \(data.count), need \(frameLength)")
            return nil
        }

        // Prepare output buffer (AAC typically decodes to 1024 samples per frame)
        let aacFrameSize = 1024
        var outputSamples = [Int16](repeating: 0, count: aacFrameSize * outputChannels)
        let outputSize = UInt32(outputSamples.count * 2)

        // Prepare input packet description (skip 7-byte ADTS header for raw AAC)
        let rawAACOffset = 7
        let rawAACData = data.subdata(in: rawAACOffset..<frameLength)

        var packetDescription = AudioStreamPacketDescription(
            mStartOffset: 0,
            mVariableFramesInPacket: UInt32(aacFrameSize),
            mDataByteSize: UInt32(rawAACData.count)
        )

        // Decode using withUnsafeMutableBytes for proper pointer lifetime
        var ioOutputDataPacketSize = UInt32(aacFrameSize)
        var decodedByteSize: UInt32 = 0

        let status = outputSamples.withUnsafeMutableBytes { outputBuffer -> OSStatus in
            var outputBufferList = AudioBufferList(
                mNumberBuffers: 1,
                mBuffers: AudioBuffer(
                    mNumberChannels: UInt32(outputChannels),
                    mDataByteSize: outputSize,
                    mData: outputBuffer.baseAddress
                )
            )

            let result = rawAACData.withUnsafeBytes { inputBytes -> OSStatus in
                return withUnsafeMutablePointer(to: &packetDescription) { packetDescPtr in
                    var context = (inputBytes.baseAddress, UInt32(rawAACData.count), packetDescPtr)

                    return withUnsafeMutablePointer(to: &context) { contextPtr in
                        AudioConverterFillComplexBuffer(
                            converter,
                            { (_, ioNumberDataPackets, ioData, outDataPacketDescription, inUserData) -> OSStatus in
                                guard let userData = inUserData else { return -1 }
                                let context = userData.assumingMemoryBound(to: (UnsafeRawPointer?, UInt32, UnsafeMutablePointer<AudioStreamPacketDescription>).self)

                                ioData.pointee.mBuffers.mData = UnsafeMutableRawPointer(mutating: context.pointee.0)
                                ioData.pointee.mBuffers.mDataByteSize = context.pointee.1
                                ioData.pointee.mBuffers.mNumberChannels = 1
                                ioNumberDataPackets.pointee = 1

                                if let outDesc = outDataPacketDescription {
                                    outDesc.pointee = context.pointee.2
                                }

                                return noErr
                            },
                            contextPtr,
                            &ioOutputDataPacketSize,
                            &outputBufferList,
                            nil
                        )
                    }
                }
            }
            decodedByteSize = outputBufferList.mBuffers.mDataByteSize
            return result
        }

        if status != noErr {
            logger.debug("AAC decode failed with status: \(status)")
            return nil
        }

        let decodedCount = Int(decodedByteSize) / 2
        return Array(outputSamples.prefix(decodedCount))
    }

    func reset() {
        if let converter = audioConverter {
            AudioConverterReset(converter)
        }
    }
}

// MARK: - Mulaw Decoder

/// µ-law audio decoder
/// Converts µ-law encoded audio to linear PCM
/// Uses standard ITU-T G.711 µ-law expansion
final class MulawAudioDecoder: AudioCodecDecoder {
    let codec: BleAudioCodec
    let outputSampleRate: Int = 16000
    let outputChannels: Int = 1

    private let logger = Logger(subsystem: "me.omi.desktop", category: "MulawAudioDecoder")

    /// µ-law to linear PCM lookup table (pre-computed for speed)
    private static let mulawToLinear: [Int16] = {
        var table = [Int16](repeating: 0, count: 256)
        for i in 0..<256 {
            let mulaw = UInt8(i)
            // Invert all bits
            let inverted = ~mulaw
            // Extract sign, exponent, and mantissa
            let sign = Int16((inverted & 0x80) >> 7)
            let exponent = Int16((inverted & 0x70) >> 4)
            let mantissa = Int16(inverted & 0x0F)

            // Compute linear value
            var linear = ((mantissa << 3) + 0x84) << exponent
            linear -= 0x84

            // Apply sign
            table[i] = sign == 1 ? -linear : linear
        }
        return table
    }()

    init(codec: BleAudioCodec) {
        self.codec = codec
    }

    func decode(_ data: Data) -> [Int16]? {
        guard !data.isEmpty else { return nil }

        var samples = [Int16](repeating: 0, count: data.count)
        for (i, byte) in data.enumerated() {
            samples[i] = Self.mulawToLinear[Int(byte)]
        }
        return samples
    }

    func reset() {
        // No state to reset
    }
}

// MARK: - LC3 Decoder (Placeholder)

/// LC3 audio decoder placeholder
/// LC3 (Low Complexity Communication Codec) is used by Friend Pendant
/// Full implementation requires liblc3 external library
///
/// To implement LC3 decoding:
/// 1. Add liblc3 as a Swift Package dependency or include as bridging header
/// 2. Initialize LC3 decoder with: lc3_setup_decoder(frame_duration_us, sample_rate, sr_pcm, mem)
/// 3. Decode frames with: lc3_decode(decoder, input, input_size, format, output, stride)
///
/// Frame parameters for Friend Pendant:
/// - Frame duration: 10ms (10000 µs)
/// - Sample rate: 16000 Hz
/// - Frame size: 30 bytes
/// - Output samples per frame: 160 (16000 * 0.01)
final class LC3AudioDecoder: AudioCodecDecoder {
    let codec: BleAudioCodec = .lc3FS1030
    let outputSampleRate: Int = 16000
    let outputChannels: Int = 1

    private let logger = Logger(subsystem: "me.omi.desktop", category: "LC3AudioDecoder")
    private let frameDurationMs: Int = 10
    private let frameSize: Int = 30
    private let samplesPerFrame: Int = 160

    init() {
        logger.warning("LC3 decoder not fully implemented - requires liblc3 library")
    }

    func decode(_ data: Data) -> [Int16]? {
        // LC3 decoding requires external liblc3 library
        // For now, return silence to prevent audio gaps
        logger.debug("LC3 decode called with \(data.count) bytes - returning silence")

        // Return silence samples matching expected output size
        let expectedSamples = (data.count / frameSize) * samplesPerFrame
        return [Int16](repeating: 0, count: max(expectedSamples, samplesPerFrame))
    }

    func reset() {
        // Would reset LC3 decoder state here
    }
}

// MARK: - Decoder Factory

/// Factory for creating audio decoders based on codec type
enum AudioDecoderFactory {

    /// Create a decoder for the specified codec
    /// - Parameter codec: The audio codec to decode
    /// - Returns: An appropriate decoder, or nil if codec is not supported
    static func createDecoder(for codec: BleAudioCodec) -> AudioCodecDecoder? {
        switch codec {
        case .pcm8, .pcm16:
            return PCMPassthroughDecoder(codec: codec)

        case .opus, .opusFS320:
            return OpusAudioDecoder(codec: codec)

        case .aac:
            return AACAudioDecoder()

        case .lc3FS1030:
            // LC3 decoder returns silence - requires liblc3 for full implementation
            return LC3AudioDecoder()

        case .mulaw8, .mulaw16:
            return MulawAudioDecoder(codec: codec)

        case .unknown:
            return nil
        }
    }

    /// Check if a codec is supported for decoding
    static func isSupported(_ codec: BleAudioCodec) -> Bool {
        switch codec {
        case .pcm8, .pcm16, .opus, .opusFS320, .aac, .mulaw8, .mulaw16:
            return true
        case .lc3FS1030:
            // LC3 returns silence but doesn't crash - partial support
            return true
        case .unknown:
            return false
        }
    }

    /// Check if a codec has full decoding support (not just placeholder)
    static func hasFullSupport(_ codec: BleAudioCodec) -> Bool {
        switch codec {
        case .pcm8, .pcm16, .opus, .opusFS320, .aac, .mulaw8, .mulaw16:
            return true
        case .lc3FS1030, .unknown:
            return false
        }
    }
}
