import Foundation
import AVFoundation
import CoreAudio

/// Service for capturing microphone audio as 16-bit PCM at 16kHz
/// Uses CoreAudio IOProc directly on the default input device to avoid
/// AVAudioEngine's implicit aggregate device creation, which degrades
/// system audio output quality (especially Bluetooth A2DP → SCO switch).
class AudioCaptureService: @unchecked Sendable {

    // MARK: - Types

    /// Callback for receiving audio chunks
    typealias AudioChunkHandler = (Data) -> Void

    /// Callback for receiving audio levels (0.0 - 1.0)
    typealias AudioLevelHandler = (Float) -> Void

    enum SilentMicRecoveryAction {
        case fallbackToBuiltIn
        case rebuildCoreAudioStack
    }

    struct SilentMicDetection {
        let deviceID: AudioDeviceID
        let deviceDescription: String
        let consecutiveSilentWindows: Int
        let isBluetoothTransport: Bool

        var suggestedAction: SilentMicRecoveryAction {
            isBluetoothTransport ? .fallbackToBuiltIn : .rebuildCoreAudioStack
        }

        var reason: String {
            "silent input on \(deviceDescription) after \(consecutiveSilentWindows) windows"
        }
    }

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
    private var isTrackingOverrideDevice = false

    /// Optional explicit device to open instead of the system default input.
    /// Used by the silent-mic fallback path to bind directly to the built-in mic.
    private let overrideDeviceID: AudioDeviceID?

    /// Default initializer — opens the system default input device.
    init() {
        self.overrideDeviceID = nil
    }

    /// Initializer that binds to an explicit CoreAudio device (e.g. built-in mic after
    /// a silent-mic fallback). Pass `kAudioObjectUnknown` to disable the override.
    init(overrideDeviceID: AudioDeviceID) {
        self.overrideDeviceID = (overrideDeviceID == kAudioObjectUnknown) ? nil : overrideDeviceID
    }

    private var onAudioChunk: AudioChunkHandler?
    private var onAudioLevel: AudioLevelHandler?

    /// Called when the mic has been alive-but-silent for `silentMicWindowThreshold`
    /// windows. By default this is limited to Bluetooth inputs, where macOS can feed
    /// zeros during A2DP/HFP profile conflicts. PTT enables all-transport detection so
    /// it can recover a stale HAL route that reports the built-in mic but still returns
    /// silence. The watchdog re-arms after each fire (see `evaluateSilentMicWindow`), so a
    /// single capture session can recover from more than one silent episode.
    var onSilentMicDetected: ((SilentMicDetection) -> Void)?
    var detectSilentMicOnAnyTransport = false

    /// Human-readable description of the capture device currently in use — for
    /// diagnostics (which mic a turn was recorded from).
    var currentDeviceDescription: String {
        let isBuiltIn = (deviceID == AudioCaptureService.findBuiltInMicDeviceID())
        return isBuiltIn ? "built-in id=\(deviceID)" : "id=\(deviceID)"
    }

    // Silent-mic watchdog. Re-arms after each fire so one session can recover from more
    // than one silent episode; two guards keep it from spinning the recovery loop:
    //   - `silentMicRecoveryCooldown`: suppress re-detection right after a fire so a freshly
    //     rebuilt/switched capture has time to deliver real audio before we judge it again.
    //   - `maxSilentMicFiresPerSession`: hard cap so an unrecoverable mic can't loop forever.
    // `silentMicDetectedFired` now means "recently fired, awaiting re-arm" (not a permanent latch).
    private var consecutiveSilentWindows: Int = 0
    private var silentMicDetectedFired: Bool = false
    private var silentMicFireCount: Int = 0
    private var lastSilentMicFireTime: CFAbsoluteTime = 0
    private let silentMicWindowThreshold: Int = 2  // windows of ~1s each
    private let silentMicRecoveryCooldown: CFAbsoluteTime = 3.0  // seconds to let recovery take effect
    private let maxSilentMicFiresPerSession: Int = 3

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

    // Silent-mic watchdog state — tracks peak amplitude within a ~1 second window
    // so we can detect a Bluetooth mic that's alive-but-silent (A2DP profile conflict).
    private var watchdogWindowPeak: Int16 = 0
    private var watchdogWindowStart: CFAbsoluteTime = 0

    /// Dedicated queue for CoreAudio device operations (start/stop/reconfigure)
    /// to avoid blocking the main thread on AudioDeviceStart/Stop calls.
    private let audioQueue = DispatchQueue(label: "com.omi.audiocapture.device")

    // MARK: - Public Methods

    func resetSilentMicWatchdog() {
        consecutiveSilentWindows = 0
        silentMicDetectedFired = false
        silentMicFireCount = 0
        lastSilentMicFireTime = 0
        watchdogWindowPeak = 0
        watchdogWindowStart = 0
    }

    /// Classify one closed ~1-second watchdog window and update re-arm bookkeeping.
    ///
    /// Returns a `SilentMicDetection` when the mic has been silent for
    /// `silentMicWindowThreshold` consecutive windows and the watchdog is armed — the
    /// caller then invokes `onSilentMicDetected`. Returns `nil` otherwise. After a fire the
    /// watchdog suppresses re-detection until `silentMicRecoveryCooldown` has elapsed, then
    /// re-arms, so a mic that recovered and later re-wedged (or a recovery that did not take)
    /// is detected again — bounded by `maxSilentMicFiresPerSession` so an unrecoverable mic
    /// cannot loop the recovery path forever.
    ///
    /// `internal` (not `private`) so the recover-more-than-once-per-session contract can be
    /// unit-tested without driving real CoreAudio buffers.
    func evaluateSilentMicWindow(peak: Int16, isBluetooth: Bool, now: CFAbsoluteTime) -> SilentMicDetection? {
        // peak ≤ 5 (≈ -76 dBFS) is effectively silent compared to real speech.
        if peak <= 5 {
            consecutiveSilentWindows += 1
        } else {
            consecutiveSilentWindows = 0
        }

        // Re-arm once the post-fire cooldown has elapsed.
        if silentMicDetectedFired, now - lastSilentMicFireTime >= silentMicRecoveryCooldown {
            silentMicDetectedFired = false
        }

        guard !silentMicDetectedFired,
              silentMicFireCount < maxSilentMicFiresPerSession,
              consecutiveSilentWindows >= silentMicWindowThreshold,
              isBluetooth || detectSilentMicOnAnyTransport
        else {
            return nil
        }

        let firedWindows = consecutiveSilentWindows
        silentMicDetectedFired = true
        silentMicFireCount += 1
        lastSilentMicFireTime = now
        // Require a fresh run of silent windows before the next fire so we never re-trigger
        // on the very next window.
        consecutiveSilentWindows = 0

        return SilentMicDetection(
            deviceID: deviceID,
            deviceDescription: currentDeviceDescription,
            consecutiveSilentWindows: firedWindows,
            isBluetoothTransport: isBluetooth
        )
    }

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
    func startCapture(onAudioChunk: @escaping AudioChunkHandler, onAudioLevel: AudioLevelHandler? = nil) async throws {
        guard !isCapturing else {
            log("AudioCapture: Already capturing")
            return
        }

        self.onAudioChunk = onAudioChunk
        self.onAudioLevel = onAudioLevel
        resetSilentMicWatchdog()

        // All CoreAudio HAL calls (AudioObjectGetPropertyData, AudioDeviceStart, etc.) are
        // synchronous IPC to coreaudiod via mach_msg. After wake from sleep the daemon can
        // take seconds to respond, blocking the caller. Dispatch the entire setup to audioQueue,
        // mirroring the pattern already used in stopCapture() and handleConfigurationChange().
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            audioQueue.async { [weak self] in
                guard let self else {
                    continuation.resume()
                    return
                }
                do {
                    try self.startCaptureOnQueue()
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Performs all blocking CoreAudio HAL setup. Must be called on audioQueue, not the main thread.
    private func startCaptureOnQueue() throws {
        resetSilentMicWatchdog()

        // 1. Resolve input device: explicit override wins while available, otherwise
        // fall back to the system default instead of pinning capture to a stale device.
        let inputDeviceID = try resolveInputDeviceID()
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
        registerActiveCapture(deviceID: deviceID)
        log("AudioCapture: Started capturing")

        // 8. Install property listeners for device changes
        installPropertyListeners()
    }

    /// Stop capturing audio
    func stopCapture() {
        resetSilentMicWatchdog()
        guard isCapturing else { return }

        removePropertyListeners()

        // Capture values before clearing state so we can dispatch the heavy
        // CoreAudio calls off the main thread.
        let procID = self.ioProcID
        let devID = self.deviceID

        ioProcID = nil
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
        isTrackingOverrideDevice = false

        // AudioDeviceStop can block waiting for the IO thread — run off main thread
        if let procID = procID, devID != kAudioObjectUnknown {
            audioQueue.async { [self] in
                AudioDeviceStop(devID, procID)
                AudioDeviceDestroyIOProcID(devID, procID)
                unregisterActiveCapture()
            }
        } else {
            unregisterActiveCapture()
        }

        log("AudioCapture: Stopped capturing")
    }

    /// Check if currently capturing
    var capturing: Bool {
        return isCapturing
    }

    /// Get the name of the current default input device (microphone)
    /// A selectable audio input device.
    struct InputDeviceInfo: Identifiable, Equatable, Sendable {
        let id: AudioDeviceID
        let uid: String
        let name: String
        let isBluetooth: Bool
    }

    /// Ray-Ban Meta / Oakley Meta glasses expose no vendor API on macOS; the
    /// input-device name is the only identity signal, so match Meta's product
    /// names precisely rather than anything containing "glass".
    static func isMetaGlassesName(_ name: String) -> Bool {
        let lower = name.lowercased()
        return lower.contains("ray-ban") || lower.contains("rayban")
            || lower.contains("oakley meta") || lower.contains("meta glasses")
    }

    /// Enumerate every device with input channels (HAL walk, same pattern as
    /// findBuiltInMicDeviceID). Device IDs are not stable across reconnects, so
    /// persistence must use the UID.
    static func listInputDevices() -> [InputDeviceInfo] {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(
            AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size
        ) == noErr else { return [] }

        let count = Int(size) / MemoryLayout<AudioDeviceID>.size
        guard count > 0 else { return [] }
        var deviceIDs = [AudioDeviceID](repeating: kAudioObjectUnknown, count: count)
        guard AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceIDs
        ) == noErr else { return [] }

        var result: [InputDeviceInfo] = []
        for id in deviceIDs where id != kAudioObjectUnknown {
            guard deviceHasInputChannels(id) else { continue }
            guard let name = deviceName(for: id), let uid = deviceUID(for: id) else { continue }

            var transport: UInt32 = 0
            var tsize = UInt32(MemoryLayout<UInt32>.size)
            var taddr = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyTransportType,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            let isBT = AudioObjectGetPropertyData(id, &taddr, 0, nil, &tsize, &transport) == noErr
                && (transport == kAudioDeviceTransportTypeBluetooth
                    || transport == kAudioDeviceTransportTypeBluetoothLE)
            result.append(InputDeviceInfo(id: id, uid: uid, name: name, isBluetooth: isBT))
        }
        return result
    }

    static func deviceName(for deviceID: AudioDeviceID) -> String? {
        var name: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioObjectPropertyName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &name) == noErr,
            let cfName = name?.takeRetainedValue()
        else { return nil }
        return cfName as String
    }

    static func deviceUID(for deviceID: AudioDeviceID) -> String? {
        var uid: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &uid) == noErr,
            let cfUID = uid?.takeRetainedValue()
        else { return nil }
        return cfUID as String
    }

    static func inputDeviceID(forUID uid: String) -> AudioDeviceID? {
        listInputDevices().first(where: { $0.uid == uid })?.id
    }

    /// UserDefaults key for the user's explicit microphone choice ("" = system default).
    static let preferredInputUIDDefaultsKey = DefaultsKey.preferredMicrophoneDeviceUID.rawValue

    // MARK: - Active-capture registry
    //
    // Tracks which devices are held by a live capture so other audio consumers
    // (push-to-talk) can avoid opening a second IOProc against the same device
    // — or joining a Bluetooth mic's A2DP↔HFP profile flap — which races the
    // two instances' stream-format reconfiguration paths.
    private static let activeCapturesLock = NSLock()
    private static var activeCaptures: [ObjectIdentifier: AudioDeviceID] = [:]

    private func registerActiveCapture(deviceID: AudioDeviceID) {
        Self.activeCapturesLock.lock()
        Self.activeCaptures[ObjectIdentifier(self)] = deviceID
        Self.activeCapturesLock.unlock()
    }

    private func unregisterActiveCapture() {
        Self.activeCapturesLock.lock()
        Self.activeCaptures.removeValue(forKey: ObjectIdentifier(self))
        Self.activeCapturesLock.unlock()
    }

    /// True when a live capture already holds this device.
    static func isDeviceActivelyCaptured(
        _ deviceID: AudioDeviceID,
        excluding excludedCapture: AudioCaptureService? = nil
    ) -> Bool {
        activeCapturesLock.lock()
        defer { activeCapturesLock.unlock() }
        let excludedID = excludedCapture.map(ObjectIdentifier.init)
        return activeCaptures.contains { owner, activeDeviceID in
            activeDeviceID == deviceID && (excludedID.map { owner != $0 } ?? true)
        }
    }

    /// True when any capture is currently running in this process.
    static func hasActiveCapture(excluding excludedCapture: AudioCaptureService? = nil) -> Bool {
        activeCapturesLock.lock()
        defer { activeCapturesLock.unlock() }
        guard let excludedCapture else { return !activeCaptures.isEmpty }
        return activeCaptures.keys.contains { $0 != ObjectIdentifier(excludedCapture) }
    }

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

    private func resolveInputDeviceID() throws -> AudioDeviceID {
        if let override = overrideDeviceID {
            if Self.isAvailableInputDevice(override) {
                log("AudioCapture: Using override device ID \(override)")
                isTrackingOverrideDevice = true
                return override
            }
            log("AudioCapture: Override device ID \(override) is unavailable; falling back to default input")
        }

        guard let defaultDeviceID = Self.currentDefaultInputDeviceID() else {
            throw AudioCaptureError.noInputAvailable
        }
        isTrackingOverrideDevice = false
        return defaultDeviceID
    }

    static func currentDefaultInputDeviceID() -> AudioDeviceID? {
        var deviceID: AudioDeviceID = kAudioObjectUnknown
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

        guard status == noErr, isAvailableInputDevice(deviceID) else { return nil }
        return deviceID
    }

    private static func isAvailableInputDevice(_ deviceID: AudioDeviceID) -> Bool {
        deviceID != kAudioObjectUnknown && deviceID != kAudioDeviceUnknown && deviceHasInputChannels(deviceID)
    }

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

            // Accumulate the silent-mic peak while converting samples to avoid an
            // extra pass on the audio callback hot path.
            let absoluteSample = pcmSample == Int16.min ? Int16.max : Int16(pcmSample.magnitude)
            if absoluteSample > watchdogWindowPeak { watchdogWindowPeak = absoluteSample }
        }

        // Convert to Data (little-endian, which is native on Apple platforms)
        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        // Silent-mic watchdog: macOS can accept the IOProc but deliver only zero samples.
        // Bluetooth inputs recover by switching to the built-in mic; PTT can opt into
        // all-transport detection so a stale built-in/default route triggers a full rebuild.
        // Classify once every ~1s window. Windows keep rolling after a fire (unlike a
        // one-shot latch) so the watchdog observes recovery and can re-arm for a second
        // episode — see `evaluateSilentMicWindow`.
        let nowAbs = CFAbsoluteTimeGetCurrent()
        if watchdogWindowStart == 0 { watchdogWindowStart = nowAbs }
        if nowAbs - watchdogWindowStart >= 1.0 {
            let isBluetooth = Self.isBluetoothTransport(deviceID: deviceID)
            if let detection = evaluateSilentMicWindow(peak: watchdogWindowPeak, isBluetooth: isBluetooth, now: nowAbs) {
                if isBluetooth {
                    log("AudioCapture: Bluetooth mic returning silence for \(detection.consecutiveSilentWindows)s — falling back to built-in mic")
                } else {
                    log("AudioCapture: Input device returning silence for \(detection.consecutiveSilentWindows)s — rebuilding CoreAudio capture")
                }
                let handler = onSilentMicDetected
                DispatchQueue.main.async { handler?(detection) }
            }
            watchdogWindowPeak = 0
            watchdogWindowStart = nowAbs
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
        registerActiveCapture(deviceID: deviceID)
        updateDefaultDeviceListener()
        installDeviceFormatListener()
    }

    private func updateDefaultDeviceListener() {
        if isTrackingOverrideDevice {
            removeDefaultDeviceListener()
            return
        }

        guard defaultDeviceListenerBlock == nil else { return }

        // Listen for default input device changes when the resolved capture device
        // is the system default. If an explicit override was requested but is
        // unavailable, capture falls back to the default and must still observe
        // default-device changes.
        var defaultDeviceAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let deviceBlock: AudioObjectPropertyListenerBlock = { [weak self] numberAddresses, addresses in
            self?.audioQueue.async {
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
    }

    private func installDeviceFormatListener() {
        guard deviceFormatListenerBlock == nil else { return }

        // Listen for format changes on current device
        var formatAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )

        let formatBlock: AudioObjectPropertyListenerBlock = { [weak self] numberAddresses, addresses in
            self?.audioQueue.async {
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
        removeDefaultDeviceListener()
        removeDeviceFormatListener()
    }

    private func removeDefaultDeviceListener() {
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
    }

    private func removeDeviceFormatListener() {
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
    /// Runs on audioQueue to avoid blocking the main thread.
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

        // Remove old format listener (device may have changed).
        removeDeviceFormatListener()

        // Delay to let the audio hardware settle after device change
        audioQueue.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.reconfigureAfterChange(retryCount: 0)
        }
    }

    private static let maxRetries = 3

    private func reconfigureAfterChange(retryCount: Int) {
        let newDeviceID: AudioDeviceID
        do {
            newDeviceID = try resolveInputDeviceID()
        } catch {
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

        updateDefaultDeviceListener()
        installDeviceFormatListener()
        registerActiveCapture(deviceID: deviceID)

        log("AudioCapture: Restarted with new configuration")
        isReconfiguring = false
    }

    private func retryOrGiveUp(retryCount: Int) {
        if retryCount < Self.maxRetries {
            let delay = Double(retryCount + 1) * 1.0  // 1s, 2s, 3s backoff
            log("AudioCapture: Retrying in \(delay)s...")
            audioQueue.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.reconfigureAfterChange(retryCount: retryCount + 1)
            }
        } else {
            logError("AudioCapture: Giving up after \(retryCount + 1) attempts")
            isReconfiguring = false
        }
    }

    // MARK: - Static helpers for silent-mic fallback

    /// Return true if the given CoreAudio device transports over Bluetooth.
    /// Used by the silent-mic watchdog to decide whether a dead input stream
    /// is the known A2DP/HFP profile-conflict case on macOS.
    static func isBluetoothTransport(deviceID: AudioDeviceID) -> Bool {
        guard deviceID != kAudioObjectUnknown else { return false }
        var transport: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyTransportType,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &transport)
        guard status == noErr else { return false }
        return transport == kAudioDeviceTransportTypeBluetooth
            || transport == kAudioDeviceTransportTypeBluetoothLE
    }

    /// True when the system's default OUTPUT device transports over Bluetooth.
    /// Opening a 16 kHz input on a BT device forces it from A2DP into HFP headset
    /// mode, which drops the OUTPUT rate to 16 kHz and chops streamed playback —
    /// so the realtime-hub PTT path captures from the built-in mic instead when
    /// this is true, keeping the BT output in A2DP.
    static func isDefaultOutputBluetooth() -> Bool {
        var deviceID = AudioDeviceID(kAudioObjectUnknown)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID)
        guard status == noErr, deviceID != kAudioObjectUnknown else { return false }
        return isBluetoothTransport(deviceID: deviceID)
    }

    /// Locate the CoreAudio device ID of the built-in microphone (if present).
    /// Returns `nil` when no built-in input is available (e.g. desktop Mac without a mic).
    static func findBuiltInMicDeviceID() -> AudioDeviceID? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size
        ) == noErr else { return nil }

        let count = Int(size) / MemoryLayout<AudioDeviceID>.size
        guard count > 0 else { return nil }
        var deviceIDs = [AudioDeviceID](repeating: kAudioObjectUnknown, count: count)
        guard AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            0,
            nil,
            &size,
            &deviceIDs
        ) == noErr else { return nil }

        for id in deviceIDs where id != kAudioObjectUnknown {
            guard deviceHasInputChannels(id) else { continue }

            var transport: UInt32 = 0
            var tsize = UInt32(MemoryLayout<UInt32>.size)
            var taddr = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyTransportType,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            let status = AudioObjectGetPropertyData(id, &taddr, 0, nil, &tsize, &transport)
            if status == noErr, transport == kAudioDeviceTransportTypeBuiltIn {
                return id
            }
        }
        return nil
    }

    /// Return true if the device has at least one input channel.
    private static func deviceHasInputChannels(_ deviceID: AudioDeviceID) -> Bool {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &size) == noErr,
              size > 0 else { return false }

        let raw = UnsafeMutableRawPointer.allocate(
            byteCount: Int(size),
            alignment: MemoryLayout<AudioBufferList>.alignment
        )
        defer { raw.deallocate() }
        let bufferList = raw.bindMemory(to: AudioBufferList.self, capacity: 1)
        guard AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, bufferList) == noErr else {
            return false
        }
        let buffers = UnsafeMutableAudioBufferListPointer(bufferList)
        for buffer in buffers where buffer.mNumberChannels > 0 {
            return true
        }
        return false
    }

    deinit {
        if isCapturing {
            removePropertyListeners()
            if let procID = ioProcID, deviceID != kAudioObjectUnknown {
                // Call the HAL teardown directly — do NOT `audioQueue.sync` here.
                // deinit can run *on* audioQueue (e.g. the last reference is released
                // inside an audioQueue block), and dispatching sync to the current
                // queue deadlocks. The object has no remaining references, so no
                // concurrent audioQueue work can touch it; these HAL calls are
                // thread-safe, so a direct call completes cleanup before deallocation
                // (which `audioQueue.async` could not guarantee).
                AudioDeviceStop(deviceID, procID)
                AudioDeviceDestroyIOProcID(deviceID, procID)
            }
            unregisterActiveCapture()
        }
    }
}
