import Foundation
import AVFoundation
import CoreAudio

/// Service for capturing system audio using Core Audio Taps (macOS 14.4+)
/// Captures all system audio output and converts to 16-bit PCM at 16kHz for transcription
@available(macOS 14.4, *)
class SystemAudioCaptureService {

    // MARK: - Types

    /// Callback for receiving audio chunks
    typealias AudioChunkHandler = (Data) -> Void

    /// Callback for receiving audio levels (0.0 - 1.0)
    typealias AudioLevelHandler = (Float) -> Void

    enum SystemAudioCaptureError: LocalizedError {
        case tapCreationFailed(OSStatus)
        case aggregateDeviceFailed(OSStatus)
        case ioProcCreationFailed(OSStatus)
        case deviceStartFailed(OSStatus)
        case formatError
        case converterCreationFailed
        case unsupportedOS

        var errorDescription: String? {
            switch self {
            case .tapCreationFailed(let status):
                return "Failed to create process tap: \(status)"
            case .aggregateDeviceFailed(let status):
                return "Failed to create aggregate device: \(status)"
            case .ioProcCreationFailed(let status):
                return "Failed to create IO proc: \(status)"
            case .deviceStartFailed(let status):
                return "Failed to start audio device: \(status)"
            case .formatError:
                return "Failed to get audio format"
            case .converterCreationFailed:
                return "Failed to create audio converter"
            case .unsupportedOS:
                return "System audio capture requires macOS 14.4 or later"
            }
        }
    }

    // MARK: - Properties

    private var tapID: AudioObjectID = kAudioObjectUnknown
    private var aggregateDeviceID: AudioObjectID = kAudioObjectUnknown
    private var ioProcID: AudioDeviceIOProcID?
    private var isCapturing = false
    private var onAudioChunk: AudioChunkHandler?
    private var onAudioLevel: AudioLevelHandler?

    /// Target sample rate for DeepGram
    private let targetSampleRate: Double = 16000

    // Resampling
    private var audioConverter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var sourceSampleRate: Double = 0.0

    // Tap UUID for identification
    private let tapUUID = UUID()

    // MARK: - Permission Checking

    /// Check if system audio capture permission is available
    /// Note: Core Audio Taps don't have a preflight API like screen capture.
    /// Permission is granted implicitly on first use, or may require entitlements.
    static func checkPermission() -> Bool {
        // For Core Audio Taps, there's no explicit permission API.
        // The system will prompt when we first try to create a tap.
        // Return true to indicate we can attempt capture.
        return true
    }

    /// Request system audio capture permission
    /// Returns true if permission is available (macOS 14.4+)
    static func requestPermission() async -> Bool {
        // Core Audio Taps permission is handled at capture time
        return true
    }

    // MARK: - Public Methods

    /// Start capturing system audio
    /// - Parameters:
    ///   - onAudioChunk: Callback receiving 16-bit PCM audio data chunks at 16kHz mono
    ///   - onAudioLevel: Optional callback receiving normalized audio level (0.0 - 1.0)
    func startCapture(onAudioChunk: @escaping AudioChunkHandler, onAudioLevel: AudioLevelHandler? = nil) throws {
        guard !isCapturing else {
            log("SystemAudioCapture: Already capturing")
            return
        }

        self.onAudioChunk = onAudioChunk
        self.onAudioLevel = onAudioLevel

        // 1. Create tap description for all system audio
        let tapDescription = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        tapDescription.uuid = tapUUID
        tapDescription.name = "OMI System Audio Tap"
        tapDescription.muteBehavior = .unmuted  // Don't mute playback

        // 2. Create the process tap
        var status = AudioHardwareCreateProcessTap(tapDescription, &tapID)
        guard status == noErr else {
            throw SystemAudioCaptureError.tapCreationFailed(status)
        }
        log("SystemAudioCapture: Created tap with ID \(tapID)")

        // 3. Create aggregate device with tap
        let aggregateDescription: [String: Any] = [
            kAudioAggregateDeviceNameKey as String: "OMI System Audio Tap Device",
            kAudioAggregateDeviceUIDKey as String: "omi.systemaudio.\(tapUUID.uuidString)",
            kAudioAggregateDeviceIsPrivateKey as String: true,
            kAudioAggregateDeviceTapListKey as String: [
                [kAudioSubTapUIDKey as String: tapUUID.uuidString]
            ],
            kAudioAggregateDeviceTapAutoStartKey as String: true
        ]

        status = AudioHardwareCreateAggregateDevice(aggregateDescription as CFDictionary, &aggregateDeviceID)
        guard status == noErr else {
            cleanupTap()
            throw SystemAudioCaptureError.aggregateDeviceFailed(status)
        }
        log("SystemAudioCapture: Created aggregate device with ID \(aggregateDeviceID)")

        // 4. Get audio format from the tap
        guard let format = getStreamFormat(for: aggregateDeviceID) else {
            cleanup()
            throw SystemAudioCaptureError.formatError
        }

        sourceSampleRate = format.mSampleRate
        log("SystemAudioCapture: Source format - \(format.mSampleRate)Hz, \(format.mChannelsPerFrame) channels, \(format.mBitsPerChannel) bits")

        // 5. Create AVAudioFormat for conversion
        guard let inputFmt = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: format.mSampleRate,
            channels: AVAudioChannelCount(format.mChannelsPerFrame),
            interleaved: false
        ) else {
            cleanup()
            throw SystemAudioCaptureError.formatError
        }
        self.inputFormat = inputFmt

        // Target format: 16kHz mono Float32 (we'll convert to Int16 manually)
        guard let targetFmt = AVAudioFormat(
            standardFormatWithSampleRate: targetSampleRate,
            channels: 1
        ) else {
            cleanup()
            throw SystemAudioCaptureError.converterCreationFailed
        }
        self.targetFormat = targetFmt

        // Create audio converter for resampling
        guard let converter = AVAudioConverter(from: inputFmt, to: targetFmt) else {
            cleanup()
            throw SystemAudioCaptureError.converterCreationFailed
        }
        self.audioConverter = converter

        // 6. Create IO proc for audio callbacks
        status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateDeviceID, nil) {
            [weak self] inNow, inInputData, inInputTime, outOutputData, inOutputTime in
            self?.handleAudioInput(inInputData, timestamp: inInputTime)
        }

        guard status == noErr else {
            cleanup()
            throw SystemAudioCaptureError.ioProcCreationFailed(status)
        }

        // 7. Start the device
        status = AudioDeviceStart(aggregateDeviceID, ioProcID)
        guard status == noErr else {
            cleanup()
            throw SystemAudioCaptureError.deviceStartFailed(status)
        }

        isCapturing = true
        log("SystemAudioCapture: Started capturing system audio")
    }

    /// Stop capturing system audio
    func stopCapture() {
        guard isCapturing else { return }
        cleanup()
        isCapturing = false
        onAudioChunk = nil
        onAudioLevel = nil
        log("SystemAudioCapture: Stopped capturing")
    }

    /// Check if currently capturing
    var capturing: Bool {
        return isCapturing
    }

    // MARK: - Private Methods

    /// Get stream format for a device
    private func getStreamFormat(for deviceID: AudioObjectID) -> AudioStreamBasicDescription? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )

        var format = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)

        let status = AudioObjectGetPropertyData(
            deviceID,
            &address,
            0,
            nil,
            &size,
            &format
        )

        return status == noErr ? format : nil
    }

    /// Handle incoming audio data from the tap
    private func handleAudioInput(_ inputData: UnsafePointer<AudioBufferList>?, timestamp: UnsafePointer<AudioTimeStamp>?) {
        guard isCapturing,
              let bufferList = inputData?.pointee,
              let converter = audioConverter,
              let targetFmt = targetFormat else { return }

        // Get the first buffer (interleaved or first channel)
        let buffer = bufferList.mBuffers

        guard let data = buffer.mData, buffer.mDataByteSize > 0 else { return }

        // Calculate frame count
        let bytesPerFrame = UInt32(MemoryLayout<Float32>.size) * buffer.mNumberChannels
        let frameCount = buffer.mDataByteSize / bytesPerFrame

        guard frameCount > 0 else { return }

        // Create input AVAudioPCMBuffer
        guard let inputFmt = inputFormat,
              let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFmt, frameCapacity: frameCount) else { return }

        inputBuffer.frameLength = frameCount

        // Copy data to input buffer
        // System audio is typically interleaved stereo Float32
        let srcPtr = data.assumingMemoryBound(to: Float32.self)
        let channelCount = Int(buffer.mNumberChannels)

        if channelCount >= 2 {
            // Mix stereo to mono by averaging channels
            guard let floatData = inputBuffer.floatChannelData else { return }
            let monoPtr = floatData[0]

            for i in 0..<Int(frameCount) {
                let left = srcPtr[i * channelCount]
                let right = srcPtr[i * channelCount + 1]
                monoPtr[i] = (left + right) / 2.0
            }
        } else {
            // Already mono, just copy
            guard let floatData = inputBuffer.floatChannelData else { return }
            memcpy(floatData[0], srcPtr, Int(buffer.mDataByteSize))
        }

        // Calculate output frame count based on sample rate conversion
        let outputFrameCapacity = AVAudioFrameCount(ceil(Double(frameCount) * targetSampleRate / sourceSampleRate))
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFmt, frameCapacity: outputFrameCapacity) else { return }

        // Convert using input block pattern
        var error: NSError?
        var hasConsumedInput = false

        let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
            if hasConsumedInput {
                outStatus.pointee = .noDataNow
                return nil
            }
            hasConsumedInput = true
            outStatus.pointee = .haveData
            return inputBuffer
        }

        converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

        if let error = error {
            logError("SystemAudioCapture: Conversion error", error: error)
            return
        }

        // Convert Float32 to Int16 (linear16 PCM for DeepGram)
        guard let channelData = outputBuffer.floatChannelData?[0] else { return }

        let processedFrameLength = Int(outputBuffer.frameLength)
        var pcmData = [Int16]()
        pcmData.reserveCapacity(processedFrameLength)

        for i in 0..<processedFrameLength {
            let sample = channelData[i]
            // Clamp and convert to Int16 range (-32768 to 32767)
            let pcmSample = Int16(max(-32768, min(32767, sample * 32767)))
            pcmData.append(pcmSample)
        }

        // Convert to Data
        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        // Calculate and report audio level (RMS normalized to 0.0 - 1.0)
        if let levelHandler = onAudioLevel, !pcmData.isEmpty {
            let sumOfSquares: Float = pcmData.reduce(0.0) { acc, sample in
                let normalized = Float(sample) / 32767.0
                return acc + normalized * normalized
            }
            let rms = sqrt(sumOfSquares / Float(pcmData.count))
            // Clamp to 0.0 - 1.0 range
            let level = min(Float(1.0), max(Float(0.0), rms))
            DispatchQueue.main.async {
                levelHandler(level)
            }
        }

        // Send to callback
        onAudioChunk?(byteData)
    }

    /// Clean up tap resources
    private func cleanupTap() {
        if tapID != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = kAudioObjectUnknown
        }
    }

    /// Clean up all resources
    private func cleanup() {
        if let procID = ioProcID, aggregateDeviceID != kAudioObjectUnknown {
            AudioDeviceStop(aggregateDeviceID, procID)
            AudioDeviceDestroyIOProcID(aggregateDeviceID, procID)
            ioProcID = nil
        }

        if aggregateDeviceID != kAudioObjectUnknown {
            AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = kAudioObjectUnknown
        }

        cleanupTap()

        audioConverter = nil
        inputFormat = nil
        targetFormat = nil
        sourceSampleRate = 0.0
    }

    deinit {
        cleanup()
    }
}
