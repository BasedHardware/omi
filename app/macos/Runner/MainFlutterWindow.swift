import Cocoa
import FlutterMacOS
import ScreenCaptureKit
import AVFoundation
import CoreBluetooth
import CoreLocation

class MainFlutterWindow: NSWindow, SCStreamDelegate, SCStreamOutput, CBCentralManagerDelegate, CLLocationManagerDelegate {

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

    // Bluetooth and Location managers
    private var bluetoothManager: CBCentralManager?
    private var locationManager: CLLocationManager?
    private var bluetoothPermissionCompletion: ((Bool) -> Void)?
    private var locationPermissionCompletion: ((Bool) -> Void)?

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
    func checkMicrophonePermission() -> String {
        switch AVAudioApplication.shared.recordPermission {
        case .granted:
            return "granted"
        case .denied:
            return "denied"
        case .undetermined:
            return "undetermined"
        @unknown default:
            return "unknown"
        }
    }
    
    @available(macOS 14.0, *)
    func requestMicrophonePermission() async -> Bool {
        guard AVAudioApplication.shared.recordPermission != .granted else {
            return true // Already granted
        }
        
        let granted = await AVAudioApplication.requestRecordPermission()
        print("Microphone permission request result: \(granted)")
        return granted
    }
    
    func checkScreenCapturePermission() async -> String {
        do {
            // Try to get shareable content to check if we have permission
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            return content.displays.isEmpty ? "denied" : "granted"
        } catch {
            if case SCStreamError.userDeclined = error {
                return "denied"
            }
            return "undetermined"
        }
    }
    
    func requestScreenCapturePermission() async -> Bool {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            return !content.displays.isEmpty
        } catch {
            if case SCStreamError.userDeclined = error {
                // Open system preferences for user to grant permission
                await MainActor.run {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")!)
                }
                return false
            }
            print("Error checking screen capture permission: \(error)")
            return false
        }
    }

    // MARK: - Bluetooth Permission Management
    
    func checkBluetoothPermission() -> String {
        if #available(macOS 10.15, *) {
            switch CBCentralManager.authorization {
            case .allowedAlways:
                return "granted"
            case .denied:
                return "denied"
            case .restricted:
                return "restricted"
            case .notDetermined:
                return "undetermined"
            @unknown default:
                return "unknown"
            }
        } else {
            // For older macOS versions, assume granted if Bluetooth is available
            return "granted"
        }
    }
    
    func requestBluetoothPermission() async -> Bool {
        if #available(macOS 10.15, *) {
            guard CBCentralManager.authorization != .allowedAlways else {
                return true // Already granted
            }
            
            // If explicitly denied or restricted, can't request again
            if CBCentralManager.authorization == .denied || CBCentralManager.authorization == .restricted {
                print("Bluetooth permission is \(CBCentralManager.authorization.rawValue), cannot request again")
                return false
            }
            
            // Check if Bluetooth service is available first
            let tempManager = CBCentralManager()
            if tempManager.state == .poweredOff {
                print("Bluetooth is powered off. User needs to enable Bluetooth in System Settings.")
                await MainActor.run {
                    NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.bluetooth")!)
                }
                return false
            } else if tempManager.state == .unsupported {
                print("Bluetooth is not supported on this device.")
                return false
            }
            
            return await withCheckedContinuation { continuation in
                // Set up timeout to prevent continuation leak
                Task {
                    try? await Task.sleep(nanoseconds: 15_000_000_000) // 15 seconds timeout for Bluetooth
                    if bluetoothPermissionCompletion != nil {
                        print("Bluetooth permission request timed out")
                        bluetoothPermissionCompletion?(false)
                    }
                }
                
                bluetoothPermissionCompletion = { granted in
                    continuation.resume(returning: granted)
                    self.bluetoothPermissionCompletion = nil // Clear to prevent multiple calls
                }
                
                // Initialize CBCentralManager to trigger permission request
                if bluetoothManager == nil {
                    print("Initializing Bluetooth central manager...")
                    bluetoothManager = CBCentralManager(delegate: self, queue: nil)
                } else {
                    // If manager already exists, check current state
                    print("Bluetooth manager exists, checking current state...")
                    centralManagerDidUpdateState(bluetoothManager!)
                }
            }
        } else {
            print("Bluetooth permission handling not available on macOS < 10.15, assuming granted")
            return true // Assume granted on older macOS versions
        }
    }
    
    // MARK: - Location Permission Management
    
    func checkLocationPermission() -> String {
        switch CLLocationManager.authorizationStatus() {
        case .authorizedAlways, .authorized:
            return "granted"
        case .denied:
            return "denied"
        case .restricted:
            return "restricted"
        case .notDetermined:
            return "undetermined"
        @unknown default:
            return "unknown"
        }
    }
    
    func requestLocationPermission() async -> Bool {
        let currentStatus = CLLocationManager.authorizationStatus()
        guard currentStatus != .authorizedAlways && currentStatus != .authorized else {
            return true
        }
        
        guard currentStatus == .notDetermined else {
            print("Location permission is \(currentStatus.rawValue), opening System Preferences")
            await MainActor.run {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices")!)
            }
            return false
        }
        
        // Check if location services are enabled before requesting
        guard CLLocationManager.locationServicesEnabled() else {
            print("Location services are disabled system-wide, opening System Preferences")
            await MainActor.run {
                NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices")!)
            }
            return false
        }
        
        return await withCheckedContinuation { continuation in
            // Set up timeout to prevent continuation leak
            Task {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10 seconds timeout
                if locationPermissionCompletion != nil {
                    print("Location permission request timed out")
                    locationPermissionCompletion?(false)
                }
            }
            
            locationPermissionCompletion = { granted in
                continuation.resume(returning: granted)
                self.locationPermissionCompletion = nil
            }
            
            if locationManager == nil {
                locationManager = CLLocationManager()
                locationManager?.delegate = self
            }
            
            locationManager?.requestWhenInUseAuthorization()
        }
    }
    
    // MARK: - CBCentralManagerDelegate
    
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        print("Bluetooth central manager state updated to: \(central.state.rawValue)")
        
        // Handle different Bluetooth states
        switch central.state {
        case .poweredOff:
            print("Bluetooth is powered off. Permission cannot be granted until Bluetooth is enabled.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .unsupported:
            print("Bluetooth is not supported on this device.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .unauthorized:
            print("Bluetooth access is not authorized for this app.")
            bluetoothPermissionCompletion?(false)
            bluetoothPermissionCompletion = nil
            return
        case .poweredOn:
            break
        case .unknown, .resetting:
            print("Bluetooth state is \(central.state). Waiting for definitive state...")
            return
        @unknown default:
            print("Unknown Bluetooth state: \(central.state)")
            return
        }
        
        if #available(macOS 10.15, *) {
            let granted: Bool
            switch CBCentralManager.authorization {
            case .allowedAlways:
                granted = true
            case .denied, .restricted:
                granted = false
            case .notDetermined:
                granted = (central.state == .poweredOn)
            @unknown default:
                granted = false
            }
            
            print("Bluetooth permission resolved: granted=\(granted)")
            bluetoothPermissionCompletion?(granted)
            bluetoothPermissionCompletion = nil
        } else {
            let granted = (central.state == .poweredOn)
            bluetoothPermissionCompletion?(granted)
            bluetoothPermissionCompletion = nil
        }
    }
    
    // MARK: - CLLocationManagerDelegate
    
    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        print("Location authorization changed to: \(status.rawValue)")
        
        guard let completion = locationPermissionCompletion else {
            print("Location permission completion is nil, ignoring delegate call")
            return
        }
        
        let granted = (status == .authorizedAlways || status == .authorized)
        print("Location permission resolved: granted=\(granted)")
        completion(granted)
    }
    
    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("Location manager failed with error: \(error.localizedDescription)")
        locationPermissionCompletion?(false)
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
        if #available(macOS 10.15, *) {
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
            case "checkMicrophonePermission":
                if #available(macOS 14.0, *) {
                    let status = self.checkMicrophonePermission()
                    result(status)
                } else {
                    result("unavailable")
                }
                
            case "requestMicrophonePermission":
                if #available(macOS 14.0, *) {
                    Task {
                        let granted = await self.requestMicrophonePermission()
                        result(granted)
                    }
                } else {
                    result(false)
                }
                
            case "checkScreenCapturePermission":
                Task {
                    let status = await self.checkScreenCapturePermission()
                    result(status)
                }
                
            case "requestScreenCapturePermission":
                Task {
                    let granted = await self.requestScreenCapturePermission()
                    result(granted)
                }
                
            case "checkBluetoothPermission":
                let status = self.checkBluetoothPermission()
                result(status)
                
            case "requestBluetoothPermission":
                Task {
                    let granted = await self.requestBluetoothPermission()
                    result(granted)
                }
                
            case "checkLocationPermission":
                let status = self.checkLocationPermission()
                result(status)
                
            case "requestLocationPermission":
                Task {
                    let granted = await self.requestLocationPermission()
                    result(granted)
                }
                
            case "start":
                Task {
                    // Check permissions before starting
                    if #available(macOS 14.0, *) {
                        let micStatus = self.checkMicrophonePermission()
                        if micStatus != "granted" {
                            result(FlutterError(code: "MIC_PERMISSION_REQUIRED", 
                                              message: "Microphone permission is required. Current status: \(micStatus)", 
                                              details: nil))
                            return
                        }
                    }
                    
                    let screenStatus = await self.checkScreenCapturePermission()
                    if screenStatus != "granted" {
                        result(FlutterError(code: "SCREEN_PERMISSION_REQUIRED", 
                                          message: "Screen capture permission is required. Current status: \(screenStatus)", 
                                          details: nil))
                        return
                    }

                    self.audioFormatSentToFlutter = false
                    self.scStreamSourceFormat = nil

                SCShareableContent.getExcludingDesktopWindows(true, onScreenWindowsOnly: true) { content, error in
                    if let error = error {
                            self.handleError(error, result: result)
                            return
                        }
                        self.availableContent = content
                        
                        // outputAudioFormat for Flutter (e.g., 16kHz or 44.1kHz Mono Int16)
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
        systemAudioPlayerNode.volume = 4.0

        print("DEBUG: Mic native format: \(self.micNodeFormat!))")
        print("DEBUG: Engine processing format: \(self.engineProcessingFormat!))")
        
        audioEngine.connect(self.micNode, to: mixerNode, format: self.micNodeFormat) // Mic uses its native format
        
        // systemAudioPlayerNode connected to mixer using engineProcessingFormat
        audioEngine.connect(systemAudioPlayerNode, to: mixerNode, format: self.engineProcessingFormat)

        // Set mixer output volume to ensure proper levels
        mixerNode.outputVolume = 4.0

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
                 outputPCMBuffer.frameLength = outputPCMBuffer.frameCapacity

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
        // Keeping it in comment so that everyone can see it and understand why it was removed.
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
        // conf.sampleRate = Int(self.engineProcessingFormat.sampleRate)
        // conf.channelCount = Int(self.engineProcessingFormat.channelCount)

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
                try? await stream.stopCapture()
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
        if audioFormatSentToFlutter {
            self.screenCaptureChannel.invokeMethod("audioStreamEnded", arguments: nil)
            print("Recording stopped (engine & SCStream), Flutter notified.")
        } else {
            print("Recording stopped (engine & SCStream), but Flutter was not fully initialized for audio.")
        }
        audioFormatSentToFlutter = false
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
        guard let currentSCStreamFormat = self.scStreamSourceFormat else {
            print("ERROR: scStreamSourceFormat is nil. Cannot process SCStream audio buffer. Buffer skipped.")
            return
        }

        if currentSCStreamFormat != self.engineProcessingFormat {
            // This block is for when SCStream's format differs from our desired engineProcessingFormat (mono, float, specific SR).
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
        }

        if systemAudioPlayerNode.engine != nil && audioEngine.isRunning {
            if systemAudioPlayerNode.isPlaying {
                systemAudioPlayerNode.scheduleBuffer(bufferToSchedule, completionHandler: nil)
            } else {
                print("Warning: systemAudioPlayerNode was not playing when an audio buffer was received. Attempting to play and schedule.")
                systemAudioPlayerNode.play()
                systemAudioPlayerNode.scheduleBuffer(bufferToSchedule, completionHandler: nil)
            }
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("SCStream stopped with error: \(error.localizedDescription)")
        if audioEngine.isRunning {
             self.screenCaptureChannel.invokeMethod("captureError", arguments: "SCStream stopped: \(error.localizedDescription)")
        }
    self.stream = nil
        // If SCStream stops unexpectedly, it might be good to tear down the whole engine.
        // However, the Flutter 'stop' call is the primary trigger for full shutdown.
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