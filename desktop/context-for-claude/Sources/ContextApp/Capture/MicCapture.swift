@preconcurrency import AVFoundation
@preconcurrency import CoreAudio
import Foundation

/// Microphone capture, delivered as 16 kHz mono Int16 little-endian PCM.
///
/// Runs a CoreAudio IOProc directly on the default input device rather than using
/// `AVAudioEngine`: the engine creates an implicit aggregate device, which degrades system
/// audio *output* quality — most visibly by dragging Bluetooth headphones out of A2DP into
/// the 16 kHz SCO/HFP profile and chopping whatever the user is listening to. Ported from
/// Omi desktop's `AudioCaptureService`, which learned every detail here the hard way.
///
/// Threading: `queue` is the single owner of all mutable state. The HAL IO thread reads that
/// state inside `handleAudioInput` and owns the watchdog counters, which is safe because a
/// device's IOProc is serial and the queue only touches those counters while no IOProc is
/// running.
final class MicCapture: AudioSource, @unchecked Sendable {

    // MARK: - Types

    /// A currently available CoreAudio input device. `uid` stays stable when CoreAudio assigns
    /// a different numeric device ID after the device is reconnected.
    struct InputDevice: Hashable {
        let id: AudioDeviceID
        let uid: String
        let name: String
    }

    // MARK: - Configuration

    private let targetSampleRate: Double = 16000

    /// Peak ≤ 5 (≈ -76 dBFS) over a whole window is silence, not quiet speech.
    private let silentPeakThreshold: Int16 = 5
    /// Windows of ~1 s that must be silent in a row before the stack is rebuilt.
    private let silentWindowThreshold = 2
    /// Give a rebuilt stack this long to deliver real audio before judging it again.
    private let silentRecoveryCooldown: CFAbsoluteTime = 3.0
    /// Hard cap so an unrecoverable mic cannot loop the recovery path forever.
    private let maxSilentRecoveriesPerSession = 3
    private static let maxRetries = 3

    /// Level shaping — a soft noise floor plus a decay, so the UI meter falls smoothly
    /// instead of flickering on preamp noise.
    private let noiseFloor: Float = 0.005
    private let decayRate: Float = 0.85

    // MARK: - Queues

    /// All CoreAudio HAL calls (`AudioObjectGetPropertyData`, `AudioDeviceStart`, …) are
    /// synchronous IPC to coreaudiod; after wake from sleep the daemon can take seconds to
    /// answer. Every device operation runs here so nothing ever blocks the main thread.
    private let queue = DispatchQueue(label: "com.omi.context-for-claude.mic.device")
    private let listenerQueue = DispatchQueue(label: "com.omi.context-for-claude.mic.listener")

    // MARK: - State (queue-confined)

    private var deviceID: AudioDeviceID = kAudioObjectUnknown
    private var ioProcID: AudioDeviceIOProcID?
    private var defaultDeviceListenerBlock: AudioObjectPropertyListenerBlock?
    private var deviceFormatListenerBlock: AudioObjectPropertyListenerBlock?
    private var isCapturing = false
    private var isReconfiguring = false

    /// Set by the silent-mic watchdog when a Bluetooth input goes dead: capture binds to the
    /// built-in mic instead. Cleared when the default input changes, because the user picking
    /// a mic outranks our fallback.
    private var fallbackDeviceID: AudioDeviceID?

    private var onChunk: (@Sendable (Data) -> Void)?
    private var onLevel: (@Sendable (Float) -> Void)?

    private var audioConverter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var detectedSampleRate: Double = 0
    private var smoothedLevel: Float = 0

    // Silent-mic watchdog, owned by the IO thread. Tracks the peak amplitude inside a ~1 s
    // window so a mic that is alive-but-silent (the Bluetooth A2DP/HFP profile flip) is
    // detected and recovered from.
    private var watchdogWindowPeak: Int16 = 0
    private var watchdogWindowStart: CFAbsoluteTime = 0
    private var consecutiveSilentWindows = 0
    private var silenceRecoveryArmed = true
    private var silenceRecoveryCount = 0
    private var lastSilenceRecoveryTime: CFAbsoluteTime = 0

    // Flipped exactly once per `convert()` call by the synchronous `AVAudioConverter` input
    // block (a `@Sendable` closure) on the non-reentrant CoreAudio IO thread, and reset at the
    // top of every `handleAudioInput`.
    private nonisolated(unsafe) var hasConsumedInput = false

    /// `isRunning` is read from the main thread while `isCapturing` is queue-confined, so the
    /// public flag is mirrored under a lock. Callers see `stop()` take effect immediately even
    /// though the HAL teardown it enqueues finishes later.
    private let runningLock = NSLock()
    private var runningFlag = false

    var isRunning: Bool {
        runningLock.lock()
        defer { runningLock.unlock() }
        return runningFlag
    }

    private func setRunning(_ value: Bool) {
        runningLock.lock()
        runningFlag = value
        runningLock.unlock()
    }

    // MARK: - Permission

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

    static func requestPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    // MARK: - AudioSource

    func start(
        onChunk: @escaping @Sendable (Data) -> Void,
        onLevel: @escaping @Sendable (Float) -> Void
    ) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            queue.async { [weak self] in
                guard let self else {
                    continuation.resume()
                    return
                }
                guard !self.isCapturing else {
                    ContextLog.info("start ignored, already capturing", "mic")
                    continuation.resume()
                    return
                }
                // The callbacks are assigned on the same serial queue that clears them in
                // teardown, so a stop's deferred clear can never race a restart's assignment.
                self.onChunk = onChunk
                self.onLevel = onLevel
                do {
                    try self.startOnQueue()
                    continuation.resume()
                } catch {
                    self.onChunk = nil
                    self.onLevel = nil
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func stop() {
        setRunning(false)
        queue.async { [weak self] in
            guard let self, self.isCapturing else { return }
            self.teardownOnQueue()
            ContextLog.info("stopped", "mic")
        }
    }

    // MARK: - Device inventory

    /// The input devices currently available for capture.
    static func availableInputDevices() -> [InputDevice] {
        audioDeviceIDs().compactMap { deviceID in
            guard
                isAvailableInputDevice(deviceID),
                let uid = deviceStringProperty(deviceID, selector: kAudioDevicePropertyDeviceUID)
            else { return nil }

            return InputDevice(
                id: deviceID,
                uid: uid,
                name: deviceStringProperty(deviceID, selector: kAudioObjectPropertyName) ?? "Microphone"
            )
        }
        .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    /// The CoreAudio device ID of the built-in microphone, or nil on a Mac without one.
    /// The silent-mic watchdog falls back to this when a Bluetooth input goes dead.
    static func findBuiltInMicDeviceID() -> AudioDeviceID? {
        for id in audioDeviceIDs() where id != kAudioObjectUnknown {
            guard deviceHasInputChannels(id) else { continue }
            if deviceTransportType(id) == kAudioDeviceTransportTypeBuiltIn { return id }
        }
        return nil
    }

    /// True when the device transports over Bluetooth — the known profile-conflict case
    /// where macOS accepts the IOProc and then feeds it zeros.
    static func isBluetoothTransport(deviceID: AudioDeviceID) -> Bool {
        guard deviceID != kAudioObjectUnknown, let transport = deviceTransportType(deviceID) else { return false }
        return transport == kAudioDeviceTransportTypeBluetooth || transport == kAudioDeviceTransportTypeBluetoothLE
    }

    // MARK: - Start / teardown (queue only)

    private func startOnQueue() throws {
        resetWatchdog()

        let inputDeviceID = try resolveInputDeviceID()
        self.deviceID = inputDeviceID

        guard let streamFormat = getStreamFormat(for: inputDeviceID),
            streamFormat.mSampleRate > 0,
            streamFormat.mChannelsPerFrame > 0
        else {
            throw AudioCaptureError.formatUnavailable
        }
        detectedSampleRate = streamFormat.mSampleRate

        try buildConverter(sourceSampleRate: streamFormat.mSampleRate)
        try startIOProc()

        isCapturing = true
        setRunning(true)
        ContextLog.info(
            "capturing device \(inputDeviceID) at \(Int(streamFormat.mSampleRate))Hz "
                + "\(streamFormat.mChannelsPerFrame)ch → 16kHz mono", "mic")

        installDefaultDeviceListener()
        installDeviceFormatListener()
    }

    /// Builds the mono input format, the 16 kHz target format, and the converter between them.
    /// The device is mixed down to mono *before* conversion, so the converter only resamples.
    private func buildConverter(sourceSampleRate: Double) throws {
        guard
            let inputFmt = AVAudioFormat(
                commonFormat: .pcmFormatFloat32,
                sampleRate: sourceSampleRate,
                channels: 1,
                interleaved: false
            ),
            let targetFmt = AVAudioFormat(standardFormatWithSampleRate: targetSampleRate, channels: 1),
            let converter = AVAudioConverter(from: inputFmt, to: targetFmt)
        else {
            throw AudioCaptureError.formatUnavailable
        }
        inputFormat = inputFmt
        targetFormat = targetFmt
        audioConverter = converter
    }

    private func startIOProc() throws {
        var procID: AudioDeviceIOProcID?
        let createStatus = AudioDeviceCreateIOProcIDWithBlock(&procID, deviceID, nil) {
            [weak self] _, inInputData, _, _, _ in
            self?.handleAudioInput(inInputData)
        }
        guard createStatus == noErr, let validProcID = procID else {
            throw AudioCaptureError.ioProcFailed(createStatus)
        }
        ioProcID = validProcID

        let startStatus = AudioDeviceStart(deviceID, validProcID)
        guard startStatus == noErr else {
            AudioDeviceDestroyIOProcID(deviceID, validProcID)
            ioProcID = nil
            throw AudioCaptureError.ioProcFailed(startStatus)
        }
    }

    private func teardownOnQueue() {
        removePropertyListeners()

        let procID = ioProcID
        let devID = deviceID
        ioProcID = nil
        deviceID = kAudioObjectUnknown
        isCapturing = false
        isReconfiguring = false
        fallbackDeviceID = nil

        if let procID, devID != kAudioObjectUnknown {
            AudioDeviceStop(devID, procID)
            AudioDeviceDestroyIOProcID(devID, procID)
        }

        // Only now is the HAL IO thread guaranteed to be out of handleAudioInput. Releasing
        // the state it reads any earlier races its reads: torn retain/release on the callbacks
        // and converter crashes intermittently on stop, and a zeroed detectedSampleRate would
        // divide-by-zero the resample math mid-callback.
        onChunk = nil
        onLevel = nil
        audioConverter = nil
        inputFormat = nil
        targetFormat = nil
        detectedSampleRate = 0
        smoothedLevel = 0
        resetWatchdog()
        setRunning(false)
    }

    private func resolveInputDeviceID() throws -> AudioDeviceID {
        if let fallback = fallbackDeviceID {
            if Self.isAvailableInputDevice(fallback) { return fallback }
            ContextLog.info("fallback input device went away, using system default", "mic")
            fallbackDeviceID = nil
        }
        guard let defaultDeviceID = Self.currentDefaultInputDeviceID() else {
            throw AudioCaptureError.noInputDevice
        }
        return defaultDeviceID
    }

    // MARK: - Audio path

    /// Frames a `sourceSampleRate` → `targetSampleRate` conversion of `frameCount` input frames
    /// produces. Returns 0 when the source rate is unknown: dividing by a zero rate yields
    /// `.infinity`, and `AVAudioFrameCount(.infinity)` traps the real-time IO thread — reachable
    /// when a device reports no rate, or when teardown zeroes the rate mid-callback.
    static func resampledFrameCapacity(
        frameCount: AVAudioFrameCount, sourceSampleRate: Double, targetSampleRate: Double
    ) -> AVAudioFrameCount {
        guard frameCount > 0, sourceSampleRate > 0, targetSampleRate > 0 else { return 0 }
        return AVAudioFrameCount(ceil(Double(frameCount) * targetSampleRate / sourceSampleRate))
    }

    /// Called on the CoreAudio HAL IO thread. Must never block: no locks, no I/O, no `sync`.
    private func handleAudioInput(_ inputData: UnsafePointer<AudioBufferList>?) {
        guard isCapturing,
            let bufferList = inputData?.pointee,
            let converter = audioConverter,
            let targetFmt = targetFormat,
            let inputFmt = inputFormat
        else { return }

        let buffer = bufferList.mBuffers
        guard let data = buffer.mData, buffer.mDataByteSize > 0 else { return }

        let bytesPerFrame = UInt32(MemoryLayout<Float32>.size) * buffer.mNumberChannels
        guard bytesPerFrame > 0 else { return }
        let frameCount = buffer.mDataByteSize / bytesPerFrame
        guard frameCount > 0 else { return }

        guard let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFmt, frameCapacity: frameCount) else { return }
        inputBuffer.frameLength = frameCount

        let srcPtr = data.assumingMemoryBound(to: Float32.self)
        let channelCount = Int(buffer.mNumberChannels)
        guard let floatData = inputBuffer.floatChannelData else { return }
        let monoPtr = floatData[0]

        if channelCount >= 2 {
            // Stereo (or more) down to mono by averaging the first two channels.
            for i in 0..<Int(frameCount) {
                let left = srcPtr[i * channelCount]
                let right = srcPtr[i * channelCount + 1]
                monoPtr[i] = (left + right) / 2.0
            }
        } else {
            memcpy(monoPtr, srcPtr, Int(buffer.mDataByteSize))
        }

        let outputFrameCapacity = Self.resampledFrameCapacity(
            frameCount: frameCount, sourceSampleRate: detectedSampleRate, targetSampleRate: targetSampleRate)
        guard outputFrameCapacity > 0,
            let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFmt, frameCapacity: outputFrameCapacity)
        else { return }

        var error: NSError?
        hasConsumedInput = false
        let inputBlock: AVAudioConverterInputBlock = { _, outStatus in
            if self.hasConsumedInput {
                outStatus.pointee = .noDataNow
                return nil
            }
            self.hasConsumedInput = true
            outStatus.pointee = .haveData
            return inputBuffer
        }
        converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

        if let error {
            ContextLog.error("conversion failed: \(error.localizedDescription)", "mic")
            return
        }

        guard let channelData = outputBuffer.floatChannelData?[0] else { return }
        let processedFrameLength = Int(outputBuffer.frameLength)
        guard processedFrameLength > 0 else { return }

        var pcm = [Int16]()
        pcm.reserveCapacity(processedFrameLength)
        var sumOfSquares: Float = 0

        for i in 0..<processedFrameLength {
            let sample = channelData[i]
            let pcmSample = Int16(max(-32768, min(32767, sample * 32767)))
            pcm.append(pcmSample)

            let normalized = Float(pcmSample) / 32767.0
            sumOfSquares += normalized * normalized

            // Accumulate the watchdog peak here rather than in a second pass over the buffer:
            // this is the audio callback hot path.
            let absoluteSample = pcmSample == Int16.min ? Int16.max : Int16(pcmSample.magnitude)
            if absoluteSample > watchdogWindowPeak { watchdogWindowPeak = absoluteSample }
        }

        // Little-endian, which is native on Apple platforms.
        let byteData = pcm.withUnsafeBufferPointer { Data(buffer: $0) }

        checkSilentMicWindow()
        reportLevel(rms: sqrt(sumOfSquares / Float(processedFrameLength)))

        onChunk?(byteData)
    }

    private func reportLevel(rms: Float) {
        guard let levelHandler = onLevel else { return }

        // Soft noise floor: subtract it rather than hard-cutting, so quiet speech survives.
        let cleanedRms = max(0.0, rms - noiseFloor)
        if cleanedRms > smoothedLevel {
            // Rising: follow immediately, so the meter feels responsive.
            smoothedLevel = cleanedRms
        } else {
            // Falling: decay, so the meter animates instead of snapping to zero.
            smoothedLevel *= decayRate
            if smoothedLevel < 0.001 { smoothedLevel = 0 }
        }

        let level = min(Float(1.0), smoothedLevel)
        DispatchQueue.main.async { levelHandler(level) }
    }

    // MARK: - Silent-mic watchdog

    private func resetWatchdog() {
        watchdogWindowPeak = 0
        watchdogWindowStart = 0
        consecutiveSilentWindows = 0
        silenceRecoveryArmed = true
        silenceRecoveryCount = 0
        lastSilenceRecoveryTime = 0
    }

    /// Closes a ~1 s window and recovers when the device is alive but delivering zeros.
    /// macOS happily accepts the IOProc and then feeds silence — most often when a Bluetooth
    /// headset flips between A2DP and SCO/HFP, but a stale HAL route on any transport does it
    /// too, so detection is not restricted to Bluetooth. Called on the IO thread.
    private func checkSilentMicWindow() {
        let now = CFAbsoluteTimeGetCurrent()
        if watchdogWindowStart == 0 { watchdogWindowStart = now }
        guard now - watchdogWindowStart >= 1.0 else { return }

        let peak = watchdogWindowPeak
        watchdogWindowPeak = 0
        watchdogWindowStart = now

        if peak <= silentPeakThreshold {
            consecutiveSilentWindows += 1
        } else {
            consecutiveSilentWindows = 0
        }

        // Re-arm once the post-recovery cooldown has elapsed, so a mic that recovered and
        // later re-wedged is caught again — this is a rolling watchdog, not a one-shot latch.
        if !silenceRecoveryArmed, now - lastSilenceRecoveryTime >= silentRecoveryCooldown {
            silenceRecoveryArmed = true
        }

        guard silenceRecoveryArmed,
            silenceRecoveryCount < maxSilentRecoveriesPerSession,
            consecutiveSilentWindows >= silentWindowThreshold
        else { return }

        let silentWindows = consecutiveSilentWindows
        silenceRecoveryArmed = false
        silenceRecoveryCount += 1
        lastSilenceRecoveryTime = now
        // Require a fresh run of silent windows before the next recovery.
        consecutiveSilentWindows = 0

        let wasBluetooth = Self.isBluetoothTransport(deviceID: deviceID)
        ContextLog.info(
            "input silent for \(silentWindows)s (bluetooth=\(wasBluetooth)) — rebuilding capture", "mic")

        queue.async { [weak self] in
            guard let self, self.isCapturing else { return }
            // A Bluetooth mic that returns zeros usually cannot be fixed by reopening it: the
            // headset is stuck in the wrong profile. Bind to the built-in mic instead, which
            // also leaves the headset in A2DP for playback.
            if wasBluetooth, let builtIn = Self.findBuiltInMicDeviceID() {
                self.fallbackDeviceID = builtIn
                ContextLog.info("falling back to the built-in mic", "mic")
            }
            self.handleConfigurationChange()
        }
    }

    // MARK: - Property listeners

    private func installDefaultDeviceListener() {
        guard defaultDeviceListenerBlock == nil else { return }

        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self else { return }
            self.queue.async {
                // The system input changed: a built-in fallback installed for a dead Bluetooth
                // mic is stale, and the user's choice outranks it.
                self.fallbackDeviceID = nil
                self.handleConfigurationChange()
            }
        }
        defaultDeviceListenerBlock = block

        AudioObjectAddPropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject), &address, listenerQueue, block)
    }

    private func installDeviceFormatListener() {
        guard deviceFormatListenerBlock == nil, deviceID != kAudioObjectUnknown else { return }

        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            guard let self else { return }
            self.queue.async { self.handleConfigurationChange() }
        }
        deviceFormatListenerBlock = block

        AudioObjectAddPropertyListenerBlock(deviceID, &address, listenerQueue, block)
    }

    private func removePropertyListeners() {
        removeDefaultDeviceListener()
        removeDeviceFormatListener()
    }

    private func removeDefaultDeviceListener() {
        guard let block = defaultDeviceListenerBlock else { return }
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectRemovePropertyListenerBlock(
            AudioObjectID(kAudioObjectSystemObject), &address, listenerQueue, block)
        defaultDeviceListenerBlock = nil
    }

    private func removeDeviceFormatListener() {
        guard let block = deviceFormatListenerBlock, deviceID != kAudioObjectUnknown else {
            deviceFormatListenerBlock = nil
            return
        }
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectRemovePropertyListenerBlock(deviceID, &address, listenerQueue, block)
        deviceFormatListenerBlock = nil
    }

    // MARK: - Rebuilding the stack

    /// Tears the IOProc down and rebuilds it against whatever the device situation now is:
    /// a new default input, a format change, or a device that went silent.
    private func handleConfigurationChange() {
        guard isCapturing, !isReconfiguring else { return }
        isReconfiguring = true

        if let procID = ioProcID, deviceID != kAudioObjectUnknown {
            AudioDeviceStop(deviceID, procID)
            AudioDeviceDestroyIOProcID(deviceID, procID)
            ioProcID = nil
        }
        // The device is about to change, so its format listener has to go with it.
        removeDeviceFormatListener()

        // Let the hardware settle before reopening; a device queried immediately after a route
        // change reports a format it is not actually ready to deliver.
        queue.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.reconfigure(retryCount: 0)
        }
    }

    private func reconfigure(retryCount: Int) {
        guard isCapturing, isReconfiguring else { return }

        let newDeviceID: AudioDeviceID
        do {
            newDeviceID = try resolveInputDeviceID()
        } catch {
            retryOrGiveUp(retryCount: retryCount, reason: "no input device")
            return
        }
        deviceID = newDeviceID

        guard let streamFormat = getStreamFormat(for: newDeviceID),
            streamFormat.mSampleRate > 0,
            streamFormat.mChannelsPerFrame > 0
        else {
            retryOrGiveUp(retryCount: retryCount, reason: "no usable stream format")
            return
        }
        detectedSampleRate = streamFormat.mSampleRate

        do {
            try buildConverter(sourceSampleRate: streamFormat.mSampleRate)
            try startIOProc()
        } catch {
            retryOrGiveUp(retryCount: retryCount, reason: error.localizedDescription)
            return
        }

        resetWatchdog()
        installDefaultDeviceListener()
        installDeviceFormatListener()
        isReconfiguring = false
        ContextLog.info(
            "rebuilt on device \(newDeviceID) at \(Int(streamFormat.mSampleRate))Hz "
                + "\(streamFormat.mChannelsPerFrame)ch", "mic")
    }

    private func retryOrGiveUp(retryCount: Int, reason: String) {
        guard retryCount < Self.maxRetries else {
            ContextLog.error("gave up rebuilding after \(retryCount + 1) attempts: \(reason)", "mic")
            // Do not leave a zombie capture claiming to be running — the app reports state
            // from `isRunning`, and a silent "running" mic is worse than an honest stop.
            teardownOnQueue()
            return
        }
        let delay = Double(retryCount + 1)  // 1s, 2s, 3s backoff
        ContextLog.info("rebuild attempt \(retryCount + 1) failed (\(reason)), retrying in \(delay)s", "mic")
        queue.asyncAfter(deadline: .now() + delay) { [weak self] in
            self?.reconfigure(retryCount: retryCount + 1)
        }
    }

    // MARK: - CoreAudio property helpers

    private func getStreamFormat(for deviceID: AudioObjectID) -> AudioStreamBasicDescription? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamFormat,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var format = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        let status = AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &format)
        return status == noErr ? format : nil
    }

    private static func currentDefaultInputDeviceID() -> AudioDeviceID? {
        var deviceID: AudioDeviceID = kAudioObjectUnknown
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceID)
        guard status == noErr, isAvailableInputDevice(deviceID) else { return nil }
        return deviceID
    }

    private static func isAvailableInputDevice(_ deviceID: AudioDeviceID) -> Bool {
        deviceID != kAudioObjectUnknown && deviceID != kAudioDeviceUnknown && deviceHasInputChannels(deviceID)
    }

    private static func audioDeviceIDs() -> [AudioDeviceID] {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard
            AudioObjectGetPropertyDataSize(
                AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr
        else { return [] }

        let count = Int(size) / MemoryLayout<AudioDeviceID>.size
        guard count > 0 else { return [] }
        var deviceIDs = [AudioDeviceID](repeating: kAudioObjectUnknown, count: count)
        guard
            AudioObjectGetPropertyData(
                AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &deviceIDs) == noErr
        else { return [] }
        return deviceIDs
    }

    private static func deviceStringProperty(
        _ deviceID: AudioDeviceID, selector: AudioObjectPropertySelector
    ) -> String? {
        var value: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard
            AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &value) == noErr,
            let string = value?.takeRetainedValue()
        else { return nil }
        return string as String
    }

    private static func deviceTransportType(_ deviceID: AudioDeviceID) -> UInt32? {
        var transport: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyTransportType,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        guard AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, &transport) == noErr else {
            return nil
        }
        return transport
    }

    /// True when the device has at least one input channel. Output-only devices show up in the
    /// same enumeration and must never be opened for capture.
    private static func deviceHasInputChannels(_ deviceID: AudioDeviceID) -> Bool {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(deviceID, &address, 0, nil, &size) == noErr, size > 0
        else { return false }

        let raw = UnsafeMutableRawPointer.allocate(
            byteCount: Int(size), alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { raw.deallocate() }
        let bufferList = raw.bindMemory(to: AudioBufferList.self, capacity: 1)
        guard AudioObjectGetPropertyData(deviceID, &address, 0, nil, &size, bufferList) == noErr else {
            return false
        }
        for buffer in UnsafeMutableAudioBufferListPointer(bufferList) where buffer.mNumberChannels > 0 {
            return true
        }
        return false
    }

    deinit {
        if isCapturing {
            removePropertyListeners()
            if let procID = ioProcID, deviceID != kAudioObjectUnknown {
                // Call the HAL teardown directly — do NOT `queue.sync` here. deinit can run *on*
                // `queue` (the last reference released inside a queue block), and dispatching
                // sync to the current queue deadlocks. No references remain, so no concurrent
                // queue work can touch this object, and these HAL calls are thread-safe.
                AudioDeviceStop(deviceID, procID)
                AudioDeviceDestroyIOProcID(deviceID, procID)
            }
        }
    }
}
