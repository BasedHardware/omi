import Foundation
import AVFoundation
import CoreAudio

/// Service for capturing microphone audio as 16-bit PCM at 16kHz
/// Uses CoreAudio IOProc directly on the default input device to avoid
/// AVAudioEngine's implicit aggregate device creation, which degrades
/// system audio output quality (especially Bluetooth A2DP → SCO switch).
class AudioCaptureService {

    // MARK: - Types

    /// Callback for receiving audio chunks
    typealias AudioChunkHandler = (Data) -> Void

    /// Callback for receiving audio levels (0.0 - 1.0)
    typealias AudioLevelHandler = (Float) -> Void

    enum AudioCaptureError: LocalizedError {
        case noInputAvailable
        case engineStartFailed(Error)
        case permissionDenied
        case converterCreationFailed

        var errorDescription: String? {
            switch self {
            case .noInputAvailable:
                return "No audio input device available"
            case .engineStartFailed(let error):
                return "Failed to start audio engine: \(error.localizedDescription)"
            case .permissionDenied:
                return "Microphone permission denied"
            case .converterCreationFailed:
                return "Failed to create audio converter"
            }
        }
    }

    // MARK: - Properties

    private var deviceID: AudioDeviceID = kAudioObjectUnknown
    private var ioProcID: AudioDeviceIOProcID?
    private var defaultDeviceListenerBlock: AudioObjectPropertyListenerBlock?
    private var deviceFormatListenerBlock: AudioObjectPropertyListenerBlock?
    private var isCapturing = false
    private var onAudioChunk: AudioChunkHandler?
    private var onAudioLevel: AudioLevelHandler?

    /// Target sample rate for DeepGram
    private let targetSampleRate: Double = 16000

    // Resampling
    private var audioConverter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var detectedSampleRate: Double = 0.0

    // Audio level smoothing (for natural decay like system audio)
    private var smoothedLevel: Float = 0.0
    private let noiseFloor: Float = 0.005  // Very low threshold for preamp noise
    private let decayRate: Float = 0.85    // Decay multiplier per frame (lower = faster decay)

    // Device change handling
    private var isReconfiguring = false
    private let listenerQueue = DispatchQueue(label: "com.omi.audiocapture.listener")

    // MARK: - Public Methods

    /// Check if microphone permission is granted
    static func checkPermission() -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            return true
        case .notDetermined, .denied, .restricted:
            return false
        @unknown default:
            return false
        }
    }

    /// Check if microphone permission was explicitly denied by the user
    static func isPermissionDenied() -> Bool {
        return AVCaptureDevice.authorizationStatus(for: .audio) == .denied
    }

    /// Get the current authorization status
    static func authorizationStatus() -> AVAuthorizationStatus {
        return AVCaptureDevice.authorizationStatus(for: .audio)
    }

    /// Request microphone permission
    static func requestPermission() async -> Bool {
        return await withCheckedContinuation { continuation in
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    /// Start capturing audio from microphone
    /// - Parameters:
    ///   - onAudioChunk: Callback receiving 16-bit PCM audio data chunks at 16kHz
    ///   - onAudioLevel: Optional callback receiving normalized audio level (0.0 - 1.0)
    func startCapture(onAudioChunk: @escaping AudioChunkHandler, onAudioLevel: AudioLevelHandler? = nil) throws {
        guard !isCapturing else {
            log("AudioCapture: Already capturing")
            return
        }

        self.onAudioChunk = onAudioChunk
        self.onAudioLevel = onAudioLevel

        // 1. Get default input device
        var inputDeviceID: AudioDeviceID = kAudioObjectUnknown
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &inputDeviceID
        )

        guard status == noErr, inputDeviceID != kAudioObjectUnknown else {
            throw AudioCaptureError.noInputAvailable
        }
        self.deviceID = inputDeviceID

        // 2. Get device stream format
        guard let streamFormat = getStreamFormat(for: deviceID) else {
            throw AudioCaptureError.noInputAvailable
        }

        detectedSampleRate = streamFormat.mSampleRate
        log("AudioCapture: Hardware format - \(streamFormat.mSampleRate)Hz, \(streamFormat.mChannelsPerFrame) channels")

        // 3. Create mono input format (we mix to mono before conversion)
        guard let inputFmt = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: streamFormat.mSampleRate,
            channels: 1,
            interleaved: false
        ) else {
            throw AudioCaptureError.converterCreationFailed
        }
        self.inputFormat = inputFmt

        // 4. Create target format: Float32 at 16kHz mono
        guard let targetFmt = AVAudioFormat(standardFormatWithSampleRate: targetSampleRate, channels: 1) else {
            throw AudioCaptureError.converterCreationFailed
        }
        self.targetFormat = targetFmt

        log("AudioCapture: Target format - \(targetFmt.sampleRate)Hz, \(targetFmt.channelCount) channels, Float32")

        // 5. Create audio converter for resampling
        guard let converter = AVAudioConverter(from: inputFmt, to: targetFmt) else {
            throw AudioCaptureError.converterCreationFailed
        }
        self.audioConverter = converter

        // 6. Create IOProc on the input device directly (no aggregate device)
        var procID: AudioDeviceIOProcID?
        let ioProcStatus = AudioDeviceCreateIOProcIDWithBlock(&procID, deviceID, nil) {
            [weak self] inNow, inInputData, inInputTime, outOutputData, inOutputTime in
            self?.handleAudioInput(inInputData, timestamp: inInputTime)
        }

        guard ioProcStatus == noErr, let validProcID = procID else {
            throw AudioCaptureError.engineStartFailed(
                NSError(domain: "AudioCapture", code: Int(ioProcStatus),
                        userInfo: [NSLocalizedDescriptionKey: "Failed to create IOProc: \(ioProcStatus)"])
            )
        }
        self.ioProcID = validProcID

        // 7. Start the device
        let startStatus = AudioDeviceStart(deviceID, validProcID)
        guard startStatus == noErr else {
            AudioDeviceDestroyIOProcID(deviceID, validProcID)
            self.ioProcID = nil
            throw AudioCaptureError.engineStartFailed(
                NSError(domain: "AudioCapture", code: Int(startStatus),
                        userInfo: [NSLocalizedDescriptionKey: "Failed to start device: \(startStatus)"])
            )
        }

        isCapturing = true
        log("AudioCapture: Started capturing")

        // 8. Install property listeners for device changes
        installPropertyListeners()
    }

    /// Stop capturing audio
    func stopCapture() {
        guard isCapturing else { return }

        removePropertyListeners()

        if let procID = ioProcID, deviceID != kAudioObjectUnknown {
            AudioDeviceStop(deviceID, procID)
            AudioDeviceDestroyIOProcID(deviceID, procID)
            ioProcID = nil
        }

        deviceID = kAudioObjectUnknown
        isCapturing = false
        isReconfiguring = false
        onAudioChunk = nil
        onAudioLevel = nil

        // Clean up converter
        audioConverter = nil
        inputFormat = nil
        targetFormat = nil
        detectedSampleRate = 0.0
        smoothedLevel = 0.0

        log("AudioCapture: Stopped capturing")
    }

    /// Check if currently capturing
    var capturing: Bool {
        return isCapturing
    }

    /// Get the name of the current default input device (microphone)
    static func getCurrentMicrophoneName() -> String? {
        var deviceID: AudioDeviceID = 0
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &deviceID
        )

        guard status == noErr, deviceID != kAudioDeviceUnknown else {
            return nil
        }

        // Get the device name
        var name: Unmanaged<CFString>?
        size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        address.mSelector = kAudioObjectPropertyName

        let nameStatus = AudioObjectGetPropertyData(
            deviceID,
            &address,
            0,
            nil,
            &size,
            &name
        )

        guard nameStatus == noErr, let cfName = name?.takeRetainedValue() else {
            return nil
        }

        return cfName as String
    }

    // MARK: - Private Methods

    /// Get stream format for a device on input scope
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

    /// Handle incoming audio data from the IOProc callback
    private func handleAudioInput(_ inputData: UnsafePointer<AudioBufferList>?, timestamp: UnsafePointer<AudioTimeStamp>?) {
        guard isCapturing,
              let bufferList = inputData?.pointee,
              let converter = audioConverter,
              let targetFmt = targetFormat,
              let inputFmt = inputFormat else { return }

        let buffer = bufferList.mBuffers
        guard let data = buffer.mData, buffer.mDataByteSize > 0 else { return }

        let bytesPerFrame = UInt32(MemoryLayout<Float32>.size) * buffer.mNumberChannels
        let frameCount = buffer.mDataByteSize / bytesPerFrame
        guard frameCount > 0 else { return }

        // Create mono input buffer for converter
        guard let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFmt, frameCapacity: frameCount) else { return }
        inputBuffer.frameLength = frameCount

        let srcPtr = data.assumingMemoryBound(to: Float32.self)
        let channelCount = Int(buffer.mNumberChannels)
        guard let floatData = inputBuffer.floatChannelData else { return }
        let monoPtr = floatData[0]

        if channelCount >= 2 {
            // Mix stereo to mono by averaging channels
            for i in 0..<Int(frameCount) {
                let left = srcPtr[i * channelCount]
                let right = srcPtr[i * channelCount + 1]
                monoPtr[i] = (left + right) / 2.0
            }
        } else {
            // Already mono, just copy
            memcpy(monoPtr, srcPtr, Int(buffer.mDataByteSize))
        }

        // Convert to target format (16kHz mono)
        let outputFrameCapacity = AVAudioFrameCount(ceil(Double(frameCount) * targetSampleRate / detectedSampleRate))
        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFmt, frameCapacity: outputFrameCapacity) else { return }

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
            logError("AudioCapture: Conversion error", error: error)
            return
        }

        // Convert Float32 samples to Int16 (linear16 PCM for DeepGram)
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

        // Convert to Data (little-endian, which is native on Apple platforms)
        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        // Calculate and report audio level (RMS normalized to 0.0 - 1.0)
        // Uses smoothing and decay to match system audio behavior
        if let levelHandler = onAudioLevel, !pcmData.isEmpty {
            let sumOfSquares: Float = pcmData.reduce(0.0) { acc, sample in
                let normalized = Float(sample) / 32767.0
                return acc + normalized * normalized
            }
            let rms = sqrt(sumOfSquares / Float(pcmData.count))

            // Apply soft noise floor - subtract noise but don't hard cutoff
            let cleanedRms = max(0.0, rms - noiseFloor)

            // Smoothing: if current level is higher, jump to it; if lower, decay gradually
            // This matches how system audio naturally behaves and feels more responsive
            if cleanedRms > smoothedLevel {
                // Rising: follow immediately for responsiveness
                smoothedLevel = cleanedRms
            } else {
                // Falling: decay gradually for smooth animation
                smoothedLevel = smoothedLevel * decayRate
                // If decayed level is very small, snap to zero to avoid endless tiny values
                if smoothedLevel < 0.001 {
                    smoothedLevel = 0.0
                }
            }

            let level = min(Float(1.0), smoothedLevel)
            DispatchQueue.main.async {
                levelHandler(level)
            }
        }

        // Send to callback
        onAudioChunk?(byteData)
    }

    // MARK: - Property Listeners

    private func installPropertyListeners() {
        // Listen for default input device changes
        var defaultDeviceAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let deviceBlock: AudioObjectPropertyListenerBlock = { [weak self] numberAddresses, addresses in
            DispatchQueue.main.async {
                self?.handleConfigurationChange()
            }
        }
        self.defaultDeviceListenerBlock = deviceBlock

        AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject),
            &defaultDeviceAddress,
            listenerQueue,
            deviceBlock
        )

        // Listen for format changes on current device
        var formatAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )

        let formatBlock: AudioObjectPropertyListenerBlock = { [weak self] numberAddresses, addresses in
            DispatchQueue.main.async {
                self?.handleConfigurationChange()
            }
        }
        self.deviceFormatListenerBlock = formatBlock

        AudioObjectAddPropertyListenerBlock(
            deviceID,
            &formatAddress,
            listenerQueue,
            formatBlock
        )
    }

    private func removePropertyListeners() {
        if let block = defaultDeviceListenerBlock {
            var address = AudioObjectPropertyAddress(
                mSelector: kAudioHardwarePropertyDefaultInputDevice,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            AudioObjectRemovePropertyListenerBlock(
                AudioObjectID(kAudioObjectSystemObject),
                &address,
                listenerQueue,
                block
            )
            defaultDeviceListenerBlock = nil
        }

        if let block = deviceFormatListenerBlock, deviceID != kAudioObjectUnknown {
            var address = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyStreamFormat,
                mScope: kAudioDevicePropertyScopeInput,
                mElement: kAudioObjectPropertyElementMain
            )
            AudioObjectRemovePropertyListenerBlock(
                deviceID,
                &address,
                listenerQueue,
                block
            )
            deviceFormatListenerBlock = nil
        }
    }

    // MARK: - Device Change Handling

    /// Handle audio configuration change (e.g., user switched microphone)
    private func handleConfigurationChange() {
        guard isCapturing, !isReconfiguring else { return }
        isReconfiguring = true

        log("AudioCapture: Configuration changed, restarting with new device...")

        // Stop IOProc on old device
        if let procID = ioProcID, deviceID != kAudioObjectUnknown {
            AudioDeviceStop(deviceID, procID)
            AudioDeviceDestroyIOProcID(deviceID, procID)
            ioProcID = nil
        }

        // Remove old format listener (device may have changed)
        if let block = deviceFormatListenerBlock, deviceID != kAudioObjectUnknown {
            var address = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyStreamFormat,
                mScope: kAudioDevicePropertyScopeInput,
                mElement: kAudioObjectPropertyElementMain
            )
            AudioObjectRemovePropertyListenerBlock(
                deviceID,
                &address,
                listenerQueue,
                block
            )
            deviceFormatListenerBlock = nil
        }

        // Delay to let the audio hardware settle after device change
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.reconfigureAfterChange(retryCount: 0)
        }
    }

    private static let maxRetries = 3

    private func reconfigureAfterChange(retryCount: Int) {
        // Get new default input device
        var newDeviceID: AudioDeviceID = kAudioObjectUnknown
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &newDeviceID
        )

        guard status == noErr, newDeviceID != kAudioObjectUnknown else {
            log("AudioCapture: No valid input device after config change (attempt \(retryCount + 1))")
            retryOrGiveUp(retryCount: retryCount)
            return
        }

        self.deviceID = newDeviceID

        // Get new format
        guard let streamFormat = getStreamFormat(for: deviceID) else {
            log("AudioCapture: Failed to get stream format (attempt \(retryCount + 1))")
            retryOrGiveUp(retryCount: retryCount)
            return
        }

        guard streamFormat.mSampleRate > 0, streamFormat.mChannelsPerFrame > 0 else {
            log("AudioCapture: No valid format after config change (attempt \(retryCount + 1))")
            retryOrGiveUp(retryCount: retryCount)
            return
        }

        detectedSampleRate = streamFormat.mSampleRate
        log("AudioCapture: New hardware format - \(streamFormat.mSampleRate)Hz, \(streamFormat.mChannelsPerFrame) channels (attempt \(retryCount + 1))")

        // Recreate input format and converter
        guard let inputFmt = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: streamFormat.mSampleRate,
            channels: 1,
            interleaved: false
        ) else {
            logError("AudioCapture: Failed to create input format")
            retryOrGiveUp(retryCount: retryCount)
            return
        }
        self.inputFormat = inputFmt

        guard let targetFmt = targetFormat,
              let newConverter = AVAudioConverter(from: inputFmt, to: targetFmt) else {
            logError("AudioCapture: Failed to create converter for new format")
            retryOrGiveUp(retryCount: retryCount)
            return
        }
        audioConverter = newConverter

        // Create new IOProc
        var procID: AudioDeviceIOProcID?
        let ioProcStatus = AudioDeviceCreateIOProcIDWithBlock(&procID, deviceID, nil) {
            [weak self] inNow, inInputData, inInputTime, outOutputData, inOutputTime in
            self?.handleAudioInput(inInputData, timestamp: inInputTime)
        }

        guard ioProcStatus == noErr, let validProcID = procID else {
            logError("AudioCapture: Failed to create IOProc: \(ioProcStatus) (attempt \(retryCount + 1))")
            retryOrGiveUp(retryCount: retryCount)
            return
        }
        self.ioProcID = validProcID

        // Start device
        let startStatus = AudioDeviceStart(deviceID, validProcID)
        guard startStatus == noErr else {
            logError("AudioCapture: Failed to start device: \(startStatus) (attempt \(retryCount + 1))")
            AudioDeviceDestroyIOProcID(deviceID, validProcID)
            self.ioProcID = nil
            retryOrGiveUp(retryCount: retryCount)
            return
        }

        // Install format listener on new device
        var formatAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )

        let formatBlock: AudioObjectPropertyListenerBlock = { [weak self] numberAddresses, addresses in
            DispatchQueue.main.async {
                self?.handleConfigurationChange()
            }
        }
        self.deviceFormatListenerBlock = formatBlock

        AudioObjectAddPropertyListenerBlock(
            deviceID,
            &formatAddress,
            listenerQueue,
            formatBlock
        )

        log("AudioCapture: Restarted with new configuration")
        isReconfiguring = false
    }

    private func retryOrGiveUp(retryCount: Int) {
        if retryCount < Self.maxRetries {
            let delay = Double(retryCount + 1) * 1.0  // 1s, 2s, 3s backoff
            log("AudioCapture: Retrying in \(delay)s...")
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.reconfigureAfterChange(retryCount: retryCount + 1)
            }
        } else {
            logError("AudioCapture: Giving up after \(retryCount + 1) attempts")
            isReconfiguring = false
        }
    }

    deinit {
        if isCapturing {
            removePropertyListeners()
            if let procID = ioProcID, deviceID != kAudioObjectUnknown {
                AudioDeviceStop(deviceID, procID)
                AudioDeviceDestroyIOProcID(deviceID, procID)
            }
        }
    }
}
