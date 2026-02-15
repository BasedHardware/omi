import Foundation
import AVFoundation
import CoreAudio
import ObjCExceptionCatcher

/// Service for capturing microphone audio as 16-bit PCM at 16kHz
/// Suitable for streaming to speech-to-text services like DeepGram
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

    private let audioEngine = AVAudioEngine()
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
    private var configChangeObserver: NSObjectProtocol?
    private var isReconfiguring = false

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

        let inputNode = audioEngine.inputNode

        // Get the hardware input format
        let hwFormat = inputNode.inputFormat(forBus: 0)

        guard hwFormat.channelCount > 0 else {
            throw AudioCaptureError.noInputAvailable
        }

        detectedSampleRate = hwFormat.sampleRate
        self.inputFormat = hwFormat

        log("AudioCapture: Hardware format - \(hwFormat.sampleRate)Hz, \(hwFormat.channelCount) channels")

        // Create target format: Float32 at 16kHz mono (standard format)
        // We'll convert Float32 to Int16 manually for DeepGram
        guard let targetFmt = AVAudioFormat(standardFormatWithSampleRate: targetSampleRate, channels: 1) else {
            throw AudioCaptureError.converterCreationFailed
        }
        self.targetFormat = targetFmt

        log("AudioCapture: Target format - \(targetFmt.sampleRate)Hz, \(targetFmt.channelCount) channels, Float32")

        // Create audio converter for resampling
        guard let converter = AVAudioConverter(from: hwFormat, to: targetFmt) else {
            throw AudioCaptureError.converterCreationFailed
        }
        self.audioConverter = converter

        // Install tap on input node
        let bufferSize: AVAudioFrameCount = 512
        inputNode.installTap(onBus: 0, bufferSize: bufferSize, format: hwFormat) { [weak self] buffer, time in
            self?.processAudioBuffer(buffer)
        }

        // Start the audio engine
        do {
            try audioEngine.start()
            isCapturing = true
            log("AudioCapture: Started capturing")
        } catch {
            inputNode.removeTap(onBus: 0)
            throw AudioCaptureError.engineStartFailed(error)
        }

        // Listen for audio device/configuration changes
        setupConfigurationChangeObserver()
    }

    /// Set up observer for audio configuration changes (device switches, format changes)
    private func setupConfigurationChangeObserver() {
        // Remove any existing observer
        if let observer = configChangeObserver {
            NotificationCenter.default.removeObserver(observer)
        }

        configChangeObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: audioEngine,
            queue: nil
        ) { [weak self] _ in
            // IMPORTANT: Don't do work directly in callback - use async to avoid deadlock
            DispatchQueue.main.async {
                self?.handleConfigurationChange()
            }
        }
    }

    /// Handle audio configuration change (e.g., user switched microphone)
    private func handleConfigurationChange() {
        guard isCapturing, !isReconfiguring else { return }
        isReconfiguring = true

        log("AudioCapture: Configuration changed, restarting with new device...")

        // Fully stop and reset the engine to ensure clean state
        // This removes all taps and resets internal connections
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        audioEngine.reset()

        // Delay to let the audio hardware settle after device change
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.reconfigureAfterChange(retryCount: 0)
        }
    }

    private static let maxRetries = 3

    private func reconfigureAfterChange(retryCount: Int) {
        let inputNode = audioEngine.inputNode
        let newHwFormat = inputNode.inputFormat(forBus: 0)

        guard newHwFormat.channelCount > 0, newHwFormat.sampleRate > 0 else {
            log("AudioCapture: No valid input after config change (attempt \(retryCount + 1))")
            if retryCount < Self.maxRetries {
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                    self?.reconfigureAfterChange(retryCount: retryCount + 1)
                }
            } else {
                logError("AudioCapture: Giving up after \(retryCount + 1) attempts")
                isReconfiguring = false
            }
            return
        }

        log("AudioCapture: New hardware format - \(newHwFormat.sampleRate)Hz, \(newHwFormat.channelCount) channels (attempt \(retryCount + 1))")

        // Update stored format info
        detectedSampleRate = newHwFormat.sampleRate
        inputFormat = newHwFormat

        // Recreate converter with new input format
        guard let targetFmt = targetFormat,
              let newConverter = AVAudioConverter(from: newHwFormat, to: targetFmt) else {
            logError("AudioCapture: Failed to create converter for new format")
            retryOrGiveUp(retryCount: retryCount)
            return
        }
        audioConverter = newConverter

        // Install tap with ObjC exception handling (installTap throws NSException, not Swift Error)
        let bufferSize: AVAudioFrameCount = 512
        let exception = ObjCExceptionCatcher.catching {
            inputNode.installTap(onBus: 0, bufferSize: bufferSize, format: newHwFormat) { [weak self] buffer, time in
                self?.processAudioBuffer(buffer)
            }
        }

        if let exception = exception {
            logError("AudioCapture: Failed to install tap: \(exception.name.rawValue) - \(exception.reason ?? "unknown") (attempt \(retryCount + 1))")
            retryOrGiveUp(retryCount: retryCount)
            return
        }

        // Restart the engine
        do {
            try audioEngine.start()
            log("AudioCapture: Restarted with new configuration")
            isReconfiguring = false
        } catch {
            logError("AudioCapture: Failed to restart engine: \(error.localizedDescription) (attempt \(retryCount + 1))")
            inputNode.removeTap(onBus: 0)
            audioEngine.reset()
            retryOrGiveUp(retryCount: retryCount)
        }
    }

    private func retryOrGiveUp(retryCount: Int) {
        if retryCount < Self.maxRetries {
            let delay = Double(retryCount + 1) * 1.0  // 1s, 2s, 3s backoff
            log("AudioCapture: Retrying in \(delay)s...")
            audioEngine.stop()
            audioEngine.reset()
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.reconfigureAfterChange(retryCount: retryCount + 1)
            }
        } else {
            logError("AudioCapture: Giving up after \(retryCount + 1) attempts")
            isReconfiguring = false
        }
    }

    /// Stop capturing audio
    func stopCapture() {
        guard isCapturing else { return }

        // Remove configuration change observer
        if let observer = configChangeObserver {
            NotificationCenter.default.removeObserver(observer)
            configChangeObserver = nil
        }

        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
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

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        guard isCapturing else { return }

        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return }

        guard let converter = audioConverter, let targetFmt = targetFormat else { return }

        // Calculate output buffer size based on sample rate conversion ratio
        let outputFrameCapacity = AVAudioFrameCount(ceil(Double(frameLength) * targetSampleRate / detectedSampleRate))

        guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFmt, frameCapacity: outputFrameCapacity) else {
            return
        }

        // Convert using input block pattern (same as OMI Watch app)
        var error: NSError?
        var hasConsumedInput = false

        let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
            if hasConsumedInput {
                outStatus.pointee = .noDataNow
                return nil
            }
            hasConsumedInput = true
            outStatus.pointee = .haveData
            return buffer
        }

        converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

        if let error = error {
            logError("AudioCapture: Conversion error", error: error)
            return
        }

        // Convert Float32 samples to Int16 (linear16 PCM for DeepGram)
        guard let channelData = outputBuffer.floatChannelData?[0] else {
            return
        }

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
}
