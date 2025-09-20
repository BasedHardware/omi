import Foundation
import WatchConnectivity
import AVFoundation

@MainActor
class WatchAudioRecorderViewModel: NSObject, ObservableObject {
    @Published var isRecording: Bool = false

    var session: WCSession
    private var audioEngine: AVAudioEngine?
    private var inputNode: AVAudioInputNode?
    private var audioBuffer: AVAudioPCMBuffer?
    private var chunkIndex: Int = 0
    private var isStreaming: Bool = false
    private var inputFormat: AVAudioFormat?
    private var audioConverter: AVAudioConverter?
    private var targetFormat: AVAudioFormat?
    private var detectedSampleRate: Double = 0.0
    
    // Audio buffering for multi-second chunks
    private var chunkBuffer: Data = Data()
    private var bufferStartTime: Date?
    private let bufferDuration: TimeInterval = 1.5 // 1.5 second chunks
    
    init(session: WCSession = .default) {
        self.session = session
        super.init()
        self.session.delegate = self
        session.activate()
        
        BatteryManager.shared.startBatteryMonitoring()
        BatteryManager.shared.sendWatchInfo()
    }

    func startRecording() {
        print("Watch: startRecording called, current isRecording: \(isRecording)")
        guard !isRecording else {
            print("Watch: Already recording, ignoring startRecording")
            return
        }

        print("Watch: Starting audio recording...")

        // Check microphone permissions and setup audio session
        checkMicrophonePermissionAndSetup { [weak self] success in
            guard let self = self else {
                print("Watch: self is nil in permission check completion")
                return
            }

            if success {
                print("Watch: Permission check successful, setting up audio streaming")
                // Setup audio streaming
                self.setupAudioStreaming()
                self.isRecording = true
                self.session.sendMessage(["method": "startRecording"], replyHandler: nil)
                print("Watch: Recording started successfully")
            } else {
                print("Watch: Failed to start recording - microphone permission denied or setup failed")
                // Send error message to Flutter app
                self.session.sendMessage(["method": "recordingError", "error": "Microphone permission denied"], replyHandler: nil)
            }
        }
    }

    func stopRecording() {
        guard isRecording else {
            print("stopRecording called but not currently recording")
            return
        }

        isRecording = false
        isStreaming = false

        // Stop audio streaming
        inputNode?.removeTap(onBus: 0)
        audioEngine?.stop()
        inputNode = nil
        audioEngine = nil

        // Clean up resampling resources
        audioConverter = nil
        targetFormat = nil
        detectedSampleRate = 0.0

        // Send any remaining buffered data and final chunk
        sendFinalAudioChunk()
        
        // Reset buffer state
        chunkBuffer = Data()
        bufferStartTime = nil

        session.sendMessage(["method": "stopRecording"], replyHandler: nil)
    }

    private func bufferAndSendAudioData(_ audioData: Data) {
        // Initialize buffer start time on first data
        if bufferStartTime == nil {
            bufferStartTime = Date()
        }
        
        // Add data to buffer
        chunkBuffer.append(audioData)
        
        // Check if we've buffered for target duration
        let currentTime = Date()
        let elapsedTime = currentTime.timeIntervalSince(bufferStartTime!)
        
        if elapsedTime >= bufferDuration {
            // Send the accumulated buffer
            sendBufferedAudioChunk()
            
            // Reset buffer for next window
            chunkBuffer = Data()
            bufferStartTime = currentTime
        }
    }
    
    private func sendBufferedAudioChunk() {
        guard !chunkBuffer.isEmpty else { return }
        
        let messageData: [String: Any] = [
            "method": "sendAudioChunk",
            "audioChunk": chunkBuffer,
            "chunkIndex": chunkIndex,
            "isLast": false,
            "sampleRate": 16000.0
        ]
        
        if session.isReachable {
            session.sendMessage(messageData, replyHandler: nil) { error in
                print("sendMessage failed for chunk \(self.chunkIndex): \(error.localizedDescription)")
                // Fallback to transferUserInfo for background reliability
                self.session.transferUserInfo(messageData)
                print("Fallback: Sent chunk \(self.chunkIndex) via transferUserInfo (\(self.chunkBuffer.count) bytes)")
            }
            print("Sent chunk \(chunkIndex) via sendMessage (\(chunkBuffer.count) bytes)")
        } else {
            // Use transferUserInfo when not reachable (background/screen off)
            session.transferUserInfo(messageData)
        }
        
        chunkIndex += 1
    }
    
    private func sendFinalAudioChunk() {
        // Send any remaining buffered data
        if !chunkBuffer.isEmpty {
            sendBufferedAudioChunk()
        }
        
        let finalMessageData: [String: Any] = [
            "method": "sendAudioChunk",
            "audioChunk": Data(),
            "chunkIndex": chunkIndex,
            "isLast": true,
            "sampleRate": 16000.0
        ]
        
        if session.isReachable {
            session.sendMessage(finalMessageData, replyHandler: nil) { error in
                self.session.transferUserInfo(finalMessageData)
                print("Final chunk sent via transferUserInfo fallback")
            }
        } else {
            session.transferUserInfo(finalMessageData)
        }
        
        print("Sent final audio chunk \(chunkIndex)")
    }

    private func checkMicrophonePermissionAndSetup(completion: @escaping (Bool) -> Void) {
        let audioSession = AVAudioSession.sharedInstance()
        
        // First check current permission status
        let permissionStatus = audioSession.recordPermission
        print("Watch: Current microphone permission status: \(permissionStatus.rawValue)")
        
        switch permissionStatus {
        case .granted:
            print("Watch: Microphone permission already granted")
            setupAudioSessionAfterPermission(completion: completion)
            
        case .denied:
            print("Watch: Microphone permission denied")
            completion(false)
            
        case .undetermined:
            print("Watch: Microphone permission undetermined, requesting permission")
            // Request permission - this will show the permission dialog
            audioSession.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        print("Watch: Microphone permission granted by user")
                        self?.setupAudioSessionAfterPermission(completion: completion)
                    } else {
                        print("Watch: Microphone permission denied by user")
                        completion(false)
                    }
                }
            }
            
        @unknown default:
            print("Watch: Unknown microphone permission status")
            completion(false)
        }
    }
    
    private func setupAudioSessionAfterPermission(completion: @escaping (Bool) -> Void) {
        let audioSession = AVAudioSession.sharedInstance()
        
        do {
            try audioSession.setCategory(.playAndRecord, 
                                       mode: .default,
                                       options: [.mixWithOthers, .allowBluetooth])
            try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
            print("Watch: Audio session configured successfully for background recording")
            completion(true)
        } catch {
            print("Watch: Audio session setup failed even with permission: \(error.localizedDescription)")
            completion(false)
        }
    }

    func requestMicrophonePermissionOnly() {
        
        let audioSession = AVAudioSession.sharedInstance()
        let permissionStatus = audioSession.recordPermission
        
        switch permissionStatus {
        case .granted:
            print("Watch: Microphone permission already granted")
            session.sendMessage(["method": "microphonePermissionResult", "granted": true], replyHandler: nil)
            
        case .denied:
            print("Watch: Microphone permission denied")
            session.sendMessage(["method": "microphonePermissionResult", "granted": false], replyHandler: nil)
            
        case .undetermined:
            print("Watch: Microphone permission undetermined, requesting permission")
            // Request permission - this will show the permission dialog
            audioSession.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    print("Watch: Microphone permission request result: \(granted)")
                    self?.session.sendMessage([
                        "method": "microphonePermissionResult", 
                        "granted": granted
                    ], replyHandler: nil)
                }
            }
            
        @unknown default:
            print("Watch: Unknown microphone permission status")
            // Send failure result to main app
            session.sendMessage(["method": "microphonePermissionResult", "granted": false], replyHandler: nil)
        }
    }

    private func setupAudioStreaming() {
        print("Setting up audio streaming...")

        do {
            audioEngine = AVAudioEngine()
            inputNode = audioEngine?.inputNode

            let inputFormat = inputNode?.inputFormat(forBus: 0)
            print("Input format: \(String(describing: inputFormat))")
            let hardwareSampleRate = inputFormat?.sampleRate ?? 0
            print("Hardware microphone sample rate: \(hardwareSampleRate)Hz")
            print("Channels: \(inputFormat?.channelCount ?? 0)")

            // Store the detected sample rate
            self.detectedSampleRate = hardwareSampleRate

            guard let inputFormat = inputFormat else {
                print("Failed to get input format")
                return
            }
            self.inputFormat = inputFormat

            // Create target format for 16kHz resampling
            guard let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1) else {
                print("Failed to create target format")
                return
            }
            self.targetFormat = targetFormat

            // Create audio converter for resampling
            guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
                print("Failed to create audio converter")
                return
            }
            self.audioConverter = converter
            print("Audio converter created: \(hardwareSampleRate)Hz -> 16000Hz")

            let bufferSize: AVAudioFrameCount = 512

            inputNode?.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { [weak self] (buffer, time) in
                self?.processAudioBuffer(buffer)
            }

            try audioEngine?.start()
            isStreaming = true
            chunkIndex = 0
            print("Audio streaming started successfully (hardware rate: \(hardwareSampleRate)Hz -> 16kHz resampled)")

        } catch {
            print("Failed to setup audio streaming: \(error)")
            print("Error details: \(error.localizedDescription)")
        }
    }

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        guard isStreaming else { return }

        // Validate buffer
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else {
            print("Buffer has zero frames")
            return
        }

        // Resample audio to 16kHz if converter is available
        let processedBuffer: AVAudioPCMBuffer
        if let converter = audioConverter, let targetFormat = targetFormat {
            let outputFrameCapacity = AVAudioFrameCount(ceil(Double(frameLength) * 16000.0 / detectedSampleRate))
            guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputFrameCapacity) else {
                print("Failed to create output buffer for resampling")
                return
            }

            var error: NSError?
            let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
                outStatus.pointee = .haveData
                return buffer
            }

            converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

            if let error = error {
                print("Audio conversion error: \(error)")
                return
            }

            processedBuffer = outputBuffer
            print("Resampled \(frameLength) frames at \(detectedSampleRate)Hz to \(outputBuffer.frameLength) frames at 16000Hz")
        } else {
            processedBuffer = buffer
            print("Using original buffer without resampling (converter not available)")
        }

        // Convert resampled buffer to 16-bit PCM data
        let channelData = processedBuffer.floatChannelData?[0]

        var pcmData = [Int16]()
        var hasNonZeroData = false

        if let channelData = channelData {
            let processedFrameLength = Int(processedBuffer.frameLength)
            for i in 0..<processedFrameLength {
                let sample = channelData[i]

                if abs(sample) > 0.01 { hasNonZeroData = true }

                let pcmSample = Int16(max(-32768, min(32767, sample * 32767)))
                pcmData.append(pcmSample)
            }
        } else {
            print("No channel data available")
            return
        }

        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        // Buffer audio data for target-duration chunks instead of sending immediately
        bufferAndSendAudioData(byteData)
    }
}

extension WatchAudioRecorderViewModel: WCSessionDelegate {
#if os(iOS)
    public func sessionDidBecomeInactive(_ session: WCSession) { }
    public func sessionDidDeactivate(_ session: WCSession) { }
#endif
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: (any Error)?) {}
    
    func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task {
            guard let method = message["method"] as? String else { return }
            switch method {
            case "startRecording":
                print("Received startRecording message from iOS app")
                self.startRecording()
            case "stopRecording":
                print("Received stopRecording message from iOS app")
                self.stopRecording()
            case "requestMicrophonePermission":
                print("Received requestMicrophonePermission message from iOS app")
                self.requestMicrophonePermissionOnly()
            case "requestBattery":
                print("WatchAudioRecorderViewModel: Received battery request from iPhone")
                BatteryManager.shared.sendBatteryLevel()
            case "requestWatchInfo":
                print("WatchAudioRecorderViewModel: Received watch info request from iPhone")
                BatteryManager.shared.sendWatchInfo()
            default:
                print("Unknown method: \(method)")
            }
        }
    }
    
    func session(_ session: WCSession, didReceiveUserInfo userInfo: [String : Any]) {
        Task {
            guard let method = userInfo["method"] as? String else { return }
            switch method {
            case "requestBattery":
                print("WatchAudioRecorderViewModel: Received background battery request from iPhone")
                BatteryManager.shared.sendBatteryLevel()
            case "requestWatchInfo":
                print("WatchAudioRecorderViewModel: Received background watch info request from iPhone")
                BatteryManager.shared.sendWatchInfo()
            default:
                print("Unknown background method: \(method)")
            }
        }
    }
}


