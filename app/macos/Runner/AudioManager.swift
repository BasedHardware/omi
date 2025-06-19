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
        // Get shareable content
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
        self.availableContent = content
        
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
            throw AudioManagerError.audioFormatError("Could not create final output audio format for Flutter")
        }
        
        // Setup final converter: engineProcessingFormat -> outputAudioFormat (for Flutter)
        self.audioConverter = AVAudioConverter(from: self.engineProcessingFormat, to: strongOutputAudioFormat)
        guard self.audioConverter != nil else {
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
                    print("DEBUG: Configured voice processing ducking to minimum level to preserve system audio volume.")
                } else {
                    print("INFO: Voice processing ducking configuration requires macOS 14.0+. System audio may be ducked on older OS versions.")
                }
                print("DEBUG: Successfully enabled voice processing on microphone input node. This may help reduce echo.")
            } catch {
                print("ERROR: Could not enable voice processing on microphone input node: \(error.localizedDescription). Echo might persist.")
            }
        } else {
            print("INFO: Voice processing on AVAudioInputNode requires macOS 10.15+. Echo might persist on older OS versions.")
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
                print("Failed to create output PCM buffer for final converter.")
                return
            }
            
            var error: NSError?
            let status = finalConverter.convert(to: outputPCMBuffer, error: &error) { inNumPackets, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }
            
            if status == .error || error != nil {
                print("Final audio conversion error from mixer tap: \(error?.localizedDescription ?? "Unknown error")")
                return
            }
            
            if status == .haveData && outputPCMBuffer.frameLength > 0 {
                if finalOutputFormat.commonFormat == .pcmFormatInt16 && finalOutputFormat.isInterleaved {
                    let dataSize = Int(outputPCMBuffer.frameLength) * Int(finalOutputFormat.streamDescription.pointee.mBytesPerFrame)
                    if dataSize > 0, let int16Data = outputPCMBuffer.int16ChannelData?[0] {
                        let audioData = Data(bytes: int16Data, count: dataSize)
                        if self.audioFormatSentToFlutter && self.isFlutterEngineActive {
                            self.screenCaptureChannel?.invokeMethod("audioFrame", arguments: audioData)
                        }
                    } else if dataSize == 0 && outputPCMBuffer.frameLength > 0 {
                        print("DEBUG: Final converter output dataSize is 0 but frameLength > 0. Format: \(finalOutputFormat)")
                    }
                }
            }
        }
        
        print("DEBUG: Mixer NOT connected to outputNode to prevent echo feedback loop.")
        print("DEBUG: Simplified pipeline - SCStream will feed directly to mixer, no systemAudioPlayerNode needed.")
        
        audioEngine.prepare()
    }
    
    private func prepSCStreamFilter() {
        let excluded = availableContent?.applications.filter { app in
            Bundle.main.bundleIdentifier == app.bundleIdentifier
        }
        filter = SCContentFilter(display: availableContent!.displays.first!, excludingApplications: excluded ?? [], exceptingWindows: [])
        
        // Reset SCStream source format for a new session
        scStreamSourceFormat = nil
    }
    
    private func startAudioEngineAndCapture() throws {
        // Ensure engine is prepared before starting
        if !audioEngine.isRunning {
            do {
                try audioEngine.start()
                print("DEBUG: AVAudioEngine started with simplified pipeline.")
            } catch {
                print("ERROR: Failed to start AVAudioEngine: \(error.localizedDescription)")
                throw AudioManagerError.engineStartError("Failed to start audio engine: \(error.localizedDescription)")
            }
        }
        
        // Wait for engine to be fully running before starting player node
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            guard let self = self else { return }
            self.safelyStartPlayerNode()
        }
        
        print("DEBUG: Audio engine startup sequence initiated.")
    }
    
    private func recordSCStream(filter: SCContentFilter) async {
        let conf = SCStreamConfiguration()
        conf.width = 2
        conf.height = 2
        conf.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(600))
        conf.showsCursor = false
        conf.capturesAudio = true
        
        stream = SCStream(filter: filter, configuration: conf, delegate: self)
        do {
            try stream?.addStreamOutput(self, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
            try await stream?.startCapture()
            print("DEBUG: SCStream capture started.")
        } catch {
            print("Error starting SCStream capture: \(error.localizedDescription)")
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
            scStreamPlayerNode.play()
            print("DEBUG: SCStream player node started safely")
        } catch {
            print("ERROR: Failed to start player node safely: \(error.localizedDescription)")
        }
    }
    
    // MARK: - SCStream Delegate Methods
    
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sampleBuffer.isValid, type == .audio else { return }
        
        guard let pcmBufferFromSCStream = sampleBuffer.asPCMBuffer else {
            print("SCStream: Failed to get PCM buffer from CMSampleBuffer")
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
                print("DEBUG: Created SCStream->Mixer converter from \(scStreamSourceFormat!) to \(self.engineProcessingFormat!)")
            } else {
                print("DEBUG: SCStream format matches engine format - no conversion needed")
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
        
        // Schedule processed audio on the dedicated SCStream player node
        if scStreamPlayerNode.engine != nil && audioEngine.isRunning {
            if scStreamPlayerNode.isPlaying {
                scStreamPlayerNode.scheduleBuffer(processedBuffer, completionHandler: nil)
            } else {
                print("Warning: SCStream player node was not playing. Attempting to start and schedule.")
                safelyStartPlayerNode()
                // Give a small delay to ensure the node is ready
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.01) {
                    if self.scStreamPlayerNode.isPlaying {
                        self.scStreamPlayerNode.scheduleBuffer(processedBuffer, completionHandler: nil)
                    }
                }
            }
        }
    }
    
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped with error: \(error.localizedDescription)")
        if audioEngine.isRunning && isFlutterEngineActive {
            self.screenCaptureChannel?.invokeMethod("captureError", arguments: "SCStream stopped: \(error.localizedDescription)")
        }
        self.stream = nil
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