import Foundation
import Combine
import WatchConnectivity
import AVFoundation

@MainActor
class WatchAudioRecorderViewModel: NSObject, WatchRecorderControlling {
    @Published var isRecording: Bool = false
    @Published private(set) var recordingStartedAt: Date?
    @Published private(set) var pendingRecoverySegments = 0
    @Published private(set) var recoveryError: String?
    private var archive: WatchRecordingStore?
    private var recoveryTimer: Timer?
    private var lastTransferAttempt: [String: TimeInterval] = [:]
    private var recordingGeneration = UUID()
    private var archiveSessionID = ""
    private var isStarting = false
    private var hasInputTap = false
    private var lastCapturedUptime: TimeInterval = 0
    private var captureHealthTimer: Timer?
    private var interruptionObserver: NSObjectProtocol?
    private let permissionRequestOverride: ((@escaping (Bool) -> Void) -> Void)?
    private let activateSessionOverride: (() throws -> Void)?
    private let deactivateSession: () throws -> Void


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
    
    init(
        session: WCSession = .default,
        permissionRequest: ((@escaping (Bool) -> Void) -> Void)? = nil,
        activateSession: (() throws -> Void)? = nil,
        deactivateSession: @escaping () throws -> Void = {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
    ) {
        self.session = session
        self.permissionRequestOverride = permissionRequest
        self.activateSessionOverride = activateSession
        self.deactivateSession = deactivateSession
        super.init()
        self.session.delegate = self
        let directory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("OmiWatchRecordings", isDirectory: true)
        do { archive = try WatchRecordingStore(directory: directory) }
        catch { recoveryError = String(localized: "watch.recovery.storageError") }
        session.activate()
        captureHealthTimer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.checkCaptureHealth() }
        }
        recoveryTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.drainRecoveryTransfers() }
        }
        
        BatteryManager.shared.startBatteryMonitoring()
        BatteryManager.shared.sendWatchInfo()
    }

    func startRecording() {
        guard !isRecording, !isStarting else { return }
        isStarting = true
        let attempt = UUID()
        recordingGeneration = attempt

        // Permission alone never activates the mic: first validate the admitted attempt and owner.
        checkMicrophonePermission { [weak self] success in
            guard let self, self.isStarting, self.recordingGeneration == attempt else { return }
            defer {
                self.isStarting = false
                if !self.isRecording {
                    self.releaseCaptureResources()
                    do { try self.archive?.finish() }
                    catch { self.recoveryError = String(localized: "watch.recovery.storageError") }
                    self.drainRecoveryTransfers()
                }
            }

            if success {
                let now = Date()
                let owner = UserDefaults.standard.string(forKey: "omiOwnerUID")
                    ?? self.session.receivedApplicationContext["omiOwnerUID"] as? String ?? ""
                guard !owner.isEmpty else {
                    self.recoveryError = String(localized: "watch.recovery.openPhone")
                    return
                }
                do {
                    guard let archive = self.archive else { throw WatchRecordingError.storageFull }
                    self.archiveSessionID = try archive.begin(ownerUID: owner, startedAt: CheckedIntegerConversion.epochMs(now) / 1000)
                    do { try self.activateAudioSession() }
                    catch {
                        self.recoveryError = String(localized: "watch.recovery.captureError")
                        return
                    }
                    guard self.setupAudioStreaming() else {
                        self.recoveryError = String(localized: "watch.recovery.captureError")
                        return
                    }
                    self.recoveryError = nil
                    self.recordingStartedAt = now
                    self.lastCapturedUptime = ProcessInfo.processInfo.systemUptime
                    self.isRecording = true
                    self.interruptionObserver = NotificationCenter.default.addObserver(
                        forName: AVAudioSession.interruptionNotification, object: nil, queue: nil
                    ) { [weak self] notification in
                        guard let value = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                              AVAudioSession.InterruptionType(rawValue: value) == .began else { return }
                        Task { @MainActor in
                            guard let self, self.recordingGeneration == attempt else { return }
                            self.stopRecording()
                            self.recoveryError = String(localized: "watch.recovery.captureStopped")
                        }
                    }
                    self.session.sendMessage(["method": "startRecording"], replyHandler: nil)
                } catch {
                    self.recoveryError = String(localized: "watch.recovery.storageError")
                }
            } else {
                self.session.sendMessage(["method": "recordingError", "error": "Microphone permission denied"], replyHandler: nil)
            }
        }
    }

    func stopRecording() {
        guard isRecording else {
            isStarting = false
            recordingGeneration = UUID()
            releaseCaptureResources()
            return
        }

        isRecording = false
        if let interruptionObserver { NotificationCenter.default.removeObserver(interruptionObserver) }
        interruptionObserver = nil
        recordingStartedAt = nil
        isStreaming = false
        recordingGeneration = UUID()

        releaseCaptureResources()

        // Send any remaining buffered data and final chunk
        sendFinalAudioChunk()
        
        // Reset buffer state
        chunkBuffer = Data()
        bufferStartTime = nil

        do { try archive?.finish() }
        catch { recoveryError = String(localized: "watch.recovery.storageError") }
        drainRecoveryTransfers()
        session.sendMessage(["method": "stopRecording"], replyHandler: nil)
    }

    /// End microphone ownership independently of pending file transfers. This
    /// also runs after cancelled permission requests and failed engine setup.
    private func releaseCaptureResources() {
        if hasInputTap { inputNode?.removeTap(onBus: 0) }
        hasInputTap = false
        audioEngine?.stop()
        inputNode = nil
        audioEngine = nil
        inputFormat = nil
        audioConverter = nil
        targetFormat = nil
        detectedSampleRate = 0
        isStreaming = false
        do {
            try deactivateSession()
        } catch {
            print("Watch microphone session deactivation failed: \(error)")
        }
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
        guard let startTime = bufferStartTime else { return }
        let elapsedTime = currentTime.timeIntervalSince(startTime)
        
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
                // Fallback to transferUserInfo for background reliability
                self.session.transferUserInfo(messageData)
            }
        } else {
            // Use transferUserInfo when not reachable (background/screen off)
            session.transferUserInfo(messageData)
        }
        
        chunkIndex += 1
    }
    
    private func sendFinalAudioChunk() {
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
            }
        } else {
            session.transferUserInfo(finalMessageData)
        }
        
    }

    private func checkMicrophonePermission(completion: @escaping (Bool) -> Void) {
        if let permissionRequestOverride {
            permissionRequestOverride(completion)
            return
        }
        let audioSession = AVAudioSession.sharedInstance()
        
        let permissionStatus = audioSession.recordPermission
        
        switch permissionStatus {
        case .granted:
            completion(true)
            
        case .denied:
            completion(false)
            
        case .undetermined:
            // Request permission
            audioSession.requestRecordPermission { granted in
                DispatchQueue.main.async {
                    completion(granted)
                }
            }
            
        @unknown default:
            completion(false)
        }
    }
    
    private func activateAudioSession() throws {
        if let activateSessionOverride {
            try activateSessionOverride()
            return
        }
        let audioSession = AVAudioSession.sharedInstance()
        try audioSession.setCategory(.playAndRecord, mode: .default, options: [.mixWithOthers, .allowBluetooth])
        try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
    }

    func requestMicrophonePermissionOnly() {
        
        let audioSession = AVAudioSession.sharedInstance()
        let permissionStatus = audioSession.recordPermission
        
        switch permissionStatus {
        case .granted:
            session.sendMessage(["method": "microphonePermissionResult", "granted": true], replyHandler: nil)
            
        case .denied:
            session.sendMessage(["method": "microphonePermissionResult", "granted": false], replyHandler: nil)
            
        case .undetermined:
            // Request permission - this will show the permission dialog
            audioSession.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    self?.session.sendMessage([
                        "method": "microphonePermissionResult", 
                        "granted": granted
                    ], replyHandler: nil)
                }
            }
            
        @unknown default:
            // Send failure result to main app
            session.sendMessage(["method": "microphonePermissionResult", "granted": false], replyHandler: nil)
        }
    }

    private func setupAudioStreaming() -> Bool {

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

            guard let inputFormat = inputFormat, hardwareSampleRate.isFinite, hardwareSampleRate > 0 else {
                print("Failed to get input format")
                return false
            }
            self.inputFormat = inputFormat

            // Create target format for 16kHz resampling
            guard let targetFormat = AVAudioFormat(standardFormatWithSampleRate: 16000.0, channels: 1) else {
                print("Failed to create target format")
                return false
            }
            self.targetFormat = targetFormat

            // Create audio converter for resampling
            guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
                print("Failed to create audio converter")
                return false
            }
            self.audioConverter = converter

            let bufferSize: AVAudioFrameCount = 512

            let generation = recordingGeneration
            let archive = self.archive
            let archiveSession = self.archiveSessionID
            inputNode?.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { [weak self] (buffer, time) in
                guard let bytes = Self.convertAudioBuffer(buffer, converter: converter, targetFormat: targetFormat,
                                                          detectedSampleRate: hardwareSampleRate) else { return }
                do { try archive?.append(bytes, sessionID: archiveSession) }
                catch {
                    Task { @MainActor in
                        guard let self, self.recordingGeneration == generation else { return }
                        self.stopRecording()
                        self.recoveryError = String(localized: "watch.recovery.storageError")
                    }
                    return
                }
                Task { @MainActor in
                    guard let self, self.isStreaming, self.recordingGeneration == generation else { return }
                    self.lastCapturedUptime = ProcessInfo.processInfo.systemUptime
                    self.bufferAndSendAudioData(bytes)
                }
            }

            hasInputTap = true
            try audioEngine?.start()
            isStreaming = true
            chunkIndex = 0
            return true

        } catch {
            print("Error details: \(error.localizedDescription)")
            return false
        }
    }

    nonisolated private static func convertAudioBuffer(_ buffer: AVAudioPCMBuffer, converter: AVAudioConverter?,
        targetFormat: AVAudioFormat?, detectedSampleRate: Double) -> Data? {

        // Validate buffer
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else {
            print("Buffer has zero frames")
            return nil
        }

        // Resample audio to 16kHz
        let processedBuffer: AVAudioPCMBuffer
        if let converter, let targetFormat {
            let outputFrameCapacity = AVAudioFrameCount(ceil(Double(frameLength) * 16000.0 / detectedSampleRate))
            guard let outputBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: outputFrameCapacity) else {
                print("Failed to create output buffer for resampling")
                return nil
            }

            var error: NSError?
            var suppliedInput = false
            let inputBlock: AVAudioConverterInputBlock = { inNumPackets, outStatus in
                guard !suppliedInput else { outStatus.pointee = .noDataNow; return nil }
                suppliedInput = true
                outStatus.pointee = .haveData
                return buffer
            }

            converter.convert(to: outputBuffer, error: &error, withInputFrom: inputBlock)

            if let error = error {
                print("Audio conversion error: \(error)")
                return nil
            }

            processedBuffer = outputBuffer
        } else {
            processedBuffer = buffer
        }

        // Convert resampled buffer to 16-bit PCM data
        let channelData = processedBuffer.floatChannelData?[0]

        var pcmData = [Int16]()

        if let channelData = channelData {
            let processedFrameLength = Int(processedBuffer.frameLength)
            for i in 0..<processedFrameLength {
                let sample = channelData[i]


                let pcmSample = Int16(max(-32768, min(32767, sample * 32767)))
                pcmData.append(pcmSample)
            }
        } else {
            print("No channel data available")
            return nil
        }

        guard !pcmData.isEmpty else { return nil }
        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        return byteData
    }

    private func checkCaptureHealth() {
        guard isRecording, ProcessInfo.processInfo.systemUptime - lastCapturedUptime > 10 else { return }
        stopRecording()
        recoveryError = String(localized: "watch.recovery.captureStopped")
    }

    func retryRecoveryTransfers() {
        checkCaptureHealth()
        lastTransferAttempt.removeAll()
        if session.activationState == .notActivated { session.activate() }
        drainRecoveryTransfers()
    }

    private func drainRecoveryTransfers() {
        guard let archive else { return }
        do {
            pendingRecoverySegments = try archive.pending().count
            if archive.recoveryFailures > 0, !isRecording {
                recoveryError = String(localized: "watch.recovery.savedAudioError")
            }
            guard session.activationState == .activated else { return }
            let inFlight = Set(session.outstandingFileTransfers.map { $0.file.fileURL.lastPathComponent })
            try archive.pruneAcknowledged(excluding: inFlight)
            let files = try archive.pending()
            pendingRecoverySegments = files.count
            lastTransferAttempt = lastTransferAttempt.filter { entry in files.contains { $0.0.lastPathComponent == entry.key } }
            let owner = UserDefaults.standard.string(forKey: "omiOwnerUID") ?? ""
            let uptime = ProcessInfo.processInfo.systemUptime
            let candidates = WatchRecoveryTransferQueue.candidates(files, ownerUID: owner,
                inFlight: inFlight, attempts: lastTransferAttempt, uptime: uptime)
            for (url, metadata) in candidates {
                session.transferFile(url, metadata: ["method": "watchRecordingFile", "recording": try JSONEncoder().encode(metadata)])
                lastTransferAttempt[url.lastPathComponent] = uptime
            }
        } catch {
            recoveryError = String(localized: "watch.recovery.storageError")
        }
    }

    private func receiveRecoveryReceipt(_ message: [String: Any]) {
        guard let name = message["fileName"] as? String, let digest = message["digest"] as? String else { return }
        do {
            try archive?.acknowledge(fileName: name, digest: digest)
            drainRecoveryTransfers()
        } catch { recoveryError = String(localized: "watch.recovery.storageError") }
    }
}

extension WatchAudioRecorderViewModel: WCSessionDelegate {
#if os(iOS)
    nonisolated public func sessionDidBecomeInactive(_ session: WCSession) { }
    nonisolated public func sessionDidDeactivate(_ session: WCSession) { }
#endif
    nonisolated func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: (any Error)?) {
        Task { @MainActor in drainRecoveryTransfers() }
    }

    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        Task { @MainActor in drainRecoveryTransfers() }
    }

    nonisolated func session(_ session: WCSession, didFinish fileTransfer: WCSessionFileTransfer, error: Error?) {
        // Keep the source until a matching durable iPhone receipt, including OS-success.
        Task { @MainActor in drainRecoveryTransfers() }
    }

    nonisolated func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        Task { @MainActor in
            if let owner = applicationContext["omiOwnerUID"] as? String {
                try? SafeDefaults.store(.string(owner), forKey: "omiOwnerUID")
            }
            if let method = applicationContext["method"] as? String {
                if method == "stopRecording" { stopRecording() }
                if method == "startRecording" { startRecording() }
            }
            drainRecoveryTransfers()
        }
    }
    
    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task { @MainActor in
            guard let method = message["method"] as? String else { return }
            switch method {
            case "watchRecordingReceipt":
                self.receiveRecoveryReceipt(message)
            case "startRecording":
                if let owner = message["omiOwnerUID"] as? String {
                    try? SafeDefaults.store(.string(owner), forKey: "omiOwnerUID")
                }
                self.startRecording()
            case "stopRecording":
                self.stopRecording()
            case "requestMicrophonePermission":
                self.requestMicrophonePermissionOnly()
            case "requestBattery":
                BatteryManager.shared.sendBatteryLevel()
            case "requestWatchInfo":
                BatteryManager.shared.sendWatchInfo()
            default:
                print("Unknown method: \(method)")
            }
        }
    }
    
    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String : Any]) {
        Task { @MainActor in
            guard let method = userInfo["method"] as? String else { return }
            switch method {
            case "watchRecordingReceipt":
                self.receiveRecoveryReceipt(userInfo)
            case "stopRecording":
                self.stopRecording()
            case "requestBattery":
                BatteryManager.shared.sendBatteryLevel()
            case "requestWatchInfo":
                BatteryManager.shared.sendWatchInfo()
            default:
                print("Unknown background method: \(method)")
            }
        }
    }
}
