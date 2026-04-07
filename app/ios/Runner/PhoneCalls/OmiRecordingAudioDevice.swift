import Foundation
import TwilioVoice
import AVFoundation

/// Custom Twilio audio device that captures both local (mic) and remote (speaker) audio streams.
///
/// Architecture:
/// - Replaces Twilio's DefaultAudioDevice with a VoiceProcessingIO audio unit
/// - audioPlayoutCallback: pulls remote audio from Twilio SDK -> plays to speaker -> streams to Flutter
/// - audioRecordCallback: captures mic audio -> sends to Twilio SDK -> streams to Flutter
///
/// Thread Safety:
/// - Audio state (`_audioUnit`, `_renderingContext`, `_capturingContext`) is protected by `@OmiAudioLock`
///   using `os_unfair_lock` (5-10ns per access) — safe for Core Audio real-time callbacks.
/// - Capture buffer is pre-allocated in `startCapturing()`, never on the audio thread.
final class OmiRecordingAudioDevice: NSObject {

    // MARK: - Audio Configuration

    let sampleRate: Double = 48000
    let channelCount: Int = 1
    let sampleSize: Int = 2  // 16-bit
    let framesPerBuffer: UInt32 = 1024

    var bytesPerFrame: Int { sampleSize * channelCount }

    // MARK: - Thread-Safe Audio State

    @OmiAudioLock private var _audioUnit: AudioUnit?
    @OmiAudioLock private var _renderingContext: RenderingContext?
    @OmiAudioLock private var _capturingContext: CapturingContext?

    // Callback reference for Core Audio C callbacks
    private var callbackRefCon: UnsafeMutableRawPointer?

    // Audio formats reported to Twilio
    private var renderingFormat: AudioFormat?
    private var capturingFormat: AudioFormat?

    // MARK: - Mute State

    /// When true, mic audio is not streamed to Flutter.
    /// Set by OmiPhoneCallsPlugin when user toggles mute.
    @OmiAudioLock var isMicStreamMuted: Bool = false

    // MARK: - Audio Data Callback

    /// Called on the audio thread with captured audio data.
    /// channel: 1 = local (mic), 2 = remote (speaker)
    var onAudioData: ((Data, Int) -> Void)?

    // MARK: - Context Types

    class RenderingContext {
        let deviceContext: AudioDeviceContext
        let maxFramesPerBuffer: Int
        var bufferList: UnsafeMutablePointer<AudioBufferList>?

        init(deviceContext: AudioDeviceContext, maxFramesPerBuffer: Int) {
            self.deviceContext = deviceContext
            self.maxFramesPerBuffer = maxFramesPerBuffer
        }
    }

    class CapturingContext {
        let deviceContext: AudioDeviceContext
        let audioUnit: AudioUnit
        let bufferList: UnsafeMutablePointer<AudioBufferList>
        let bufferSizeBytes: UInt32

        /// Pre-allocate buffer at init time — never allocate on the audio thread.
        init(deviceContext: AudioDeviceContext, audioUnit: AudioUnit,
             maxFrames: UInt32, bytesPerFrame: Int) {
            self.deviceContext = deviceContext
            self.audioUnit = audioUnit

            let size = maxFrames * UInt32(bytesPerFrame)
            self.bufferSizeBytes = size

            let bl = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: 1)
            bl.pointee.mNumberBuffers = 1
            bl.pointee.mBuffers.mNumberChannels = 1
            bl.pointee.mBuffers.mDataByteSize = size
            bl.pointee.mBuffers.mData = UnsafeMutableRawPointer.allocate(
                byteCount: Int(size), alignment: 16
            )
            self.bufferList = bl
        }

        deinit {
            bufferList.pointee.mBuffers.mData?.deallocate()
            bufferList.deallocate()
        }
    }

    // MARK: - Init

    override init() {
        super.init()

        renderingFormat = AudioFormat(
            channels: channelCount,
            sampleRate: UInt32(sampleRate),
            framesPerBuffer: Int(framesPerBuffer)
        )
        capturingFormat = AudioFormat(
            channels: channelCount,
            sampleRate: UInt32(sampleRate),
            framesPerBuffer: Int(framesPerBuffer)
        )
    }

    deinit {
        if let unit = _audioUnit {
            AudioOutputUnitStop(unit)
            AudioUnitUninitialize(unit)
            AudioComponentInstanceDispose(unit)
        }
        cleanupCallbacks()
    }

    // MARK: - Bridge Methods (thread-safe access for C callbacks)

    func getRenderingContext() -> RenderingContext? { _renderingContext }
    func getCapturingContext() -> CapturingContext? { _capturingContext }
    func getAudioUnit() -> AudioUnit? { _audioUnit }
    func getMicMuted() -> Bool { isMicStreamMuted }

    // MARK: - Core Audio Setup

    private func setupAudioUnit() -> Bool {
        // Dispose existing
        if let unit = _audioUnit {
            AudioOutputUnitStop(unit)
            AudioUnitUninitialize(unit)
            AudioComponentInstanceDispose(unit)
            _audioUnit = nil
        }
        cleanupCallbacks()

        // Find VoiceProcessingIO
        var desc = AudioComponentDescription(
            componentType: kAudioUnitType_Output,
            componentSubType: kAudioUnitSubType_VoiceProcessingIO,
            componentManufacturer: kAudioUnitManufacturer_Apple,
            componentFlags: 0,
            componentFlagsMask: 0
        )

        guard let component = AudioComponentFindNext(nil, &desc) else {
            print("OmiAudioDevice: VoiceProcessingIO not found")
            return false
        }

        var tempUnit: AudioUnit?
        var status = AudioComponentInstanceNew(component, &tempUnit)
        guard status == noErr, let unit = tempUnit else {
            print("OmiAudioDevice: failed to create audio unit: \(status)")
            return false
        }

        _audioUnit = unit

        // Enable input (mic) on bus 1
        var enableInput: UInt32 = 1
        status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO,
                                      kAudioUnitScope_Input, 1,
                                      &enableInput, UInt32(MemoryLayout<UInt32>.size))
        guard status == noErr else {
            print("OmiAudioDevice: enable input failed: \(status)")
            return false
        }

        // Enable output (speaker) on bus 0
        var enableOutput: UInt32 = 1
        status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_EnableIO,
                                      kAudioUnitScope_Output, 0,
                                      &enableOutput, UInt32(MemoryLayout<UInt32>.size))
        guard status == noErr else {
            print("OmiAudioDevice: enable output failed: \(status)")
            return false
        }

        // Set PCM format
        var format = AudioStreamBasicDescription(
            mSampleRate: sampleRate,
            mFormatID: kAudioFormatLinearPCM,
            mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
            mBytesPerPacket: UInt32(bytesPerFrame),
            mFramesPerPacket: 1,
            mBytesPerFrame: UInt32(bytesPerFrame),
            mChannelsPerFrame: UInt32(channelCount),
            mBitsPerChannel: UInt32(sampleSize * 8),
            mReserved: 0
        )

        // Format for mic output (bus 1, output scope)
        status = AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat,
                                      kAudioUnitScope_Output, 1,
                                      &format, UInt32(MemoryLayout<AudioStreamBasicDescription>.size))
        guard status == noErr else {
            print("OmiAudioDevice: set input format failed: \(status)")
            return false
        }

        // Format for speaker input (bus 0, input scope)
        status = AudioUnitSetProperty(unit, kAudioUnitProperty_StreamFormat,
                                      kAudioUnitScope_Input, 0,
                                      &format, UInt32(MemoryLayout<AudioStreamBasicDescription>.size))
        guard status == noErr else {
            print("OmiAudioDevice: set output format failed: \(status)")
            return false
        }

        // Setup callbacks
        callbackRefCon = Unmanaged.passRetained(self).toOpaque()

        // Render callback (speaker/playout) — remote audio from Twilio
        var renderCB = AURenderCallbackStruct(
            inputProc: omiAudioPlayoutCallback,
            inputProcRefCon: callbackRefCon
        )
        status = AudioUnitSetProperty(unit, kAudioUnitProperty_SetRenderCallback,
                                      kAudioUnitScope_Input, 0,
                                      &renderCB, UInt32(MemoryLayout<AURenderCallbackStruct>.size))
        guard status == noErr else {
            print("OmiAudioDevice: set render callback failed: \(status)")
            return false
        }

        // Input callback (mic/capture) — local audio
        var inputCB = AURenderCallbackStruct(
            inputProc: omiAudioRecordCallback,
            inputProcRefCon: callbackRefCon
        )
        status = AudioUnitSetProperty(unit, kAudioOutputUnitProperty_SetInputCallback,
                                      kAudioUnitScope_Global, 0,
                                      &inputCB, UInt32(MemoryLayout<AURenderCallbackStruct>.size))
        guard status == noErr else {
            print("OmiAudioDevice: set input callback failed: \(status)")
            return false
        }

        // Initialize and start
        status = AudioUnitInitialize(unit)
        guard status == noErr else {
            print("OmiAudioDevice: initialize failed: \(status)")
            return false
        }

        status = AudioOutputUnitStart(unit)
        guard status == noErr else {
            print("OmiAudioDevice: start failed: \(status)")
            return false
        }

        print("OmiAudioDevice: audio unit setup complete (48kHz mono 16-bit)")
        return true
    }

    private func cleanupCallbacks() {
        if let ref = callbackRefCon {
            Unmanaged<OmiRecordingAudioDevice>.fromOpaque(ref).release()
            callbackRefCon = nil
        }
    }
}

// MARK: - AudioDevice Protocol

extension OmiRecordingAudioDevice: AudioDevice {

    func captureFormat() -> AudioFormat? { capturingFormat }
    func renderFormat() -> AudioFormat? { renderingFormat }

    func isInitialized() -> Bool { $_audioUnit.isNotNil }

    func isStarted() -> Bool {
        guard let unit = _audioUnit else { return false }
        var running: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        let status = AudioUnitGetProperty(unit, kAudioOutputUnitProperty_IsRunning,
                                          kAudioUnitScope_Global, 0, &running, &size)
        return status == noErr && running != 0
    }

    func start() -> Bool {
        guard let unit = _audioUnit else { return false }
        return AudioOutputUnitStart(unit) == noErr
    }

    func stop() -> Bool {
        guard let unit = _audioUnit else { return false }
        return AudioOutputUnitStop(unit) == noErr
    }
}

// MARK: - AudioDeviceRenderer Protocol

extension OmiRecordingAudioDevice: AudioDeviceRenderer {

    func initializeRenderer() -> Bool { true }

    func startRendering(_ context: AudioDeviceContext) -> Bool {
        _renderingContext = RenderingContext(
            deviceContext: context,
            maxFramesPerBuffer: Int(framesPerBuffer)
        )
        return true
    }

    func stopRendering() -> Bool {
        _renderingContext = nil
        return true
    }
}

// MARK: - AudioDeviceCapturer Protocol

extension OmiRecordingAudioDevice: AudioDeviceCapturer {

    func initializeCapturer() -> Bool {
        return setupAudioUnit()
    }

    func startCapturing(_ context: AudioDeviceContext) -> Bool {
        guard let unit = _audioUnit else { return false }
        // Pre-allocate buffer here — never on the audio thread
        _capturingContext = CapturingContext(
            deviceContext: context,
            audioUnit: unit,
            maxFrames: framesPerBuffer,
            bytesPerFrame: bytesPerFrame
        )
        return true
    }

    func stopCapturing() -> Bool {
        _capturingContext = nil
        return true
    }
}

// MARK: - Core Audio Callbacks

/// Playout callback — pulls remote audio from Twilio, plays to speaker, streams to Flutter
private func omiAudioPlayoutCallback(
    inRefCon: UnsafeMutableRawPointer,
    ioActionFlags: UnsafeMutablePointer<AudioUnitRenderActionFlags>,
    inTimeStamp: UnsafePointer<AudioTimeStamp>,
    inBusNumber: UInt32,
    inNumberFrames: UInt32,
    ioData: UnsafeMutablePointer<AudioBufferList>?
) -> OSStatus {
    guard let ioData = ioData else { return noErr }

    let device = Unmanaged<OmiRecordingAudioDevice>.fromOpaque(inRefCon).takeUnretainedValue()

    guard let context = device.getRenderingContext() else {
        // Fill with silence
        let buf = UnsafeMutableAudioBufferListPointer(ioData)
        for i in 0..<buf.count {
            if let data = buf[i].mData {
                memset(data, 0, Int(buf[i].mDataByteSize))
            }
        }
        return noErr
    }

    // Pull audio from Twilio
    let buf = UnsafeMutableAudioBufferListPointer(ioData)
    if let data = buf[0].mData {
        let size = Int(inNumberFrames * UInt32(device.bytesPerFrame))
        AudioDeviceReadRenderData(context: context.deviceContext, data: data, sizeInBytes: size)

        // Stream remote audio to Flutter (channel 2)
        if let callback = device.onAudioData {
            let audioData = Data(bytes: data, count: size)
            callback(audioData, 2)
        }
    }

    return noErr
}

/// Record callback — captures mic audio, sends to Twilio, streams to Flutter
private func omiAudioRecordCallback(
    inRefCon: UnsafeMutableRawPointer,
    ioActionFlags: UnsafeMutablePointer<AudioUnitRenderActionFlags>,
    inTimeStamp: UnsafePointer<AudioTimeStamp>,
    inBusNumber: UInt32,
    inNumberFrames: UInt32,
    ioData: UnsafeMutablePointer<AudioBufferList>?
) -> OSStatus {
    let device = Unmanaged<OmiRecordingAudioDevice>.fromOpaque(inRefCon).takeUnretainedValue()

    guard let context = device.getCapturingContext(),
          let audioUnit = device.getAudioUnit() else { return noErr }

    // Use pre-allocated buffer. If frame count exceeds our buffer, fill with silence.
    let needed = inNumberFrames * UInt32(device.bytesPerFrame)
    if needed > context.bufferSizeBytes {
        print("OmiAudioDevice: frame count \(inNumberFrames) exceeds buffer capacity")
        return noErr
    }

    // Reset buffer size for this render
    context.bufferList.pointee.mBuffers.mDataByteSize = needed

    // Capture from microphone
    let status = AudioUnitRender(audioUnit, ioActionFlags, inTimeStamp, inBusNumber,
                                 inNumberFrames, context.bufferList)
    guard status == noErr else { return status }

    guard let data = context.bufferList.pointee.mBuffers.mData else {
        return kAudioUnitErr_InvalidParameter
    }

    let size = Int(context.bufferList.pointee.mBuffers.mDataByteSize)

    // Stream local audio to Flutter (channel 1) — skip when muted
    if !device.getMicMuted(), let callback = device.onAudioData {
        let audioData = Data(bytes: data, count: size)
        callback(audioData, 1)
    }

    // Send to Twilio
    AudioDeviceWriteCaptureData(context: context.deviceContext, data: data, sizeInBytes: size)

    return status
}
