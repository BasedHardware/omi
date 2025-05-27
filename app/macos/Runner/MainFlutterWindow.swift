import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation

class MainFlutterWindow: NSWindow, SCStreamDelegate, SCStreamOutput {

    enum AudioQuality: Int {
        case normal = 128, good = 192, high = 256, extreme = 320
    }

    var availableContent: SCShareableContent?
    var filter: SCContentFilter?
    var audioSettings: [String: Any]!
    var stream: SCStream!

    private let audioEngine = AVAudioEngine()
    private let systemAudioPlayerNode = AVAudioPlayerNode()
    private let mixerNode = AVAudioMixerNode()

    private var engineProcessingFormat: AVAudioFormat!
    private var micNode: AVAudioInputNode!
    private var micNodeFormat: AVAudioFormat!
    var outputAudioFormat: AVAudioFormat?
    var audioConverter: AVAudioConverter?

    private var screenCaptureChannel: FlutterMethodChannel!
    private var audioFormatSentToFlutter: Bool = false

    private var scStreamSourceFormat: AVAudioFormat?
    
    // Two-step conversion: intermediate format and second converter
    private var scStreamIntermediateFormat: AVAudioFormat?
    private var scStreamSecondConverter: AVAudioConverter?

    // Manual resampling function to avoid AVAudioConverter OSStatus errors
    private func resampleAudio(input: [Float], fromRate: Double, toRate: Double) -> [Float] {
        if fromRate == toRate {
            return input
        }
        
        let ratio = fromRate / toRate
        let outputCount = Int(Double(input.count) / ratio)
        var output = [Float](repeating: 0, count: outputCount)
        
        for i in 0..<outputCount {
            let sourceIndex = Double(i) * ratio
            let index0 = Int(sourceIndex)
            let index1 = min(index0 + 1, input.count - 1)
            let fraction = sourceIndex - Double(index0)
            
            if index0 < input.count {
                output[i] = Float((1.0 - fraction) * Double(input[index0]) + fraction * Double(input[index1]))
            }
        }
        return output
    }
    
    // Convert stereo to mono by averaging channels
    private func stereoToMono(leftChannel: [Float], rightChannel: [Float]) -> [Float] {
        let count = min(leftChannel.count, rightChannel.count)
        var mono = [Float](repeating: 0, count: count)
        for i in 0..<count {
            mono[i] = (leftChannel[i] + rightChannel[i]) * 0.5
        }
        return mono
    }

    @available(macOS 14.0, *)
    func checkAndRequestMicrophonePermission() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted:
            return true
        case .denied:
            print("Microphone permission denied.")
            // Optionally, guide user to System Settings
            // NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!)
            return false
        case .undetermined:
            print("Microphone permission undetermined. Requesting...")
            let granted = await AVAudioApplication.requestRecordPermission()
            if granted {
                print("Microphone permission granted after request.")
            } else {
                print("Microphone permission denied after request.")
            }
            return granted
        @unknown default:
            print("Unknown microphone permission state.")
            return false
        }
    }

    override func awakeFromNib() {
        let flutterViewController = FlutterViewController()
        let windowFrame = self.frame
        self.contentViewController = flutterViewController
        self.setFrame(windowFrame, display: true)

        RegisterGeneratedPlugins(registry: flutterViewController)

        screenCaptureChannel = FlutterMethodChannel(
            name: "screenCapturePlatform",
            binaryMessenger: flutterViewController.engine.binaryMessenger)

        self.micNode = audioEngine.inputNode
        self.micNodeFormat = self.micNode.outputFormat(forBus: 0)

        // Attempt to enable voice processing for AEC
        // This should be done before the engine is started or the graph is fully configured.
        if #available(macOS 10.15, *) { // setVoiceProcessingEnabled is available macOS 10.15+
            do {
                try self.micNode.setVoiceProcessingEnabled(true)
                print("DEBUG: Successfully enabled voice processing on microphone input node. This may help reduce echo.")
            } catch {
                print("ERROR: Could not enable voice processing on microphone input node: \(error.localizedDescription). Echo might persist.")
            }
        } else {
            print("INFO: Voice processing on AVAudioInputNode requires macOS 10.15+. Echo might persist on older OS versions.")
        }

        engineProcessingFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                               sampleRate: self.micNodeFormat.sampleRate, // Use mic's native rate
                                               channels: 1, // MONO for mixing
                                               interleaved: false)
        
        print("DEBUG: Engine processing format (mic native SR: \(self.micNodeFormat.sampleRate)) SR: \(engineProcessingFormat.sampleRate), CH: \(engineProcessingFormat.channelCount)")

        setupAudioEngine() // Uses engineProcessingFormat for mixer tap and systemAudioPlayerNode connection

        screenCaptureChannel.setMethodCallHandler { [weak self] (call, result) in
            guard let self = self else { return }
            switch call.method {
            case "start":
                Task {
                    if #available(macOS 14.0, *) {
                        let micPermissionGranted = await self.checkAndRequestMicrophonePermission()
                        guard micPermissionGranted else {
                            result(FlutterError(code: "MIC_PERMISSION_DENIED", message: "Microphone permission was not granted.", details: nil))
                            return
                        }
                    } else {
                        print("Warning: Microphone permission check is for macOS 14+. On older versions, proceeding without explicit check.")
                    }

                    self.audioFormatSentToFlutter = false
                    self.scStreamSourceFormat = nil   // Reset for new stream

                SCShareableContent.getExcludingDesktopWindows(true, onScreenWindowsOnly: true) { content, error in
                    if let error = error {
                            self.handleError(error, result: result)
                            return
                        }
                        self.availableContent = content
                        
                        // outputAudioFormat for Flutter (e.g., 16kHz or 44.1kHz Mono Int16)
                        // Let's target 16kHz for Flutter as a common speech rate.
                        let flutterOutputSampleRate = 16000.0 
                        let flutterOutputChannels: AVAudioChannelCount = 1
                        self.updateAudioSettings(sampleRate: flutterOutputSampleRate, channels: flutterOutputChannels)

                        print("DEBUG: Flutter output format will be SR: \(flutterOutputSampleRate), CH: \(flutterOutputChannels)")
                        self.outputAudioFormat = AVAudioFormat(commonFormat: .pcmFormatInt16,
                                                               sampleRate: flutterOutputSampleRate,
                                                               channels: flutterOutputChannels,
                                                               interleaved: true)

                        guard let strongOutputAudioFormat = self.outputAudioFormat else {
                            result(FlutterError(code: "AUDIO_FORMAT_ERROR", message: "Could not create final output audio format for Flutter", details: nil))
                            return
                        }

                        // Final converter: engineProcessingFormat -> outputAudioFormat (for Flutter)
                        self.audioConverter = AVAudioConverter(from: self.engineProcessingFormat, to: strongOutputAudioFormat)
                        guard self.audioConverter != nil else {
                            result(FlutterError(code: "CONVERTER_SETUP_ERROR", message: "Could not create main audio converter to Flutter format", details: nil))
                        return
                        }
                        self.audioConverter?.sampleRateConverterAlgorithm = AVSampleRateConverterAlgorithm_Mastering
                        self.audioConverter?.sampleRateConverterQuality = .max
                        
                        // Enable dithering for better quality when converting to Int16
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
                        self.screenCaptureChannel.invokeMethod("audioFormat", arguments: formatDetails)
                        self.audioFormatSentToFlutter = true
                        
                        self.prepSCStreamFilter()
                        
                        do {
                            try self.startAudioEngineAndCapture()
                            Task { await self.recordSCStream(filter: self.filter!) }
                            result(nil)
                        } catch {
                            print("Error starting audio engine or capture: \(error.localizedDescription)")
                            result(FlutterError(code: "ENGINE_START_ERROR", message: error.localizedDescription, details: nil))
                        }
                    }
                }
            case "stop":
                self.stopAudioEngineAndCapture()
                result(nil)
            default:
                result(FlutterMethodNotImplemented)
            }
        }
        super.awakeFromNib()
    }

    func handleError(_ error: Error, result: FlutterResult) {
        switch error {
        case SCStreamError.userDeclined:
            NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!)
            result(FlutterError(code: "PERMISSION_ERROR", message: "User declined screen capture permission.", details: nil))
        default:
            print("[err] failed to fetch available content: \(error.localizedDescription)")
            result(FlutterError(code: "SHAREABLE_CONTENT_ERROR", message: error.localizedDescription, details: nil))
        }
    }

    func setupAudioEngine() {
        audioEngine.attach(systemAudioPlayerNode)
        audioEngine.attach(mixerNode)

        // Set systemAudioPlayerNode to full volume to ensure system audio
        // is captured at proper levels for recording
        systemAudioPlayerNode.volume = 4.0
        print("DEBUG: systemAudioPlayerNode volume set to 1.0 for proper system audio capture.")

        print("DEBUG: Mic native format: \(self.micNodeFormat!))")
        print("DEBUG: Engine processing format: \(self.engineProcessingFormat!))")
        
        audioEngine.connect(self.micNode, to: mixerNode, format: self.micNodeFormat) // Mic uses its native format
        
        // systemAudioPlayerNode connected to mixer using engineProcessingFormat
        audioEngine.connect(systemAudioPlayerNode, to: mixerNode, format: self.engineProcessingFormat)

        // Set mixer output volume to ensure proper levels
        mixerNode.outputVolume = 4.0
        print("DEBUG: Mixer output volume set to 1.0 for proper audio levels.")

        // Mixer tap is at engineProcessingFormat
        mixerNode.installTap(onBus: 0, bufferSize: 1024, format: self.engineProcessingFormat) { [weak self] (buffer, time) in
            guard let self = self, let finalConverter = self.audioConverter, let finalOutputFormat = self.outputAudioFormat else {
                // print("Mixer tap: finalConverter or finalOutputFormat is nil")
                return
            }

            let outputBufferFrameCapacity = AVAudioFrameCount(Double(buffer.frameLength) * (finalOutputFormat.sampleRate / buffer.format.sampleRate))
            guard let outputPCMBuffer = AVAudioPCMBuffer(pcmFormat: finalOutputFormat, frameCapacity: outputBufferFrameCapacity) else {
                print("Failed to create output PCM buffer for final converter.")
                return
            }
            // outputPCMBuffer.frameLength = outputPCMBuffer.frameCapacity // Set frameLength after conversion

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
                 outputPCMBuffer.frameLength = outputPCMBuffer.frameCapacity // THIS WAS IN THE WRONG PLACE - set it before checking data size if using frameCapacity
                                                                            // Actually, the converter sets the frameLength of outputPCMBuffer.

                if finalOutputFormat.commonFormat == .pcmFormatInt16 && finalOutputFormat.isInterleaved {
                    let dataSize = Int(outputPCMBuffer.frameLength) * Int(finalOutputFormat.streamDescription.pointee.mBytesPerFrame)
                    if dataSize > 0, let int16Data = outputPCMBuffer.int16ChannelData?[0] {
                        let audioData = Data(bytes: int16Data, count: dataSize)
                        if self.audioFormatSentToFlutter {
                           self.screenCaptureChannel.invokeMethod("audioFrame", arguments: audioData)
                        }
                    } else if dataSize == 0 && outputPCMBuffer.frameLength > 0 {
                         print("DEBUG: Final converter output dataSize is 0 but frameLength > 0. Format: \(finalOutputFormat)")
                    }
                }
            }
        }

        // REMOVED: The connection from mixerNode to outputNode was causing echo feedback.
        // The mixerNode was routing the combined audio (including microphone) back to system output,
        // which SCStream would then capture, creating a circular feedback loop.
        // We only need the mixer for combining sources and tapping for recording, not for playback.
        // audioEngine.disconnectNodeOutput(mixerNode) // make sure we have a clean slot
        // audioEngine.connect(mixerNode, to: audioEngine.outputNode, format: self.engineProcessingFormat)
        // mixerNode.volume = 0 // mute – we only need the connection for clocking, not playback
        print("DEBUG: Mixer NOT connected to outputNode to prevent echo feedback loop.")
        
        audioEngine.prepare()
    }

    func prepSCStreamFilter() {
    let excluded = availableContent?.applications.filter { app in
            Bundle.main.bundleIdentifier == app.bundleIdentifier
    }
    filter = SCContentFilter(display: availableContent!.displays.first!, excludingApplications: excluded ?? [], exceptingWindows: [])

        // Reset SCStream source format for a new session
        scStreamSourceFormat = nil
    }

    func startAudioEngineAndCapture() throws {
        // REMOVED AVAudioSession configuration lines that are unavailable/problematic on macOS
        
        if !audioEngine.isRunning {
            try audioEngine.start()
            print("DEBUG: AVAudioEngine started.")
        }
        
        // Ensure systemAudioPlayerNode is playing AFTER the engine has started.
        if systemAudioPlayerNode.engine != nil && !systemAudioPlayerNode.isPlaying { 
             systemAudioPlayerNode.play() 
             print("DEBUG: systemAudioPlayerNode explicitly started in startAudioEngineAndCapture.")
        } else if systemAudioPlayerNode.engine == nil {
            print("ERROR: systemAudioPlayerNode.engine is nil in startAudioEngineAndCapture. Cannot play.")
        } else if systemAudioPlayerNode.isPlaying {
            print("DEBUG: systemAudioPlayerNode was already playing in startAudioEngineAndCapture.")
        }
    }

    func recordSCStream(filter: SCContentFilter) async {
    let conf = SCStreamConfiguration()
    conf.width = 2
    conf.height = 2
        conf.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(600))
        conf.showsCursor = false
    conf.capturesAudio = true
        
        // DO NOT explicitly set conf.sampleRate or conf.channelCount here.
        // Let SCStream use its default/preferred audio format.
        // We will convert it if necessary.
        // conf.sampleRate = Int(self.engineProcessingFormat.sampleRate) // REMOVED
        // conf.channelCount = Int(self.engineProcessingFormat.channelCount) // REMOVED

    stream = SCStream(filter: filter, configuration: conf, delegate: self)
    do {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: .global(qos: .userInitiated))
        try await stream.startCapture()
            print("DEBUG: SCStream capture started.")
    } catch {
            print("Error starting SCStream capture: \(error.localizedDescription)")
            self.screenCaptureChannel.invokeMethod("captureError", arguments: "SCStream: \(error.localizedDescription)")
            DispatchQueue.main.async { self.stopAudioEngineAndCapture() }
    }
}

    func stopAudioEngineAndCapture() {
        // Stop SCStream first
    if stream != nil {
            Task {
                try? await stream.stopCapture() // Errors handled in delegate or ignored for stop
                self.stream = nil
            }
        }
        
        // Stop AVAudioEngine
        if audioEngine.isRunning {
            audioEngine.stop()
            // audioEngine.inputNode.removeTap(onBus: 0) // If mic tap was used directly
            // mixerNode.removeTap(onBus: 0) // Tap is auto-removed when engine stops or node is reset
        }
        systemAudioPlayerNode.stop()


        // Reset converters and formats
        self.audioConverter = nil
        self.scStreamSourceFormat = nil

        // Notify Flutter
        if audioFormatSentToFlutter { // Only send if start was successful enough to send format
            self.screenCaptureChannel.invokeMethod("audioStreamEnded", arguments: nil)
            print("Recording stopped (engine & SCStream), Flutter notified.")
        } else {
            print("Recording stopped (engine & SCStream), but Flutter was not fully initialized for audio.")
        }
        audioFormatSentToFlutter = false // Reset for next session
    }

    // Modified to accept parameters
    func updateAudioSettings(sampleRate: Double, channels: AVAudioChannelCount) {
        audioSettings = [AVSampleRateKey: sampleRate, AVNumberOfChannelsKey: channels]
    }

    // SCStream Delegate methods
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sampleBuffer.isValid, type == .audio else { return }

        guard let pcmBufferFromSCStream = sampleBuffer.asPCMBuffer else {
            print("SCStream: Failed to get PCM buffer from CMSampleBuffer")
            return
        }

        if scStreamSourceFormat == nil {
            scStreamSourceFormat = pcmBufferFromSCStream.format
            print("DEBUG: SCStream actual source format: \(scStreamSourceFormat!)")
            
            // Detailed format logging
            let sourceDesc = scStreamSourceFormat!.streamDescription.pointee
            print("DEBUG: SCStream format details - SR: \(sourceDesc.mSampleRate), CH: \(sourceDesc.mChannelsPerFrame), BitsPerCh: \(sourceDesc.mBitsPerChannel), BytesPerFrame: \(sourceDesc.mBytesPerFrame), BytesPerPacket: \(sourceDesc.mBytesPerPacket)")
            
            let engineDesc = self.engineProcessingFormat.streamDescription.pointee  
            print("DEBUG: Engine format details - SR: \(engineDesc.mSampleRate), CH: \(engineDesc.mChannelsPerFrame), BitsPerCh: \(engineDesc.mBitsPerChannel), BytesPerFrame: \(engineDesc.mBytesPerFrame), BytesPerPacket: \(engineDesc.mBytesPerPacket)")
            
            // Check if formats differ and note for manual processing
            if scStreamSourceFormat != self.engineProcessingFormat {
                print("DEBUG: SCStream format (\(scStreamSourceFormat!)) differs from Engine format (\(self.engineProcessingFormat!)). Will use manual conversion.")
    } else {
                print("DEBUG: SCStream format matches Engine format. No conversion needed.")
            }
        }

        var bufferToSchedule: AVAudioPCMBuffer = pcmBufferFromSCStream

        // Manual conversion if formats differ (avoiding AVAudioConverter OSStatus errors)
        // First, ensure scStreamSourceFormat is not nil before checking its properties or comparing it.
        guard let currentSCStreamFormat = self.scStreamSourceFormat else {
            print("ERROR: scStreamSourceFormat is nil. Cannot process SCStream audio buffer. Buffer skipped.")
            return
        }

        if currentSCStreamFormat != self.engineProcessingFormat {
            // This block is for when SCStream's format differs from our desired engineProcessingFormat (mono, float, specific SR).
            // The original crash happened here due to assumptions about floatChannelData.
            // We need to ensure the input is deinterleaved float to use floatChannelData directly.
            
            guard currentSCStreamFormat.commonFormat == .pcmFormatFloat32,
                  !currentSCStreamFormat.isInterleaved, // Must be deinterleaved for this specific access pattern
                  let floatDataPointers = pcmBufferFromSCStream.floatChannelData else {
                print("ERROR: SCStream buffer (format: \(currentSCStreamFormat.description)) is not in deinterleaved float format or floatChannelData is nil. Cannot perform current manual conversion. Buffer skipped.")
                // TODO: Consider a fallback to AVAudioConverter if other formats from SCStream need robust handling here.
                return
            }

            let inputFrameCount = Int(pcmBufferFromSCStream.frameLength)
            let inputSampleRate = currentSCStreamFormat.sampleRate
            let outputSampleRate = self.engineProcessingFormat.sampleRate
            var monoResampled: [Float] // This will hold the audio data after resampling and mono conversion

            if currentSCStreamFormat.channelCount == 1 {
                // Input is already mono (but deinterleaved float as per guard)
                let sourceChannelPtr = floatDataPointers[0]
                let sourceArray = Array(UnsafeBufferPointer(start: sourceChannelPtr, count: inputFrameCount))
                if inputSampleRate != outputSampleRate {
                    monoResampled = resampleAudio(input: sourceArray, fromRate: inputSampleRate, toRate: outputSampleRate)
                } else {
                    monoResampled = sourceArray
                }
                print("DEBUG: Manual conversion: SCStream Mono \(inputSampleRate)Hz -> Engine Mono \(outputSampleRate)Hz")
            } else if currentSCStreamFormat.channelCount >= 2 {
                // Input is stereo (or more channels, take first two) deinterleaved float
                let leftChannelPtr = floatDataPointers[0]
                let rightChannelPtr = floatDataPointers[1] // Safe due to channelCount >= 2

                let leftArray = Array(UnsafeBufferPointer(start: leftChannelPtr, count: inputFrameCount))
                let rightArray = Array(UnsafeBufferPointer(start: rightChannelPtr, count: inputFrameCount))

                let leftResampled: [Float]
                let rightResampled: [Float]

                if inputSampleRate != outputSampleRate {
                    leftResampled = resampleAudio(input: leftArray, fromRate: inputSampleRate, toRate: outputSampleRate)
                    rightResampled = resampleAudio(input: rightArray, fromRate: inputSampleRate, toRate: outputSampleRate)
                } else {
                    leftResampled = leftArray
                    rightResampled = rightArray
                }
                monoResampled = stereoToMono(leftChannel: leftResampled, rightChannel: rightResampled)
                print("DEBUG: Manual conversion: SCStream \(currentSCStreamFormat.channelCount)-channel \(inputSampleRate)Hz -> Engine Mono \(outputSampleRate)Hz")
            } else {
                print("ERROR: SCStream buffer has \(currentSCStreamFormat.channelCount) channels (e.g., 0), which is not supported for manual conversion. Buffer skipped.")
                return
            }
            
            // Create output buffer for the processed monoResampled data
            let outputFrameCount = monoResampled.count
            guard let manuallyConvertedBuffer = AVAudioPCMBuffer(pcmFormat: self.engineProcessingFormat, frameCapacity: AVAudioFrameCount(outputFrameCount)) else {
                print("ERROR: Failed to create output buffer for manually converted audio.")
                return
            }
            manuallyConvertedBuffer.frameLength = AVAudioFrameCount(outputFrameCount)
            
            // engineProcessingFormat is known to be non-interleaved Float32, so floatChannelData![0] is correct for it.
            let monoOutputDataPtr = manuallyConvertedBuffer.floatChannelData![0]
            for i in 0..<outputFrameCount {
                monoOutputDataPtr[i] = monoResampled[i]
            }
            
            bufferToSchedule = manuallyConvertedBuffer
            // Original debug log: print("DEBUG: Manual conversion complete: \(inputFrameCount) → \(outputFrameCount) frames (stereo \(inputSampleRate)Hz → mono \(outputSampleRate)Hz)")
        }

        if systemAudioPlayerNode.engine != nil && audioEngine.isRunning {
            if systemAudioPlayerNode.isPlaying {
                systemAudioPlayerNode.scheduleBuffer(bufferToSchedule, completionHandler: nil)
            } else {
                print("Warning: systemAudioPlayerNode was not playing when an audio buffer was received. Attempting to play and schedule.")
                systemAudioPlayerNode.play()
                systemAudioPlayerNode.scheduleBuffer(bufferToSchedule, completionHandler: nil)
            }
        } else {
             // This log can be noisy if it happens after stop has been called.
             // Only log if we expect to be running.
             // if self.stream != nil { // A proxy for "capture is supposed to be active"
             //    print("Debug: systemAudioPlayerNode.engine is nil or audioEngine is not running. SCStream Buffer not scheduled.")
             // }
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped with error: \(error.localizedDescription)")
        if audioEngine.isRunning {
             self.screenCaptureChannel.invokeMethod("captureError", arguments: "SCStream stopped: \(error.localizedDescription)")
        }
    self.stream = nil
        // Consider if a full stopAudioEngineAndCapture is needed or if it's handled by the main stop call.
        // If SCStream stops unexpectedly, it might be good to tear down the whole engine.
        // However, the Flutter 'stop' call is the primary trigger for full shutdown.
        // For now, just log and nil out the stream. The 'stop' call will do full cleanup.
}
}

extension CMSampleBuffer {
    var asPCMBuffer: AVAudioPCMBuffer? {
        try? self.withAudioBufferList { audioBufferList, blockBuffer -> AVAudioPCMBuffer? in
            guard var absd = self.formatDescription?.audioStreamBasicDescription else { return nil }
            guard let format = AVAudioFormat(streamDescription: &absd) else { return nil}
            return AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: audioBufferList.unsafePointer)
        }
    }
}