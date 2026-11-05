import AudioToolbox
import AVFoundation
import os
@preconcurrency import TwilioVoice

/// A Twilio audio device that also hands both sides of the call to the transcript: a VoiceProcessingIO
/// unit whose playout callback pulls the remote side from Twilio (channel 2) and whose record callback
/// captures the microphone for Twilio (channel 1). 48 kHz mono PCM16.
/// Port of Flutter's `ios/Runner/PhoneCalls/OmiRecordingAudioDevice.swift`.
///
/// Twilio calls the `AudioDevice` methods on its own threads and Core Audio calls the callbacks on its
/// realtime thread, so all state sits behind one unfair lock (nanoseconds, safe on the audio thread);
/// the capture buffer is allocated in `startCapturing`, never on the audio thread.
final class CallRecordingAudioDevice: NSObject, @unchecked Sendable {
    static let sampleRate: Double = 48000
    static let framesPerBuffer: UInt32 = 1024
    static let bytesPerFrame = 2

    typealias Tap = @Sendable (Data, PhoneCallAudioChannel) -> Void

    fileprivate struct State {
        var unit: AudioUnit?
        /// CallKit may activate the session before Twilio made the unit; such a start is honored later.
        var pendingStart = false
        var renderContext: AudioDeviceContext?
        var capture: CaptureBuffer?
        var micMuted = false
        var tap: Tap?
    }

    fileprivate let state = OSAllocatedUnfairLock(uncheckedState: State())
    private var callbackRef: UnsafeMutableRawPointer?
    private let format = AudioFormat(
        channels: 1, sampleRate: UInt32(CallRecordingAudioDevice.sampleRate), framesPerBuffer: Int(CallRecordingAudioDevice.framesPerBuffer)
    )

    deinit {
        if let unit = state.withLockUnchecked({ $0.unit }) { Self.dispose(unit) }
        callbackRef.map { Unmanaged<CallRecordingAudioDevice>.fromOpaque($0).release() }
    }

    func setTap(_ tap: Tap?) {
        state.withLockUnchecked { $0.tap = tap }
    }

    /// Muted: the microphone side is not transcribed (Twilio mutes the call itself).
    func setMicMuted(_ muted: Bool) {
        state.withLockUnchecked { $0.micMuted = muted }
    }

    /// The audio session is active (CallKit): run the unit, or remember to once it exists.
    @discardableResult
    func start() -> Bool {
        state.withLockUnchecked { state in
            guard let unit = state.unit else {
                state.pendingStart = true
                return false
            }
            let started = AudioOutputUnitStart(unit) == noErr
            if started { state.pendingStart = false }
            return started
        }
    }

    private func honorPendingStart() {
        state.withLockUnchecked { state in
            guard state.pendingStart, let unit = state.unit, AudioOutputUnitStart(unit) == noErr else { return }
            state.pendingStart = false
        }
    }

    private static func dispose(_ unit: AudioUnit) {
        AudioOutputUnitStop(unit)
        AudioUnitUninitialize(unit)
        AudioComponentInstanceDispose(unit)
    }

    // MARK: Core Audio

    private func makeUnit() -> Bool {
        if let old = state.withLockUnchecked({ state -> AudioUnit? in
            defer { state.unit = nil }
            return state.unit
        }) { Self.dispose(old) }
        var description = AudioComponentDescription(
            componentType: kAudioUnitType_Output, componentSubType: kAudioUnitSubType_VoiceProcessingIO,
            componentManufacturer: kAudioUnitManufacturer_Apple, componentFlags: 0, componentFlagsMask: 0
        )
        guard let component = AudioComponentFindNext(nil, &description) else { return false }
        var created: AudioUnit?
        guard AudioComponentInstanceNew(component, &created) == noErr, let unit = created else { return false }
        guard configure(unit) else {
            AudioComponentInstanceDispose(unit)
            return false
        }
        state.withLockUnchecked { $0.unit = unit }
        return true
    }

    private func configure(_ unit: AudioUnit) -> Bool {
        var enable: UInt32 = 1
        let size32 = UInt32(MemoryLayout<UInt32>.size)
        var format = AudioStreamBasicDescription(
            mSampleRate: Self.sampleRate, mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
            mBytesPerPacket: UInt32(Self.bytesPerFrame), mFramesPerPacket: 1, mBytesPerFrame: UInt32(Self.bytesPerFrame),
            mChannelsPerFrame: 1, mBitsPerChannel: 16, mReserved: 0
        )
        let formatSize = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        if callbackRef == nil { callbackRef = Unmanaged.passRetained(self).toOpaque() }
        var playout = AURenderCallbackStruct(inputProc: callPlayoutCallback, inputProcRefCon: callbackRef)
        var record = AURenderCallbackStruct(inputProc: callRecordCallback, inputProcRefCon: callbackRef)
        let callbackSize = UInt32(MemoryLayout<AURenderCallbackStruct>.size)
        let steps: [OSStatus] = [
            AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO, kAudioUnitScope_Input, 1, &enable, size32),
            AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO, kAudioUnitScope_Output, 0, &enable, size32),
            AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Output, 1, &format, formatSize),
            AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &format, formatSize),
            AudioUnitSetProperty(unit, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &playout, callbackSize),
            AudioUnitSetProperty(unit, kAudioOutputUnitProperty_SetInputCallback, kAudioUnitScope_Global, 0, &record, callbackSize),
            AudioUnitInitialize(unit),
            AudioOutputUnitStart(unit),
        ]
        return steps.allSatisfy { $0 == noErr }
    }
}

enum PhoneCallAudioChannel: UInt8, Sendable {
    case microphone = 1, remote = 2
}

/// The microphone buffer the record callback renders into (allocated once per call).
final class CaptureBuffer: @unchecked Sendable {
    let context: AudioDeviceContext
    let unit: AudioUnit
    let list: UnsafeMutablePointer<AudioBufferList>
    let capacity: UInt32

    init(context: AudioDeviceContext, unit: AudioUnit) {
        self.context = context
        self.unit = unit
        capacity = CallRecordingAudioDevice.framesPerBuffer * UInt32(CallRecordingAudioDevice.bytesPerFrame)
        list = .allocate(capacity: 1)
        list.pointee.mNumberBuffers = 1
        list.pointee.mBuffers.mNumberChannels = 1
        list.pointee.mBuffers.mDataByteSize = capacity
        list.pointee.mBuffers.mData = .allocate(byteCount: Int(capacity), alignment: 16)
    }

    deinit {
        list.pointee.mBuffers.mData?.deallocate()
        list.deallocate()
    }
}

extension CallRecordingAudioDevice: AudioDevice {
    func captureFormat() -> AudioFormat? {
        format
    }

    func renderFormat() -> AudioFormat? {
        format
    }

    func initializeRenderer() -> Bool {
        true
    }

    func startRendering(_ context: AudioDeviceContext) -> Bool {
        state.withLockUnchecked { $0.renderContext = context }
        return true
    }

    func stopRendering() -> Bool {
        state.withLockUnchecked { $0.renderContext = nil }
        return true
    }

    func initializeCapturer() -> Bool {
        guard makeUnit() else { return false }
        honorPendingStart()
        return true
    }

    func startCapturing(_ context: AudioDeviceContext) -> Bool {
        let ready = state.withLockUnchecked { state -> Bool in
            guard let unit = state.unit else { return false }
            state.capture = CaptureBuffer(context: context, unit: unit)
            return true
        }
        honorPendingStart()
        return ready
    }

    func stopCapturing() -> Bool {
        state.withLockUnchecked { $0.capture = nil }
        return true
    }
}

// The remote side: pulled from Twilio, played, and tapped as channel 2.
// swiftlint:disable:next function_parameter_count
private func callPlayoutCallback(
    refCon: UnsafeMutableRawPointer, _: UnsafeMutablePointer<AudioUnitRenderActionFlags>, _: UnsafePointer<AudioTimeStamp>,
    _: UInt32, frames: UInt32, ioData: UnsafeMutablePointer<AudioBufferList>?
) -> OSStatus {
    guard let ioData else { return noErr }
    let device = Unmanaged<CallRecordingAudioDevice>.fromOpaque(refCon).takeUnretainedValue()
    let (context, tap) = device.state.withLockUnchecked { ($0.renderContext, $0.tap) }
    let buffers = UnsafeMutableAudioBufferListPointer(ioData)
    guard let context else {
        for buffer in buffers { if let data = buffer.mData { memset(data, 0, Int(buffer.mDataByteSize)) } }
        return noErr
    }
    guard let first = buffers.first, let data = first.mData else { return noErr }
    let size = Int(frames) * CallRecordingAudioDevice.bytesPerFrame
    AudioDeviceReadRenderData(context: context, data: data, sizeInBytes: size)
    tap?(Data(bytes: data, count: size), .remote)
    return noErr
}

// The microphone: rendered into the call's buffer, tapped as channel 1 (unless muted), sent to Twilio.
// swiftlint:disable:next function_parameter_count
private func callRecordCallback(
    refCon: UnsafeMutableRawPointer, flags: UnsafeMutablePointer<AudioUnitRenderActionFlags>, time: UnsafePointer<AudioTimeStamp>,
    bus: UInt32, frames: UInt32, _: UnsafeMutablePointer<AudioBufferList>?
) -> OSStatus {
    let device = Unmanaged<CallRecordingAudioDevice>.fromOpaque(refCon).takeUnretainedValue()
    let (capture, tap) = device.state.withLockUnchecked { ($0.capture, $0.micMuted ? nil : $0.tap) }
    guard let capture else { return noErr }
    let needed = frames * UInt32(CallRecordingAudioDevice.bytesPerFrame)
    guard needed <= capture.capacity else { return noErr }
    capture.list.pointee.mBuffers.mDataByteSize = needed
    let status = AudioUnitRender(capture.unit, flags, time, bus, frames, capture.list)
    guard status == noErr, let data = capture.list.pointee.mBuffers.mData else { return status }
    let size = Int(capture.list.pointee.mBuffers.mDataByteSize)
    tap?(Data(bytes: data, count: size), .microphone)
    AudioDeviceWriteCaptureData(context: capture.context, data: data, sizeInBytes: size)
    return status
}
