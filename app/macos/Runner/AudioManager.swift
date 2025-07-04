import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation

// MARK: - Audio Manager
class AudioManager: NSObject, SCStreamDelegate, SCStreamOutput {
    
    // MARK: - Audio Properties
    private let audioEngine = AVAudioEngine()
    private let scStreamPlayerNode = AVAudioPlayerNode()
    private let mixerNode = AVAudioMixerNode()
    
    private var engineProcessingFormat: AVAudioFormat!
    private var micNode: AVAudioInputNode!
    private var micNodeFormat: AVAudioFormat!
    private var outputAudioFormat: AVAudioFormat?
    private var audioConverter: AVAudioConverter?
    
    private var scStreamSourceFormat: AVAudioFormat?
    private var scStreamConverter: AVAudioConverter?
    
    // SCStream properties
    private var availableContent: SCShareableContent?
    private var filter: SCContentFilter?
    private var stream: SCStream?
    private var audioSettings: [String: Any]!
    
    // Activity management to prevent system sleep
    private var preventSleepActivity: NSObjectProtocol?
    
    // Flutter communication
    private weak var screenCaptureChannel: FlutterMethodChannel?
    private var audioFormatSentToFlutter: Bool = false
    private var isFlutterEngineActive: Bool = true
    
    // MARK: - Initialization
    override init() {
        super.init()
        setupAudioComponents()
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
    
    func startCapture() async throws {
        // Start sleep prevention first
        startSleepPrevention()
        
        // Get shareable content
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        self.availableContent = content
        
        guard !content.displays.isEmpty else {
            stopSleepPrevention() // Clean up if we fail
            throw AudioManagerError.audioFormatError("No displays available for screen capture. Found \(content.displays.count) displays.")
        }
        
        let primaryDisplay = content.displays.first!
        print("DEBUG: Using primary display: \(primaryDisplay.displayID), Frame: \(primaryDisplay.frame)")
        
        // Setup audio formats for Flutter output
        let flutterOutputSampleRate = 16000.0
        let flutterOutputChannels: AVAudioChannelCount = 1
        updateAudioSettings(sampleRate: flutterOutputSampleRate, channels: flutterOutputChannels)
        
        print("DEBUG: Flutter output format will be SR: \(flutterOutputSampleRate), CH: \(flutterOutputChannels)")
        self.outputAudioFormat = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                               sampleRate: flutterOutputSampleRate,
                                               channels: flutterOutputChannels,
                                               interleaved: true)
        
        guard let strongOutputAudioFormat = self.outputAudioFormat else {
            stopSleepPrevention() // Clean up if we fail
            throw AudioManagerError.audioFormatError("Could not create final output audio format for Flutter")
        }
        
        // Setup final converter: engineProcessingFormat -> outputAudioFormat (for Flutter)
        self.audioConverter = AVAudioConverter(from: self.engineProcessingFormat, to: strongOutputAudioFormat)
        guard self.audioConverter != nil else {
            stopSleepPrevention() // Clean up if we fail
            throw AudioManagerError.converterSetupError("Could not create main audio converter to Flutter format")
        }
        
        self.audioConverter?.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
        self.audioConverter?.sampleRateConverterQuality = .max
        self.audioConverter?.dither = true
        print("DEBUG: Final audioConverter configured with mastering algorithm and dithering")
        
        // Send format details to Flutter
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
        
        // Setup SCStream filter
        prepSCStreamFilter()
        
        // Start audio engine and capture
        try startAudioEngineAndCapture()
        await recordSCStream(filter: self.filter!)
    }
    
    func stopCapture() {
        // Stop SCStream first
        if stream != nil {
            Task {
                try? await stream?.stopCapture()
                self.stream = nil
            }
        }
        
        // Stop AVAudioEngine
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        scStreamPlayerNode.stop()
        
        // Stop sleep prevention
        stopSleepPrevention()
        
        // Reset converters and formats
        self.audioConverter = nil
        self.scStreamSourceFormat = nil
        self.scStreamConverter = nil
        
        // Notify Flutter
        if audioFormatSentToFlutter && isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("audioStreamEnded", arguments: nil)
            print("Recording stopped (engine & SCStream), Flutter notified.")
        } else {
            print("Recording stopped (engine & SCStream), but Flutter was not active or not fully initialized for audio.")
        }
        audioFormatSentToFlutter = false
    }
    
    func isRecording() -> Bool {
        let engineRunning = audioEngine.isRunning
        let streamActive = stream != nil
        let formatSent = audioFormatSentToFlutter
        
        return engineRunning && formatSent
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
    
    // MARK: - Private Setup Methods
    
    private func setupAudioComponents() {
        self.micNode = audioEngine.inputNode
        self.micNodeFormat = self.micNode.outputFormat(forBus: 0)
        
        // Attempt to enable voice processing for AEC
        if #available(macOS 10.15, *) {
            do {
                try self.micNode.setVoiceProcessingEnabled(true)
                // Configure ducking to minimum level to keep system audio audible
                if #available(macOS 14.0, *) {
                    var duckingConfig = AVAudioVoiceProcessingOtherAudioDuckingConfiguration()
                    duckingConfig.enableAdvancedDucking = false
                    duckingConfig.duckingLevel = .min
                    self.micNode.voiceProcessingOtherAudioDuckingConfiguration = duckingConfig
                }
            } catch {
                print("ERROR: Could not enable voice processing on microphone input node: \(error.localizedDescription). Echo might persist.")
            }
        }
        
        engineProcessingFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                               sampleRate: self.micNodeFormat.sampleRate,
                                               channels: 1,
                                               interleaved: false)
        
        print("DEBUG: Engine processing format (mic native SR: \(self.micNodeFormat.sampleRate)) SR: \(engineProcessingFormat.sampleRate), CH: \(engineProcessingFormat.channelCount)")
        
        setupAudioEngine()
    }
    
    private func setupAudioEngine() {
        audioEngine.attach(scStreamPlayerNode)
        audioEngine.attach(mixerNode)
        
        print("DEBUG: Mic native format: \(self.micNodeFormat!))")
        print("DEBUG: Engine processing format: \(self.engineProcessingFormat!))")
        
        // Connect mic directly to mixer with its native format
        audioEngine.connect(self.micNode, to: mixerNode, format: self.micNodeFormat)
        
        // Connect SCStream player to mixer with engine processing format
        audioEngine.connect(scStreamPlayerNode, to: mixerNode, format: self.engineProcessingFormat)
        
        // Set normal volume - no compensation needed with simplified pipeline
        scStreamPlayerNode.volume = 1.0
        mixerNode.outputVolume = 1.0
        
        // Mixer tap is at engineProcessingFormat
        mixerNode.installTap(onBus: 0, bufferSize: 1024, format: self.engineProcessingFormat) { [weak self] (buffer, time) in
            guard let self = self, let finalConverter = self.audioConverter, let finalOutputFormat = self.outputAudioFormat else {
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
                print("ERROR: Final audio conversion error from mixer tap: \(error?.localizedDescription ?? "Unknown error")")
                return
            }
            
            if status == .haveData && outputPCMBuffer.frameLength > 0 {
                if finalOutputFormat.commonFormat == .pcmFormatInt16 && finalOutputFormat.isInterleaved {
                    let dataSize = Int(outputPCMBuffer.frameLength) * Int(finalOutputFormat.streamDescription.pointee.mBytesPerFrame)
                    if dataSize > 0, let int16Data = outputPCMBuffer.int16ChannelData?[0] {
                        let audioData = Data(bytes: int16Data, count: dataSize)
                        if self.audioFormatSentToFlutter && self.isFlutterEngineActive {
                            self.screenCaptureChannel?.invokeMethod("audioFrame", arguments: audioData)
                        } else {
                            print("WARNING: Audio data NOT sent to Flutter - Format sent: \(self.audioFormatSentToFlutter), Engine active: \(self.isFlutterEngineActive)")
                        }
                    } else if dataSize == 0 && outputPCMBuffer.frameLength > 0 {
                        print("WARNING: Final converter output dataSize is 0 but frameLength > 0. Format: \(finalOutputFormat)")
                    }
                }
            }
        }
        
        
        audioEngine.prepare()
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
        // Ensure engine is prepared before starting
        if !audioEngine.isRunning {
            do {
                try audioEngine.start()
            } catch {
                print("ERROR: Failed to start AVAudioEngine: \(error.localizedDescription)")
                throw AudioManagerError.engineStartError("Failed to start audio engine: \(error.localizedDescription)")
            }
        }
        
        // Wait for engine to be fully running before starting player node
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self = self else { return }
            self.safelyStartPlayerNode()
        }
    }
    
    private func recordSCStream(filter: SCContentFilter) async {
        let conf = SCStreamConfiguration()
        conf.width = 2
        conf.height = 2
        conf.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(600))
        conf.showsCursor = false
        conf.capturesAudio = true
        
        stream = SCStream(filter: filter, configuration: conf, delegate: self)
        
        guard let stream = stream else {
            print("ERROR: Failed to create SCStream instance")
            if isFlutterEngineActive {
                self.screenCaptureChannel?.invokeMethod("captureError", arguments: "Failed to create SCStream instance")
            }
            return
        }
        
        do {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
            
            try await stream.startCapture()
        } catch {
            print("ERROR: SCStream capture failed: \(error.localizedDescription)")
            print("ERROR: Error details: \(error)")
            
            if error.localizedDescription.contains("displays") || error.localizedDescription.contains("windows") {
                
                // Try to refresh available content and retry once
                do {
                    let refreshedContent = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
                    
                    if !refreshedContent.displays.isEmpty {
                        self.availableContent = refreshedContent
                    }
                } catch {
                    print("ERROR: Failed to refresh content: \(error.localizedDescription)")
                }
            }
            
            if isFlutterEngineActive {
                self.screenCaptureChannel?.invokeMethod("captureError", arguments: "SCStream: \(error.localizedDescription)")
            }
            DispatchQueue.main.async { self.stopCapture() }
        }
    }
    
    private func updateAudioSettings(sampleRate: Double, channels: AVAudioChannelCount) {
        audioSettings = [AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: channels]
    }
    
    private func safelyStartPlayerNode() {
        guard audioEngine.isRunning else {
            print("ERROR: Cannot start player node - audio engine not running")
            return
        }
        
        guard scStreamPlayerNode.engine != nil else {
            print("ERROR: Player node not attached to engine")
            return
        }
        
        guard !scStreamPlayerNode.isPlaying else {
            print("DEBUG: Player node already playing")
            return
        }
        
        do {
            // Check if the node is ready to play
            guard scStreamPlayerNode.engine?.isRunning == true else {
                print("ERROR: Audio engine not ready for player node")
                return
            }
            
            scStreamPlayerNode.play()
        } catch {
            print("ERROR: Failed to start player node safely: \(error.localizedDescription)")
            if isFlutterEngineActive {
                self.screenCaptureChannel?.invokeMethod("captureError", arguments: "Player node start failed: \(error.localizedDescription)")
            }
        }
    }
    
    // MARK: - SCStream Delegate Methods
    
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sampleBuffer.isValid, type == .audio else { 
            print("SCStream: Invalid sample buffer or non-audio type: \(type)")
            return 
        }
        
        guard let pcmBufferFromSCStream = sampleBuffer.asPCMBuffer else {
            print("ERROR: SCStream: Failed to get PCM buffer from CMSampleBuffer")
            return
        }
        
        if scStreamSourceFormat == nil {
            scStreamSourceFormat = pcmBufferFromSCStream.format
            print("DEBUG: SCStream actual source format: \(scStreamSourceFormat!)")
            
            // Set up converter from SCStream format to mixer format if needed
            if scStreamSourceFormat != self.engineProcessingFormat {
                scStreamConverter = AVAudioConverter(from: scStreamSourceFormat!, to: self.engineProcessingFormat)
                scStreamConverter?.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
                scStreamConverter?.sampleRateConverterQuality = .max
            }
        }
        
        var processedBuffer: AVAudioPCMBuffer = pcmBufferFromSCStream
        
        // Convert format if needed using AVAudioConverter
        if let converter = scStreamConverter {
            let outputFrameCapacity = AVAudioFrameCount(Double(pcmBufferFromSCStream.frameLength) * (self.engineProcessingFormat.sampleRate / scStreamSourceFormat!.sampleRate))
            
            guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: self.engineProcessingFormat, frameCapacity: outputFrameCapacity) else {
                print("ERROR: Failed to create converted buffer for SCStream audio")
                return
            }
            
            var error: NSError?
            let status = converter.convert(to: convertedBuffer, error: &error) { inNumPackets, outStatus in
                outStatus.pointee = .haveData
                return pcmBufferFromSCStream
            }
            
            if status == .error || error != nil {
                print("ERROR: SCStream audio conversion failed: \(error?.localizedDescription ?? "Unknown error")")
                return
            }
            
            if status == .haveData && convertedBuffer.frameLength > 0 {
                processedBuffer = convertedBuffer
            } else {
                print("WARNING: SCStream converter produced no data")
                return
            }
        }
        
        safelyScheduleBuffer(processedBuffer)
    }
    
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped with error: \(error.localizedDescription)")
        
        // Clean up sleep prevention since recording stopped
        stopSleepPrevention()
        
        if audioEngine.isRunning && isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("captureError", arguments: "SCStream stopped: \(error.localizedDescription)")
        }
        self.stream = nil
    }
    
    private func safelyScheduleBuffer(_ buffer: AVAudioPCMBuffer) {
        guard scStreamPlayerNode.engine != nil && audioEngine.isRunning else {
            print("ERROR: Cannot schedule buffer - audio engine not ready")
            return
        }
        
        if scStreamPlayerNode.isPlaying {
            scStreamPlayerNode.scheduleBuffer(buffer, completionHandler: nil)
        } else {
            print("Warning: SCStream player node was not playing. Attempting to start and schedule.")
            safelyStartPlayerNode()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                if self.scStreamPlayerNode.isPlaying {
                    self.scStreamPlayerNode.scheduleBuffer(buffer, completionHandler: nil)
                } else {
                    print("ERROR: Failed to start player node for buffer scheduling")
                }
            }
        }
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