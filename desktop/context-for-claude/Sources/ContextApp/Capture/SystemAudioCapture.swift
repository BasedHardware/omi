import AppKit
@preconcurrency import AVFoundation
@preconcurrency import CoreAudio
import Foundation

/// Captures everything the machine plays out of its speakers — the other side of a call —
/// with a CoreAudio process tap (macOS 14.4+), converted to 16 kHz mono Int16 LE PCM.
///
/// This is a direct port of Omi desktop's `SystemAudioCaptureService`, which is the proven
/// implementation: global tap → private aggregate device → `AVAudioConverter` → IOProc.
/// Every deviation from that shape has previously produced audible artifacts or phantom
/// devices, so the structure is deliberately conservative.
@available(macOS 14.4, *)
final class SystemAudioCapture: AudioSource, @unchecked Sendable {

    // MARK: - State

    // Everything below is owned by `audioQueue`. The HAL IO thread reads (never writes)
    // the converter/format/handler references while the device is running; `audioQueue`
    // is what serialises a stop's clear against a restart's fresh assignment.
    private var tapID: AudioObjectID = kAudioObjectUnknown
    private var aggregateDeviceID: AudioObjectID = kAudioObjectUnknown
    private var ioProcID: AudioDeviceIOProcID?
    private var audioConverter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var sourceSampleRate: Double = 0
    private var chunkHandler: (@Sendable (Data) -> Void)?
    private var levelHandler: (@Sendable (Float) -> Void)?

    // Written on `audioQueue`, read from the HAL IO thread and from `isRunning` on any
    // thread. A plain Bool rather than a lock: the IO callback is real time and must never
    // block, and a stale read costs at most one discarded buffer.
    private nonisolated(unsafe) var capturing = false

    // Flipped exactly once per `convert()` call by the synchronous AVAudioConverter input
    // block (a @Sendable closure) on the non-reentrant CoreAudio IO thread. Reset at the
    // top of every `handleAudioInput` call.
    private nonisolated(unsafe) var hasConsumedInput = false

    private let targetSampleRate: Double = 16_000
    private let tapUUID = UUID()

    /// CoreAudio HAL calls are synchronous IPC to `coreaudiod`; after wake from sleep they
    /// can block for seconds. Nothing touching the HAL runs on the caller's thread.
    private let audioQueue = DispatchQueue(label: "com.omi.context-for-claude.systemaudio")

    private var terminationObserver: NSObjectProtocol?

    private static let logCategory = "system-audio"

    // MARK: - Lifecycle

    init() {
        // Last line of defence against a leaked tap. A process tap and its aggregate device
        // are registered with coreaudiod, not with our address space: if the app exits with
        // one live, it can linger as a phantom audio device that outlives the app. Terminate
        // arrives on the main thread and the synchronous hop is bounded by one HAL teardown.
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            guard let self else { return }
            self.audioQueue.sync { self.cleanup() }
        }
    }

    deinit {
        if let terminationObserver {
            NotificationCenter.default.removeObserver(terminationObserver)
        }
        // Call the HAL teardown directly — do NOT `audioQueue.sync` here. `deinit` can run
        // *on* audioQueue (the last strong reference is held by the teardown block dispatched
        // from `stop()`), and dispatching sync to the current serial queue deadlocks it
        // permanently. The object has no remaining references, so no concurrent audioQueue
        // work can touch it, and these HAL calls are thread-safe.
        cleanup()
    }

    // MARK: - AudioSource

    var isRunning: Bool { capturing }

    func start(
        onChunk: @escaping @Sendable (Data) -> Void,
        onLevel: @escaping @Sendable (Float) -> Void
    ) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            audioQueue.async { [weak self] in
                guard let self else {
                    continuation.resume()
                    return
                }
                guard !self.capturing else {
                    ContextLog.info("Already capturing system audio", Self.logCategory)
                    continuation.resume()
                    return
                }
                self.chunkHandler = onChunk
                self.levelHandler = onLevel
                do {
                    try self.startOnQueue()
                    continuation.resume()
                } catch {
                    self.chunkHandler = nil
                    self.levelHandler = nil
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    func stop() {
        audioQueue.async { // strong self: the object must outlive its own HAL teardown
            guard self.capturing else { return }
            self.capturing = false
            self.cleanup()
            self.chunkHandler = nil
            self.levelHandler = nil
            ContextLog.info("Stopped capturing system audio", Self.logCategory)
        }
    }

    // MARK: - Setup

    /// All blocking CoreAudio HAL setup. Must run on `audioQueue`.
    private func startOnQueue() throws {
        // 1. A global tap over every process except ourselves, muting nothing. `.unmuted` is not
        //    optional: any other mute behaviour silences the user's own playback while we listen.
        let tapDescription = Self.makeGlobalTapDescription(
            name: "Context for Claude System Audio Tap", uuid: tapUUID)

        var status = AudioHardwareCreateProcessTap(tapDescription, &tapID)
        guard status == noErr else {
            // The one HAL call the consent governs, so the only one whose refusal is a permission
            // answer. Everything below this line needs a tap that already exists.
            if Self.tapCreationWasRefused(status) { Permissions.noteSystemAudioTapRefused() }
            throw AudioCaptureError.tapFailed(status)
        }
        ContextLog.info("Created process tap \(tapID)", Self.logCategory)

        // 2. A private aggregate device fed by that tap.
        //
        // IMPORTANT: drift compensation is enabled per-tap via kAudioSubTapDriftCompensationKey.
        // Without it the aggregate device's clock drifts against the real output device and the
        // system resamples on every IO cycle to compensate, which puts periodic crackling into
        // *all* system audio playback — music, calls, everything — even though we only read from
        // the tap. CoreAudio expects a CFNumber here ("non-zero value indicates that drift
        // compensation is enabled", <CoreAudio/AudioHardware.h>), not a CFBoolean.
        let aggregateDescription: [String: Any] = [
            kAudioAggregateDeviceNameKey as String: "Context for Claude System Audio Tap Device",
            kAudioAggregateDeviceUIDKey as String: "omi.ambient.systemaudio.\(tapUUID.uuidString)",
            kAudioAggregateDeviceIsPrivateKey as String: true,
            kAudioAggregateDeviceTapListKey as String: [
                [
                    kAudioSubTapUIDKey as String: tapUUID.uuidString,
                    kAudioSubTapDriftCompensationKey as String: NSNumber(value: 1),
                    kAudioSubTapDriftCompensationQualityKey as String:
                        NSNumber(value: kAudioAggregateDriftCompensationMaxQuality),
                ]
            ],
            kAudioAggregateDeviceTapAutoStartKey as String: true,
        ]

        status = AudioHardwareCreateAggregateDevice(
            aggregateDescription as CFDictionary, &aggregateDeviceID)
        guard status == noErr else {
            cleanup()
            throw AudioCaptureError.aggregateFailed(status)
        }
        ContextLog.info("Created aggregate device \(aggregateDeviceID)", Self.logCategory)

        // 3. Whatever rate and layout the tap actually hands us.
        guard let format = Self.streamFormat(for: aggregateDeviceID) else {
            cleanup()
            throw AudioCaptureError.formatUnavailable
        }
        sourceSampleRate = format.mSampleRate
        ContextLog.info(
            "Tap format \(format.mSampleRate) Hz, \(format.mChannelsPerFrame) ch, \(format.mBitsPerChannel) bit",
            Self.logCategory)

        guard let inputFmt = Self.makeConverterInputFormat(sampleRate: format.mSampleRate),
            let targetFmt = AVAudioFormat(standardFormatWithSampleRate: targetSampleRate, channels: 1),
            let converter = AVAudioConverter(from: inputFmt, to: targetFmt)
        else {
            cleanup()
            throw AudioCaptureError.formatUnavailable
        }
        inputFormat = inputFmt
        targetFormat = targetFmt
        audioConverter = converter

        // 4. IO proc, then start.
        status = AudioDeviceCreateIOProcIDWithBlock(&ioProcID, aggregateDeviceID, nil) {
            [weak self] _, inInputData, _, _, _ in
            self?.handleAudioInput(inInputData)
        }
        guard status == noErr else {
            cleanup()
            throw AudioCaptureError.ioProcFailed(status)
        }

        status = AudioDeviceStart(aggregateDeviceID, ioProcID)
        guard status == noErr else {
            cleanup()
            throw AudioCaptureError.ioProcFailed(status)
        }

        capturing = true
        ContextLog.info("Started capturing system audio", Self.logCategory)
    }

    // MARK: - Teardown

    /// Destroys the tap. Idempotent: a destroyed tap leaves `kAudioObjectUnknown` behind so a
    /// second call is a no-op and can never double-destroy an id coreaudiod has reused.
    private func cleanupTap() {
        if tapID != kAudioObjectUnknown {
            AudioHardwareDestroyProcessTap(tapID)
            tapID = kAudioObjectUnknown
        }
    }

    /// Full teardown, in HAL order: stop the IO proc, destroy it, destroy the aggregate device,
    /// destroy the tap. Idempotent, so start-failure paths, `stop()`, terminate, and `deinit`
    /// can all call it and only the first one does work.
    private func cleanup() {
        if let procID = ioProcID, aggregateDeviceID != kAudioObjectUnknown {
            AudioDeviceStop(aggregateDeviceID, procID)
            AudioDeviceDestroyIOProcID(aggregateDeviceID, procID)
        }
        ioProcID = nil

        if aggregateDeviceID != kAudioObjectUnknown {
            AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
            aggregateDeviceID = kAudioObjectUnknown
        }

        cleanupTap()

        audioConverter = nil
        inputFormat = nil
        targetFormat = nil
        sourceSampleRate = 0
    }

    // MARK: - Audio path

    private static func streamFormat(for deviceID: AudioObjectID) -> AudioStreamBasicDescription? {
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

    /// The converter input format is ALWAYS mono: `handleAudioInput` down-mixes stereo source
    /// frames into channel 0 and never fills a second channel, so the converter must see mono
    /// and do sample-rate conversion only. Declaring the source channel count here made the
    /// converter run its own stereo→mono downmix against the unwritten channel 1, averaging the
    /// real mix against silence — roughly 6 dB of attenuation on everything fed to transcription.
    private static func makeConverterInputFormat(sampleRate: Double) -> AVAudioFormat? {
        AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: sampleRate,
            channels: 1,
            interleaved: false
        )
    }

    /// Frames a `sourceSampleRate`→`targetSampleRate` conversion of `frameCount` input frames
    /// produces. Returns 0 when the source rate is unknown: dividing by a zero rate yields
    /// `.infinity`, and `AVAudioFrameCount(.infinity)` traps the real-time tap thread — reachable
    /// when the tap reports no rate at start or teardown zeroes the rate mid-callback.
    private static func resampledFrameCapacity(
        frameCount: AVAudioFrameCount, sourceSampleRate: Double, targetSampleRate: Double
    ) -> AVAudioFrameCount {
        guard frameCount > 0, sourceSampleRate > 0, targetSampleRate > 0 else { return 0 }
        return AVAudioFrameCount(ceil(Double(frameCount) * targetSampleRate / sourceSampleRate))
    }

    /// Runs on the CoreAudio HAL IO thread. Allocation-light, never blocking, never locking.
    private func handleAudioInput(_ inputData: UnsafePointer<AudioBufferList>?) {
        guard capturing,
            let bufferList = inputData?.pointee,
            let converter = audioConverter,
            let inputFmt = inputFormat,
            let targetFmt = targetFormat
        else { return }

        let buffer = bufferList.mBuffers
        guard let data = buffer.mData, buffer.mDataByteSize > 0 else { return }

        let bytesPerFrame = UInt32(MemoryLayout<Float32>.size) * buffer.mNumberChannels
        guard bytesPerFrame > 0 else { return }
        let frameCount = buffer.mDataByteSize / bytesPerFrame
        guard frameCount > 0,
            let inputBuffer = AVAudioPCMBuffer(pcmFormat: inputFmt, frameCapacity: frameCount),
            let floatData = inputBuffer.floatChannelData
        else { return }

        inputBuffer.frameLength = frameCount

        // System audio arrives interleaved Float32, usually stereo. Average to mono.
        let srcPtr = data.assumingMemoryBound(to: Float32.self)
        let channelCount = Int(buffer.mNumberChannels)
        let monoPtr = floatData[0]

        if channelCount >= 2 {
            for i in 0..<Int(frameCount) {
                let left = srcPtr[i * channelCount]
                let right = srcPtr[i * channelCount + 1]
                monoPtr[i] = (left + right) / 2.0
            }
        } else {
            memcpy(monoPtr, srcPtr, Int(buffer.mDataByteSize))
        }

        let outputFrameCapacity = Self.resampledFrameCapacity(
            frameCount: frameCount,
            sourceSampleRate: sourceSampleRate,
            targetSampleRate: targetSampleRate)
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
            ContextLog.error("Conversion failed: \(error.localizedDescription)", Self.logCategory)
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
            let scaled = max(-32768, min(32767, sample * 32767))
            pcm.append(Int16(scaled))
            let normalized = scaled / 32767.0
            sumOfSquares += normalized * normalized
        }

        let byteData = pcm.withUnsafeBufferPointer { Data(buffer: $0) }

        if let levelHandler {
            let rms = sqrt(sumOfSquares / Float(processedFrameLength))
            let level = min(Float(1.0), max(Float(0.0), rms))
            DispatchQueue.main.async { levelHandler(level) }
        }

        chunkHandler?(byteData)
    }

    // MARK: - Tap description

    /// The one place a tap is described, for both the capture path and the consent prime.
    ///
    /// The exclude list is what keeps our own output off the tap. It used to be empty, which made
    /// this a global tap over *every* process including this one — so the first-run cinematic's bed
    /// and swooshes, and every click a Settings surface plays while a session is live, were recorded,
    /// transcribed, and filed in the user's own conversation history as if somebody had said them.
    ///
    /// The exclusion is unconditional and lasts the whole process lifetime, deliberately not scoped
    /// to onboarding: chrome sounds can fire from any surface at any time, including while capture
    /// is already running.
    static func makeGlobalTapDescription(name: String, uuid: UUID) -> CATapDescription {
        makeGlobalTapDescription(name: name, uuid: uuid, excluding: excludedProcessObjects())
    }

    /// The construction on its own, with the exclusion handed in, so it can be exercised without
    /// the HAL.
    static func makeGlobalTapDescription(
        name: String,
        uuid: UUID,
        excluding processObjects: [AudioObjectID]
    ) -> CATapDescription {
        let description = CATapDescription(stereoGlobalTapButExcludeProcesses: processObjects)
        description.uuid = uuid
        description.name = name
        description.muteBehavior = .unmuted
        return description
    }

    /// Just us.
    ///
    /// `CATapDescription` takes CoreAudio process *object* ids, not pids — the Swift signature is
    /// `[AudioObjectID]`. A raw pid poured into an `AudioObjectID` names some unrelated audio object
    /// or nothing at all, which would read exactly like a fix while our own audio kept landing in the
    /// tap. `kAudioHardwarePropertyTranslatePIDToProcessObject` is the only correct way across.
    static func excludedProcessObjects() -> [AudioObjectID] {
        guard let own = ownProcessObject() else {
            // Fail open rather than refuse to capture: losing the other side of every call is worse
            // than the noise. Logged as an error, because it means our own sounds are being recorded.
            ContextLog.error(
                "could not resolve this app's CoreAudio process object; the tap cannot exclude us",
                logCategory)
            return []
        }
        return [own]
    }

    /// This process's CoreAudio process object, or `nil` if the HAL will not translate it.
    static func ownProcessObject() -> AudioObjectID? {
        var pid = pid_t(ProcessInfo.processInfo.processIdentifier)
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyTranslatePIDToProcessObject,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var objectID: AudioObjectID = kAudioObjectUnknown
        var size = UInt32(MemoryLayout<AudioObjectID>.size)
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &address,
            UInt32(MemoryLayout<pid_t>.size),
            &pid,
            &size,
            &objectID)
        guard status == noErr, objectID != kAudioObjectUnknown else { return nil }
        return objectID
    }

    // MARK: - Permission

    /// **Tells macOS refusing this process a tap apart from CoreAudio having a bad moment.**
    ///
    /// The system-audio counterpart of `ScreenPipeline.noteIfDeclined`, and it has to be as narrow as
    /// that one for the same reason: what it records lowers the cached grant, which sends the user to
    /// System Settings. Doing that over an ordinary hiccup would be the same lie as the one this whole
    /// area exists to stop, pointing the other way.
    ///
    /// Two things keep it narrow.
    ///
    /// **Only tap creation is judged.** `AudioHardwareCreateProcessTap` is the single call the tap
    /// consent governs; the aggregate device, the stream format, the converter and
    /// `AudioDeviceStart` all come after a tap macOS has already allowed, so their failures are about
    /// devices and formats and are left to the ordinary retry — a display or output-device change, a
    /// renegotiated rate, an IOProc that would not start.
    ///
    /// **And a HAL that cannot answer anything is not a refusal.** `coreaudiod` is synchronous IPC
    /// and this file already documents it blocking for seconds after a wake from sleep, which is
    /// exactly when the engine restarts capture; `kAudioHardwareNotRunningError` and
    /// `kAudioHardwareNotReadyError` name that state, and the right response to it is the next
    /// attempt rather than a sentence about System Settings.
    ///
    /// Everything else from that one call is treated as the refusal, which is the same reading
    /// `primePermission` has always taken of it ("consent likely denied"). The alternative — an
    /// allowlist of the statuses a denial is *believed* to produce — fails silently in the direction
    /// that matters most: a denial answered with an unlisted status would leave the cache vouching for
    /// a dead tap, which is the defect.
    static func tapCreationWasRefused(_ status: OSStatus) -> Bool {
        guard status != noErr else { return false }
        return status != kAudioHardwareNotRunningError && status != kAudioHardwareNotReadyError
    }

    /// Fires the CoreAudio process-tap consent prompt during onboarding instead of mid-call.
    ///
    /// The tap consent — "<app> is requesting to bypass the system private window picker and
    /// directly access your screen and audio" — is separate from the Screen Recording TCC grant
    /// and only fires the first time a tap is actually created. Without this, the first real
    /// conversation is what raises it.
    ///
    /// Builds the identical tap and aggregate device the capture path builds, so macOS shows and
    /// persists the exact same consent, then tears both down immediately. It never creates an IO
    /// proc and never starts capture. Uses local ids only, so it is safe to call concurrently
    /// with a live capture, and it is idempotent once consent is granted.
    ///
    /// - Returns: `true` if the tap was created (consent granted, or already granted);
    ///   `false` if tap creation failed, which is what a denial looks like.
    @discardableResult
    static func primePermission() -> Bool {
        var tapID: AudioObjectID = kAudioObjectUnknown
        var aggregateDeviceID: AudioObjectID = kAudioObjectUnknown

        // Guarantees full teardown on every exit path, in the same order as `cleanup()`.
        // No AudioDeviceStop / AudioDeviceDestroyIOProcID — no IO proc is ever created here.
        func teardown() {
            if aggregateDeviceID != kAudioObjectUnknown {
                AudioHardwareDestroyAggregateDevice(aggregateDeviceID)
                aggregateDeviceID = kAudioObjectUnknown
            }
            if tapID != kAudioObjectUnknown {
                AudioHardwareDestroyProcessTap(tapID)
                tapID = kAudioObjectUnknown
            }
        }

        let tapUUID = UUID()
        let tapDescription = makeGlobalTapDescription(
            name: "Context for Claude System Audio Tap (permission prime)", uuid: tapUUID)

        var status = AudioHardwareCreateProcessTap(tapDescription, &tapID)
        guard status == noErr else {
            ContextLog.error(
                "primePermission tap creation failed (\(status)) — consent likely denied",
                logCategory)
            teardown()
            return false
        }

        // Some macOS versions only register the consent once a tap-backed aggregate device is
        // instantiated, so mirror the real path exactly — including drift compensation.
        let aggregateDescription: [String: Any] = [
            kAudioAggregateDeviceNameKey as String: "Context for Claude System Audio Tap Device",
            kAudioAggregateDeviceUIDKey as String: "omi.ambient.systemaudio.\(tapUUID.uuidString)",
            kAudioAggregateDeviceIsPrivateKey as String: true,
            kAudioAggregateDeviceTapListKey as String: [
                [
                    kAudioSubTapUIDKey as String: tapUUID.uuidString,
                    kAudioSubTapDriftCompensationKey as String: NSNumber(value: 1),
                    kAudioSubTapDriftCompensationQualityKey as String:
                        NSNumber(value: kAudioAggregateDriftCompensationMaxQuality),
                ]
            ],
            kAudioAggregateDeviceTapAutoStartKey as String: true,
        ]

        status = AudioHardwareCreateAggregateDevice(
            aggregateDescription as CFDictionary, &aggregateDeviceID)
        guard status == noErr else {
            // The tap itself was created, so consent already fired. Treat as primed.
            ContextLog.error(
                "primePermission aggregate device creation failed (\(status))", logCategory)
            teardown()
            return true
        }

        teardown()
        ContextLog.info("primePermission complete, tap and aggregate device destroyed", logCategory)
        return true
    }
}
