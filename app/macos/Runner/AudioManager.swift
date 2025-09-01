import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation

// MARK: - Audio Manager
class AudioManager: NSObject, SCStreamDelegate, SCStreamOutput {

    private enum Constants {
        static let audioProcessingQueueLabel = "com.friend.audiomixer"
        static let silenceThreshold: Float = 0.005
        static let flutterOutputSampleRate = 16000.0
        static let flutterOutputChannels: AVAudioChannelCount = 1
        static let micTapBufferSize: AVAudioFrameCount = 1024
        static let audioMixTimerInterval: TimeInterval = 1.0
        static let deviceStatusTimerInterval: TimeInterval = 0.2
        static let deviceChangeDebounce: TimeInterval = 0.5
        static let scStreamFrameRate: CMTimeScale = 600
        static let desiredChunkSizeInFrames = 16000
    }
    
    // MARK: - Audio Properties
    private var audioEngine: AVAudioEngine?
    
    private var micNode: AVAudioInputNode?
    private var micNodeFormat: AVAudioFormat?
    private var outputAudioFormat: AVAudioFormat?
    private var micAudioConverter: AVAudioConverter?
    
    private var scStreamSourceFormat: AVAudioFormat?
    private var systemAudioConverter: AVAudioConverter?
    
    // Audio mixing properties
    private let audioProcessingQueue = DispatchQueue(label: Constants.audioProcessingQueueLabel, qos: .userInitiated)
    private var micAudioQueue = [AVAudioPCMBuffer]()
    private var systemAudioQueue = [AVAudioPCMBuffer]()
    private var audioMixTimer: Timer?
    private var deviceStatusTimer: Timer?
    private var deviceChangeWorkItem: DispatchWorkItem?
    private var deviceListChangedListener: AudioObjectPropertyListenerBlock?
    private var isCurrentlyUsingSpeakers: Bool = false
    private var knownDeviceIDs: [AudioDeviceID] = []
    private var currentInputDeviceID: AudioDeviceID?
    private var currentInputDeviceName: String?
    private var micRMS: Float = 0.0
    private var systemAudioRMS: Float = 0.0
    private var isMicSilent: Bool = true
    private var isSystemAudioSilent: Bool = true
    
    // SCStream properties
    private var availableContent: SCShareableContent?
    private var filter: SCContentFilter?
    private var stream: SCStream?
    private var audioSettings: [String: Any]!
    private var streamOutputReference: AudioManager?
    
    // Activity management to prevent system sleep
    private var preventSleepActivity: NSObjectProtocol?
    
    // Flutter communication
    private weak var screenCaptureChannel: FlutterMethodChannel?
    private var audioFormatSentToFlutter: Bool = false
    private var isFlutterEngineActive: Bool = true

    private var _isRecording: Bool = false

    override init() {
        super.init()
    }
    
    deinit {
        // Ensure all resources are released if the manager is deallocated.
        stopCapture()
        print("DEBUG: AudioManager deinitialized.")
    }
    
    // MARK: - Public Interface
    
    func setFlutterChannel(_ channel: FlutterMethodChannel) {
        self.screenCaptureChannel = channel
        self.isFlutterEngineActive = true
    }
    
    func setFlutterEngineActive(_ active: Bool) {
        self.isFlutterEngineActive = active
        if !active {
            print("DEBUG: Flutter engine marked as inactive, will not send messages")
        }
    }

    func isRecording() -> Bool {
        return _isRecording;
    }
    
    func startCapture() async throws {
        // Start sleep prevention first, and ensure it's stopped on any failure path.
        startSleepPrevention()
        
        do {
            try setupAudioSession()
            try configureAudioFormatsAndConverter()
            installMicTap()
            try await setupScreenCapture()
            startMonitoringTimers()
            try await startAudioEngineAndSCStream()
            _isRecording = true
        } catch {
            print("ERROR: Capture setup failed: \(error.localizedDescription)")
            stopCapture() // Ensure cleanup on failure
            throw error // Re-throw to inform the caller
        }
    }
    
    func stopCapture() {
        guard _isRecording else {
            // If not recording, there's nothing to stop. This prevents redundant cleanup.
            return
        }
        
        _isRecording = false
        self.isCurrentlyUsingSpeakers = false

        // Stop timers and listeners first to prevent new events.
        audioMixTimer?.invalidate()
        audioMixTimer = nil
        deviceStatusTimer?.invalidate()
        deviceStatusTimer = nil
        removeDeviceListChangeObserver()

        // Stop the hardware and streams.
        if let scStream = stream {
            Task {
                try? await scStream.stopCapture()
                await MainActor.run {
                    self.stream = nil
                }
            }
        }
        
        if let engine = audioEngine, engine.isRunning {
            engine.stop()
            micNode?.removeTap(onBus: 0)
        }
        
        // Clean up resources.
        audioProcessingQueue.async {
            self.micAudioQueue.removeAll()
            self.systemAudioQueue.removeAll()
        }
        
        self.micAudioConverter = nil
        self.systemAudioConverter = nil
        self.outputAudioFormat = nil
        self.micNodeFormat = nil
        self.scStreamSourceFormat = nil
        self.micNode = nil
        self.audioEngine = nil
        self.streamOutputReference = nil
        
        // Stop system-level activities.
        stopSleepPrevention()
        
        // Notify Flutter about the stream ending.
        if audioFormatSentToFlutter && isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("audioStreamEnded", arguments: nil)
            print("DEBUG: Recording stopped, Flutter notified.")
        } else {
            print("DEBUG: Recording stopped, but Flutter was not active or not fully initialized for audio.")
        }
        audioFormatSentToFlutter = false
    }
    
    // Check if current display setup is still valid
    func validateDisplaySetup() async -> Bool {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            let hasDisplays = !content.displays.isEmpty
            print("DEBUG: Display validation - Available displays: \(content.displays.count)")
            return hasDisplays
        } catch {
            print("ERROR: Failed to validate display setup: \(error.localizedDescription)")
            return false
        }
    }
    
    // Refresh available content (when displays change)
    func refreshAvailableContent() async throws {
        print("DEBUG: Refreshing available content...")
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        self.availableContent = content
        
        print("DEBUG: Content refreshed - Displays: \(content.displays.count), Applications: \(content.applications.count)")
        
        guard !content.displays.isEmpty else {
            throw AudioManagerError.audioFormatError("No displays available after refresh")
        }
    }
    
    // MARK: - Sleep Prevention Methods
    
    private func startSleepPrevention() {
        guard preventSleepActivity == nil else {
            print("DEBUG: Sleep prevention already active")
            return
        }
        
        preventSleepActivity = ProcessInfo.processInfo.beginActivity(
            options: [.userInitiated, .idleSystemSleepDisabled],
            reason: "Recording system audio and microphone"
        )
    }
    
    private func stopSleepPrevention() {
        if let activity = preventSleepActivity {
            ProcessInfo.processInfo.endActivity(activity)
            preventSleepActivity = nil
            print("DEBUG: Stopped sleep prevention activity")
        }
    }
    
    // MARK: - Capture Setup Helpers
    
    private func setupAudioSession() throws {
        audioEngine = AVAudioEngine()
        setupDeviceListChangeObserver()
        
        self.isCurrentlyUsingSpeakers = self.isUsingSpeakers()
        self.knownDeviceIDs = self.getAudioDeviceIDs()
        self.currentInputDeviceID = self.getDefaultInputDeviceID()
        
        print("DEBUG: Initial speaker status: \(self.isCurrentlyUsingSpeakers)")
        if let deviceID = self.currentInputDeviceID, let deviceName = getDeviceName(for: deviceID) {
            print("DEBUG: Initial input device: \(deviceName) (ID: \(deviceID))")
            self.currentInputDeviceName = deviceName
        }
    }
    
    private func configureAudioFormatsAndConverter() throws {
        updateAudioSettings(sampleRate: Constants.flutterOutputSampleRate, channels: Constants.flutterOutputChannels)
        
        self.outputAudioFormat = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                               sampleRate: Constants.flutterOutputSampleRate,
                                               channels: Constants.flutterOutputChannels,
                                               interleaved: true)
        
        guard let outputFormat = self.outputAudioFormat else {
            throw AudioManagerError.audioFormatError("Could not create final output audio format for Flutter")
        }
        
        self.micNode = audioEngine?.inputNode
        self.micNodeFormat = self.micNode!.outputFormat(forBus: 0)
        
        self.micAudioConverter = AVAudioConverter(from: self.micNodeFormat!, to: outputFormat)
        guard self.micAudioConverter != nil else {
            throw AudioManagerError.converterSetupError("Could not create main audio converter to Flutter format")
        }
        
        self.micAudioConverter?.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
        self.micAudioConverter?.sampleRateConverterQuality = .max
        self.micAudioConverter?.dither = true
        
        print("DEBUG: Mic native format: \(self.micNodeFormat!))")
        print("DEBUG: Flutter output format will be SR: \(Constants.flutterOutputSampleRate), CH: \(Constants.flutterOutputChannels)")
    }
    
    private func installMicTap() {
        micNode!.installTap(onBus: 0, bufferSize: Constants.micTapBufferSize, format: self.micNodeFormat!) { [weak self] (buffer, time) in
            guard let self = self, let finalConverter = self.micAudioConverter, let finalOutputFormat = self.outputAudioFormat else {
                return
            }
            
            let outputBufferFrameCapacity = AVAudioFrameCount(Double(buffer.frameLength) * (finalOutputFormat.sampleRate / buffer.format.sampleRate))
            guard let outputPCMBuffer = AVAudioPCMBuffer(pcmFormat: finalOutputFormat, frameCapacity: outputBufferFrameCapacity) else {
                print("ERROR: Failed to create output PCM buffer for final converter.")
                return
            }
            
            var error: NSError?
            let status = finalConverter.convert(to: outputPCMBuffer, error: &error) { inNumPackets, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }
            
            if status == .error || error != nil {
                print("ERROR: Final audio conversion error from mic tap: \(error?.localizedDescription ?? "Unknown error")")
                return
            }
            
            if status == .haveData && outputPCMBuffer.frameLength > 0 {
                let rms = self.calculateRMS(buffer: outputPCMBuffer)
                self.micRMS = rms
                self.isMicSilent = self.micRMS < Constants.silenceThreshold
                // print("DEBUG: Mic audio buffer captured. RMS: \(String(format: "%.4f", rms)). Silent: \(self.isMicSilent). Adding to queue.")
                self.audioProcessingQueue.async {
                    self.micAudioQueue.append(outputPCMBuffer)
                }
            }
        }
        audioEngine?.prepare()
    }
    
    private func setupScreenCapture() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        self.availableContent = content
        
        guard !content.displays.isEmpty else {
            throw AudioManagerError.audioFormatError("No displays available for screen capture. Found \(content.displays.count) displays.")
        }
        
        prepSCStreamFilter()
    }
    
    private func startMonitoringTimers() {
        DispatchQueue.main.async {
            self.audioMixTimer = Timer.scheduledTimer(withTimeInterval: Constants.audioMixTimerInterval, repeats: true) { [weak self] _ in
                self?.processAudioQueues()
            }
            self.deviceStatusTimer = Timer.scheduledTimer(withTimeInterval: Constants.deviceStatusTimerInterval, repeats: true) { [weak self] _ in
                self?.sendMicrophoneStatus()
            }
        }
    }
    
    private func startAudioEngineAndSCStream() async throws {
        guard let strongOutputAudioFormat = self.outputAudioFormat else {
            throw AudioManagerError.audioFormatError("Output audio format not configured.")
        }
        
        // Send format details to Flutter before starting capture.
        let isBigEndian = (strongOutputAudioFormat.streamDescription.pointee.mFormatFlags & kAudioFormatFlagIsBigEndian) != 0
        let formatDetails: [String: Any] = [
            "sampleRate": strongOutputAudioFormat.sampleRate,
            "channels": strongOutputAudioFormat.channelCount,
            "bitsPerChannel": strongOutputAudioFormat.streamDescription.pointee.mBitsPerChannel,
            "isFloat": (strongOutputAudioFormat.commonFormat == .pcmFormatFloat32 || strongOutputAudioFormat.commonFormat == .pcmFormatFloat64),
            "isBigEndian": isBigEndian,
            "isInterleaved": strongOutputAudioFormat.isInterleaved
        ]
        if isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("audioFormat", arguments: formatDetails)
            self.audioFormatSentToFlutter = true
        } else {
            print("DEBUG: Skipping audioFormat message - Flutter engine inactive")
        }
        
        // Start the engine and stream.
        do {
            try audioEngine?.start()
            try await recordSCStream(filter: self.filter!)
        } catch {
            print("ERROR: Failed to start capturing: \(error.localizedDescription)")
            throw error
        }
    }
    
    // MARK: - Private Helper Methods
    
    @objc private func handleAudioEngineConfigurationChange() {
        print("DEBUG: Audio engine configuration changed. Checking for active device change.")

        guard let newDeviceID = getDefaultInputDeviceID() else {
            print("ERROR: Could not get new default input device ID during configuration change.")
            return
        }

        if newDeviceID != self.currentInputDeviceID {
            self.currentInputDeviceID = newDeviceID
            if let deviceName = getDeviceName(for: newDeviceID) {
                print("DEBUG: Active input device changed to: \(deviceName) (ID: \(newDeviceID))")
                self.currentInputDeviceName = deviceName
            } else {
                self.currentInputDeviceName = nil
            }

            // Notify Flutter that the device has changed.
            if isFlutterEngineActive {
                self.screenCaptureChannel?.invokeMethod("microphoneDeviceChanged", arguments: nil)
                print("DEBUG: Notified Flutter of microphone device change.")
            }
        } else {
            print("DEBUG: Default input device remains the same. No notification sent.")
        }
    }

    private func getDefaultInputDeviceID() -> AudioDeviceID? {
        var deviceID: AudioDeviceID = 0
        var propertySize = UInt32(MemoryLayout<AudioDeviceID>.size)
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &propertySize,
            &deviceID
        )

        if status == noErr {
            return deviceID
        } else {
            print("ERROR: Could not get default input device ID: \(status)")
            return nil
        }
    }

    private func getDeviceName(for deviceID: AudioDeviceID) -> String? {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioObjectPropertyName,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        
        var deviceName: CFString = "" as CFString
        var propertySize = UInt32(MemoryLayout<CFString>.size)
        
        let status = AudioObjectGetPropertyData(
            deviceID,
            &address,
            0,
            nil,
            &propertySize,
            &deviceName
        )
        
        if status == noErr {
            return deviceName as String
        } else {
            print("ERROR: Could not get name for device \(deviceID): \(status)")
            return nil
        }
    }
    
    private func sendMicrophoneStatus() {
        guard let deviceName = self.currentInputDeviceName else { return }
        
        let status: [String: Any] = [
            "deviceName": deviceName,
            "micLevel": self.micRMS,
            "systemAudioLevel": self.systemAudioRMS
        ]
        
        if isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("microphoneStatus", arguments: status)
        }
    }
    
    private func prepSCStreamFilter() {
        guard let content = availableContent else {
            print("ERROR: No available content when preparing SCStream filter")
            return
        }
        
        guard !content.displays.isEmpty else {
            print("ERROR: No displays available when preparing SCStream filter")
            return
        }
        
        let primaryDisplay = content.displays.first!
        print("DEBUG: Preparing filter for display: \(primaryDisplay.displayID)")
        
        // Exclude our own app from being captured
        let excluded = content.applications.filter { app in
            Bundle.main.bundleIdentifier == app.bundleIdentifier
        }
        print("DEBUG: Excluding \(excluded.count) applications from capture")
        
        // Create filter with primary display
        filter = SCContentFilter(display: primaryDisplay, excludingApplications: excluded, exceptingWindows: [])
        print("DEBUG: SCStream filter created successfully")
        
        // Reset SCStream source format for a new session
        scStreamSourceFormat = nil
    }
    
    private func startAudioEngineAndCapture() throws {
        do {
            try audioEngine?.start()
        } catch {
            print("ERROR: Failed to start AVAudioEngine: \(error.localizedDescription)")
            throw AudioManagerError.engineStartError("Failed to start audio engine: \(error.localizedDescription)")
        }
        
    }
    
    private func recordSCStream(filter: SCContentFilter) async throws {
        let conf = SCStreamConfiguration()
        conf.width = 2
        conf.height = 2
        conf.minimumFrameInterval = CMTime(value: 1, timescale: Constants.scStreamFrameRate)
        conf.showsCursor = false
        conf.capturesAudio = true
        
        stream = SCStream(filter: filter, configuration: conf, delegate: self)
        
        guard let stream = stream else {
            throw AudioManagerError.engineStartError("Failed to create SCStream instance")
        }
        
        streamOutputReference = self
        
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: .global(qos: .userInitiated))
        try await stream.startCapture()
    }
    
    private func concatenateBuffers(buffers: [AVAudioPCMBuffer]) -> AVAudioPCMBuffer? {
        guard !buffers.isEmpty else { return nil }
        
        let outputFormat = buffers.first!.format
        let totalFrames = buffers.reduce(0) { AVAudioFrameCount($0) + $1.frameLength }
        
        guard let concatenatedBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: totalFrames) else {
            print("ERROR: Failed to create concatenated buffer.")
            return nil
        }
        
        var offset: AVAudioFrameCount = 0
        for buffer in buffers {
            guard let sourcePtr = buffer.int16ChannelData?[0],
                  let destPtr = concatenatedBuffer.int16ChannelData?[0] else {
                print("ERROR: Could not get int16 channel data for concatenation.")
                return nil
            }
            
            let bytesToCopy = Int(buffer.frameLength) * Int(outputFormat.streamDescription.pointee.mBytesPerFrame)
            let destOffsetInSamples = Int(offset) * Int(outputFormat.channelCount)
            
            memcpy(destPtr.advanced(by: destOffsetInSamples), sourcePtr, bytesToCopy)
            
            offset += buffer.frameLength
        }
        
        concatenatedBuffer.frameLength = totalFrames
        return concatenatedBuffer
    }
    
    private func calculateRMS(buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.int16ChannelData?[0] else { return 0 }
        let frameLength = Int(buffer.frameLength)
        if frameLength == 0 { return 0 }

        var sumOfSquares: Float = 0.0
        for i in 0..<frameLength {
            // Normalize Int16 to [-1.0, 1.0]
            let sample = Float(channelData[i]) / Float(Int16.max)
            sumOfSquares += sample * sample
        }

        return sqrt(sumOfSquares / Float(frameLength))
    }
    
    private func getAudioDeviceIDs() -> [AudioDeviceID] {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        var propertySize: UInt32 = 0
        var status = AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &propertyAddress, 0, nil, &propertySize)
        if status != noErr {
            print("ERROR: Could not get size of device list: \(status)")
            return []
        }

        let deviceCount = Int(propertySize) / MemoryLayout<AudioDeviceID>.size
        var deviceIDs = [AudioDeviceID](repeating: 0, count: deviceCount)

        status = AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &propertyAddress, 0, nil, &propertySize, &deviceIDs)
        if status != noErr {
            print("ERROR: Could not get device list: \(status)")
            return []
        }

        return deviceIDs
    }
    
    private func isUsingSpeakers() -> Bool {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultOutputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        
        var deviceID: AudioDeviceID = 0
        var propertySize = UInt32(MemoryLayout<AudioDeviceID>.size)
        
        let status = AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject),
            &propertyAddress,
            0,
            nil,
            &propertySize,
            &deviceID
        )
        
        if status != noErr {
            print("ERROR: Could not get default output device: \(status)")
            return false
        }
        
        propertyAddress.mSelector = kAudioDevicePropertyTransportType
        var transportType: UInt32 = 0
        propertySize = UInt32(MemoryLayout<UInt32>.size)
        
        let transportStatus = AudioObjectGetPropertyData(
            deviceID,
            &propertyAddress,
            0,
            nil,
            &propertySize,
            &transportType
        )
        
        if transportStatus != noErr {
            print("ERROR: Could not get transport type for device \(deviceID): \(transportStatus)")
            return false
        }
        
        // Built-in speakers, DisplayPort, and HDMI are common speaker types.
        // Other types like USB, Bluetooth, etc., are typically headphones or external interfaces.
        switch transportType {
        case kAudioDeviceTransportTypeBuiltIn,
             kAudioDeviceTransportTypeDisplayPort,
             kAudioDeviceTransportTypeHDMI:
            return true
        default:
            return false
        }
    }
    
    private func processAudioQueues() {
        audioProcessingQueue.async { [weak self] in
            guard let self = self else { return }

            // Grab all available buffers from both queues.
            let micBuffers = self.micAudioQueue
            self.micAudioQueue.removeAll()
            
            let systemBuffers = self.systemAudioQueue
            self.systemAudioQueue.removeAll()
            
            if micBuffers.isEmpty && systemBuffers.isEmpty {
                return // Nothing to process.
            }
            
            print("DEBUG: Processing audio. Mic buffers: \(micBuffers.count), System buffers: \(systemBuffers.count)")
            
            // Concatenate all buffers from each source.
            let micBuffer = self.concatenateBuffers(buffers: micBuffers)
            var systemBuffer = self.concatenateBuffers(buffers: systemBuffers)
            
            // If speakers are the output AND the mic is not silent, nullify the system audio buffer to prevent echo.
            if self.isCurrentlyUsingSpeakers && !self.isMicSilent {
                print("DEBUG: Speakers active and mic is not silent. Ignoring system audio to prevent echo.")
                systemBuffer = nil
            }
            
            // Mix the buffers. The mixer handles a nil systemBuffer gracefully.
            if let mixedBuffer = self.mixAudioBuffers(micBuffer: micBuffer, systemBuffer: systemBuffer) {
                self.sendAudioBufferToFlutter(mixedBuffer)
            }
        }
    }
    
    private func mixAudioBuffers(micBuffer: AVAudioPCMBuffer?, systemBuffer: AVAudioPCMBuffer?) -> AVAudioPCMBuffer? {
        let micFrames = micBuffer?.frameLength ?? 0
        let systemFrames = systemBuffer?.frameLength ?? 0
        let totalFrames = max(micFrames, systemFrames)
        
        if totalFrames == 0 { return nil }
        
        print("DEBUG: Mixing audio into mono. Total frames: \(totalFrames). Mic frames: \(micFrames), System frames: \(systemFrames).")

        // outputFormat is now mono (1 channel)
        guard let outputFormat = self.outputAudioFormat,
              let mixedBuffer = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: totalFrames) else {
            print("ERROR: Failed to create mixed mono buffer.")
            return nil
        }
        
        mixedBuffer.frameLength = totalFrames
        
        let micInt16 = micBuffer?.int16ChannelData?[0]
        let systemInt16 = systemBuffer?.int16ChannelData?[0]
        
        guard let mixedInt16 = mixedBuffer.int16ChannelData?[0] else {
            print("ERROR: Failed to get int16 channel data for mixed buffer.")
            return nil
        }
        
        // Mix samples by averaging them. If one source is shorter or nil, its contribution is 0.
        for i in 0..<Int(totalFrames) {
            let micSample = (i < micFrames) ? Float(micInt16?[i] ?? 0) : 0.0
            let systemSample = (i < systemFrames) ? Float(systemInt16?[i] ?? 0) : 0.0
            
            // Mix by averaging. Clamp to prevent overflow.
            let mixedSample = (micSample + systemSample) / 2.0
            let clampedSample = max(Float(Int16.min), min(Float(Int16.max), mixedSample))
            
            mixedInt16[i] = Int16(clampedSample)
        }
        
        return mixedBuffer
    }
    
    private func sendAudioBufferToFlutter(_ buffer: AVAudioPCMBuffer) {
        guard let finalOutputFormat = self.outputAudioFormat,
              finalOutputFormat.commonFormat == .pcmFormatInt16,
              finalOutputFormat.isInterleaved else {
            print("ERROR: Output format is not Int16 interleaved, cannot send to Flutter.")
            return
        }
        
        let bytesPerFrame = Int(finalOutputFormat.streamDescription.pointee.mBytesPerFrame)
        let totalFrames = Int(buffer.frameLength)
        
        guard let int16DataPtr = buffer.int16ChannelData?[0] else { return }
        
        // The desired chunk size matches what the backend expects for streaming transcription.
        let desiredChunkSizeInFrames = Constants.desiredChunkSizeInFrames
        
        var framesProcessed = 0
        while framesProcessed < totalFrames {
            let framesRemaining = totalFrames - framesProcessed
            let framesInThisChunk = min(desiredChunkSizeInFrames, framesRemaining)
            let bytesInThisChunk = framesInThisChunk * bytesPerFrame
            
            if bytesInThisChunk > 0 {
                let dataChunk = Data(bytes: int16DataPtr.advanced(by: framesProcessed), count: bytesInThisChunk)
                print("DEBUG: Sending \(dataChunk.count) bytes of mixed audio to Flutter.")
                if self.audioFormatSentToFlutter && self.isFlutterEngineActive {
                    self.screenCaptureChannel?.invokeMethod("audioFrame", arguments: dataChunk)
                }
            }
            
            framesProcessed += framesInThisChunk
        }
    }
    
    private func updateAudioSettings(sampleRate: Double, channels: AVAudioChannelCount) {
        audioSettings = [AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: channels]
    }
    
    // MARK: - SCStream Delegate Methods
    
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sampleBuffer.isValid else { return }
        
        guard type == .audio else { return }
        
        guard let pcmBufferFromSCStream = sampleBuffer.asPCMBuffer else {
            print("ERROR: SCStream: Failed to get PCM buffer from CMSampleBuffer")
            return
        }
        
        // Immediately create a deep copy to ensure memory stability, especially for deinterleaved formats.
        guard let stablePcmBuffer = pcmBufferFromSCStream.deepCopy() else {
            print("ERROR: Failed to create a stable deep copy of the system audio buffer.")
            return
        }
        
        // Lazily create the converter on the first buffer received.
        if scStreamSourceFormat == nil {
            scStreamSourceFormat = stablePcmBuffer.format
            print("DEBUG: SCStream actual source format: \(scStreamSourceFormat!)")
            
            // Always create the converter. It will handle identity conversion if formats match.
            systemAudioConverter = AVAudioConverter(from: scStreamSourceFormat!, to: self.outputAudioFormat!)
            systemAudioConverter?.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
            systemAudioConverter?.sampleRateConverterQuality = .max
            systemAudioConverter?.dither = true
        }
        
        // Always use the converter path, which now handles all cases (conversion or identity copy).
        guard let converter = self.systemAudioConverter, let finalOutputFormat = self.outputAudioFormat else {
            print("ERROR: System audio converter or output format not available.")
            return
        }
        
        let outputBufferFrameCapacity = AVAudioFrameCount(Double(stablePcmBuffer.frameLength) * (finalOutputFormat.sampleRate / stablePcmBuffer.format.sampleRate))
        guard let outputPCMBuffer = AVAudioPCMBuffer(pcmFormat: finalOutputFormat, frameCapacity: outputBufferFrameCapacity) else {
            print("ERROR: Failed to create output PCM buffer for system audio converter.")
            return
        }
        
        var error: NSError?
        let status = converter.convert(to: outputPCMBuffer, error: &error) { inNumPackets, outStatus in
            outStatus.pointee = .haveData
            return stablePcmBuffer // Use the stable, deep-copied buffer here.
        }
        
        if status == .error || error != nil {
            print("ERROR: SCStream audio conversion failed: \(error?.localizedDescription ?? "Unknown error")")
            return
        }
        
        if status == .haveData && outputPCMBuffer.frameLength > 0 {
            let rms = self.calculateRMS(buffer: outputPCMBuffer)
            self.systemAudioRMS = rms
            self.isSystemAudioSilent = rms < Constants.silenceThreshold
            // print("DEBUG: System audio buffer captured (converted). RMS: \(String(format: "%.4f", rms)). Silent: \(self.isSystemAudioSilent). Adding to queue. Frame length: \(outputPCMBuffer.frameLength)")
            self.audioProcessingQueue.async {
                self.systemAudioQueue.append(outputPCMBuffer)
            }
        }
    }
    
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped with error: \(error.localizedDescription)")
        
        // Clean up sleep prevention since recording stopped
        stopSleepPrevention()
        
        if isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("captureError", arguments: "SCStream stopped: \(error.localizedDescription)")
        }
        self.stream = nil
        self.streamOutputReference = nil
    }

    private func setupDeviceListChangeObserver() {
        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        deviceListChangedListener = { (inNumberAddresses, inAddresses) in
            // Invalidate any existing work item to reset the debounce period
            self.deviceChangeWorkItem?.cancel()

            // Create a new work item to handle the change after a short delay
            let workItem = DispatchWorkItem { [weak self] in
                guard let self = self else { return }

                let newDeviceIDs = self.getAudioDeviceIDs()
                if self.knownDeviceIDs.isEmpty {
                    self.knownDeviceIDs = newDeviceIDs
                    print("DEBUG: Initial device list populated, not treating as a change.")
                    return
                }
                
                if Set(newDeviceIDs) != Set(self.knownDeviceIDs) {
                    print("DEBUG: Audio device list changed.")
                    self.knownDeviceIDs = newDeviceIDs
                    
                    // Handle device change logic
                    self.handleAudioEngineConfigurationChange()
                    
                    // Update speaker status and notify Flutter
                    self.isCurrentlyUsingSpeakers = self.isUsingSpeakers()
                    print("DEBUG: Speaker status updated on device change: \(self.isCurrentlyUsingSpeakers)")
                    self.screenCaptureChannel?.invokeMethod("speakerStatusChanged", arguments: ["isUsingSpeakers": self.isCurrentlyUsingSpeakers])
                }
            }
            
            self.deviceChangeWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + Constants.deviceChangeDebounce, execute: workItem)
        }

        let systemObjectID = AudioObjectID(kAudioObjectSystemObject)
        let status = AudioObjectAddPropertyListenerBlock(systemObjectID, &propertyAddress, nil, deviceListChangedListener!)
        if status != noErr {
            print("ERROR: Failed to add listener for audio device list changes: \(status)")
        }
    }

    private func removeDeviceListChangeObserver() {
        deviceChangeWorkItem?.cancel()
        deviceChangeWorkItem = nil
        guard let listener = deviceListChangedListener else { return }

        var propertyAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )

        let systemObjectID = AudioObjectID(kAudioObjectSystemObject)
        let status = AudioObjectRemovePropertyListenerBlock(systemObjectID, &propertyAddress, nil, listener)
        if status != noErr {
            print("ERROR: Failed to remove listener for audio device list changes: \(status)")
        }
        deviceListChangedListener = nil
    }
    
}

// MARK: - Audio Manager Errors
enum AudioManagerError: Error {
    case audioFormatError(String)
    case converterSetupError(String)
    case engineStartError(String)
    
    var localizedDescription: String {
        switch self {
        case .audioFormatError(let message):
            return "Audio Format Error: \(message)"
        case .converterSetupError(let message):
            return "Converter Setup Error: \(message)"
        case .engineStartError(let message):
            return "Engine Start Error: \(message)"
        }
    }
}

// MARK: - CMSampleBuffer Extension
extension CMSampleBuffer {
    var asPCMBuffer: AVAudioPCMBuffer? {
        try? self.withAudioBufferList { audioBufferList, blockBuffer -> AVAudioPCMBuffer? in
            guard var absd = self.formatDescription?.audioStreamBasicDescription else { return nil }
            guard let format = AVAudioFormat(streamDescription: &absd) else { return nil}
            return AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: audioBufferList.unsafePointer)
        }
    }
}

// MARK: - AVAudioPCMBuffer Extension
extension AVAudioPCMBuffer {
    func deepCopy() -> AVAudioPCMBuffer? {
        guard let pcmCopy = AVAudioPCMBuffer(pcmFormat: self.format, frameCapacity: self.frameCapacity) else { return nil }
        
        pcmCopy.frameLength = self.frameLength
        
        let channelCount = Int(self.format.channelCount)
        let frameLength = Int(self.frameLength)
        
        if format.commonFormat == .pcmFormatInt16 {
            for i in 0..<channelCount {
                if let source = self.int16ChannelData?[i], let destination = pcmCopy.int16ChannelData?[i] {
                    destination.initialize(from: source, count: frameLength)
                }
            }
        } else if format.commonFormat == .pcmFormatFloat32 {
            for i in 0..<channelCount {
                if let source = self.floatChannelData?[i], let destination = pcmCopy.floatChannelData?[i] {
                    destination.initialize(from: source, count: frameLength)
                }
            }
        } else {
            print("ERROR: Deep copy not supported for this PCM format.")
            return nil
        }
        
        return pcmCopy
    }
}
