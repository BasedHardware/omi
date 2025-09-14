//
//  CounterViewModel.swift
//  watchflutter Watch App
//
//  Created by Leandro Pontes Berleze on 23/04/24.
//

import Foundation
import WatchConnectivity
import AVFoundation

@MainActor
class CounterViewModel: NSObject, ObservableObject {
    @Published var count: Int = 0
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
    
    init(session: WCSession = .default) {
        self.session = session
        super.init()
        self.session.delegate = self
        session.activate()
    }
    
    func increment(_ sendMessage: Bool = true) {
        count = count + 1
        if sendMessage {
            session.sendMessage(["method": "increment"], replyHandler: nil)
        }
    }
    
    func decrement(_ sendMessage: Bool = true) {
        count = count - 1
        if sendMessage {
            session.sendMessage(["method": "decrement"], replyHandler: nil)
        }
    }

    func startRecording() {
        guard !isRecording else { return }

        print("Starting audio recording...")
        // Setup audio streaming
        setupAudioStreaming()

        isRecording = true
        session.sendMessage(["method": "startRecording"], replyHandler: nil)
        print("Recording started")
    }

    func stopRecording() {
        guard isRecording else {
            print("stopRecording called but not currently recording")
            return
        }

        print("Stopping audio recording...")
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

        // Send final chunk to indicate end of stream - always 16kHz now
        sendAudioChunk(Data(), chunkIndex: chunkIndex, isLast: true, sampleRate: 16000.0)

        session.sendMessage(["method": "stopRecording"], replyHandler: nil)
        print("Recording stopped and final chunk sent")
    }

    private func sendAudioChunk(_ audioData: Data, chunkIndex: Int, isLast: Bool, sampleRate: Double) {
        let chunkArray = [UInt8](audioData)

        session.sendMessage([
            "method": "sendAudioChunk",
            "audioChunk": audioData,
            "chunkIndex": chunkIndex,
            "isLast": isLast,
            "sampleRate": sampleRate
        ], replyHandler: nil) { error in
            print("Failed to send audio chunk \(chunkIndex): \(error.localizedDescription)")
        }

        if isLast {
            print("Sent final audio chunk \(chunkIndex)")
        } else {
            // Only print every 10th chunk to reduce log spam
            if chunkIndex % 10 == 0 {
                print("Sent audio chunk \(chunkIndex) with \(chunkArray.count) bytes, rate: \(sampleRate)Hz")
            }
        }
    }

    private func setupAudioStreaming() {
        print("Setting up audio streaming...")

        let audioSession = AVAudioSession.sharedInstance()

        do {
            try audioSession.setCategory(.record, mode: .measurement, options: .duckOthers)
            try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
            print("Audio session configured successfully")

            audioEngine = AVAudioEngine()
            inputNode = audioEngine?.inputNode

            let inputFormat = inputNode?.inputFormat(forBus: 0)
            print("Input format: \(String(describing: inputFormat))")
            let hardwareSampleRate = inputFormat?.sampleRate ?? 0
            print("Hardware microphone sample rate: \(hardwareSampleRate)Hz")
            print("Channels: \(inputFormat?.channelCount ?? 0)")

            // Store the detected sample rate
            self.detectedSampleRate = hardwareSampleRate

            // Store the input format for later use
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

            // Use smaller buffer size for better real-time performance
            let bufferSize: AVAudioFrameCount = 512 // Smaller buffer for lower latency

            // Install a tap on the input node to capture audio data
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
            // Calculate expected output buffer size
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
            // Fallback to original buffer if converter not available
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

                // Check if we have actual audio data
                if abs(sample) > 0.01 {
                    hasNonZeroData = true
                }

                // Convert float (-1.0 to 1.0) to 16-bit PCM (-32768 to 32767)
                let pcmSample = Int16(max(-32768, min(32767, sample * 32767)))
                pcmData.append(pcmSample)
            }
        } else {
            print("No channel data available")
            return
        }

        // Convert to bytes (little-endian)
        let byteData = pcmData.withUnsafeBufferPointer { buffer in
            return Data(buffer: buffer)
        }

        // Send chunk to iOS app - always report 16kHz now
        sendAudioChunk(byteData, chunkIndex: chunkIndex, isLast: false, sampleRate: 16000.0)
        chunkIndex += 1

        // Only print every 10th chunk to reduce log spam
        if chunkIndex % 10 == 0 {
            print("Processed audio buffer: \(frameLength) frames (\(detectedSampleRate)Hz) -> \(byteData.count) bytes (16kHz), chunk: \(chunkIndex), hasAudio: \(hasNonZeroData)")
        }
    }

}

extension CounterViewModel: WCSessionDelegate {
#if os(iOS)
    public func sessionDidBecomeInactive(_ session: WCSession) { }
    public func sessionDidDeactivate(_ session: WCSession) { }
#endif
    
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: (any Error)?) {}
    
    // Receive message From AppDelegate.swift that send from iOS devices
    func session(_ session: WCSession, didReceiveMessage message: [String : Any]) {
        Task {
            guard let method = message["method"] as? String else {
                return
            }
            
            switch method {
            case "increment":
                self.increment(false)
            case "decrement":
                self.decrement(false)
            case "setCount":
                self.count = message["data"] as! Int
            default:
                print("None")
            }
        }
    }
    
}
