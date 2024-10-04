//
//  FriendManager.swift
//  scribehardware
//
//  Created by Ash Bhat on 9/28/24.
//

import UIKit
import CoreBluetooth
import Speech
import AVFoundation
import SwiftWhisper
import AudioKit

class FriendManager {
    
    static var singleton = FriendManager()
   
    var bluetoothScanner: BluetoothScanner!
    var friendDevice: Friend?  // Retain Friend object
    var bleManager: BLEManager?  // Retain BLEManager
    var audioPlayer: AVAudioPlayer?

    var deviceCompletion: ((Friend?, Error?) -> Void)?
    var transcriptCompletion: ((String?) -> Void)?
    
    var connectionCompletion: ((Bool) -> Void)?
    let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))

    let whisper: Whisper?
    
    var transcriptTimer: Timer?
    var audioFileTimer: Timer?

    init() {
        // let modelURL = Bundle.module.url(forResource: "ggml-tiny.en", withExtension: "bin")!
        // whisper = Whisper(fromFileURL: modelURL)
        whisper = nil
        bluetoothScanner = BluetoothScanner()
        bluetoothScanner.delegate = self
    }
    
    @objc func transcribeAudio(url: URL, completion: @escaping (String?, Error?) ->Void) {
        self.extractTextFromAudio(url) { result, error in
            if let result = result {
                completion(result, error)
            }
            else {
                print("error")
                completion(result, error)
            }
        }
    }
    
    func extractTextFromAudio(_ audioURL: URL, completionHandler: @escaping (String?, Error?) ->Void) {
        
        let originalStderr = dup(fileno(stderr))
        let nullDevice = open("/dev/null", O_WRONLY)
        dup2(nullDevice, fileno(stderr))
        close(nullDevice)
        
        convertAudioFileToPCMArray(fileURL: audioURL) { result in
            guard let whisper = self.whisper else {
                completionHandler(nil, nil)
                return
            }
            switch result {
                case .success(let success):
                    Task {
                        do {
                            let segments = try await whisper.transcribe(audioFrames: success)
                            completionHandler(segments.map(\.text).joined(), nil)
                        } catch {
                            completionHandler(nil, error)
                        }
                    }
                case .failure(_):
                    completionHandler(nil, nil)
            }
            
            // Restore stdout after function execution
            // Restore the original stderr
            fflush(stderr)
            dup2(originalStderr, fileno(stderr))
            close(originalStderr)
        }
    }
    
    func getLiveTranscription(device: Friend, completion: @escaping (String?) -> Void) {
        transcriptCompletion = completion
        transcriptTimer?.invalidate()
        transcriptTimer = Timer.scheduledTimer(withTimeInterval: 8.0, repeats: true, block: { timer in
            if let recording = device.recording {
                let recordingFileURL = recording.fileURL
                device.resetRecording()
                if self.fileHasData(url: recordingFileURL) {
                    print("file has data")
                }
                else {
                    print("no data in file")
                }
                
                self.transcribeAudio(url: recordingFileURL, completion: { result, error in
                    completion(result)
                })
            }
            else {
                completion(nil)
            }
        })
    }
    
    func getRawAudio(device: Friend, completion: @escaping (URL?) -> Void) {
//        transcriptCompletion = completion
        audioFileTimer?.invalidate()
        audioFileTimer = Timer.scheduledTimer(withTimeInterval: 8.0, repeats: true, block: { timer in
            if let recording = device.recording {
                let recordingFileURL = recording.fileURL
                device.resetRecording()
                completion(recordingFileURL)
            }
            else {
                completion(nil)
            }
        })
    }
    
    func getCurrentTranscription(completion: @escaping (String?) -> Void) {
        if let friendDevice = self.friendDevice, let recording = friendDevice.recording {
            let recordingFileURL = recording.fileURL
            self.friendDevice?.resetRecording()
            if self.fileHasData(url: recordingFileURL) {
                print("file has data")
            }
            else {
                print("no data in file")
            }
            
            self.transcribeAudio(url: recordingFileURL, completion: { result, error in
                completion(result)
            })
        }
        else {
            completion(nil)
        }
    }
    
    func fileHasData(url: URL) -> Bool {
        do {
            let fileAttributes = try FileManager.default.attributesOfItem(atPath: url.path)
            if let fileSize = fileAttributes[FileAttributeKey.size] as? UInt64 {
                return fileSize > 0
            }
        } catch {
            print("Error checking file size: \(error.localizedDescription)")
        }
        return false
    }
    
    func replayAudio(from url: URL) {
        do {
            // Initialize the audio player with the file URL
            audioPlayer = try AVAudioPlayer(contentsOf: url)
            audioPlayer?.prepareToPlay()
            audioPlayer?.play()
        } catch let error {
            print("Failed to play audio: \(error.localizedDescription)")
        }
    }
    
//    func getFriendDeviceOnConnection(completion: @escaping(Friend?, Error?) -> Void) {
//        if friendDevice != nil {
//            completion(self.friendDevice, nil)
//        }
//        else {
//            self.deviceCompletion = completion
//        }
//    }

    func connectionStatus(completion: @escaping(Bool) -> Void) {
        self.connectionCompletion = completion
    }
    
    func startScan() {
        self.bluetoothScanner.centralManager.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }
    
    func startRecordingWhenReady() {
        switch self.friendDevice?.status {
            case .ready:
                let uuidString = UUID().uuidString
                let recording = Recording(filename: "\(uuidString).wav")  // Your custom recording handler
                self.friendDevice!.start(recording: recording)
            
//                startRealTimeTranscription(from: recording.fileURL)
            case .error(_):
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: {
                    self.startRecordingWhenReady()
                })
            case .none:
                print("should not reach here")
        }
    }
    
    func startRecordingWhenReady(device: Friend) {
        switch device.status {
            case .ready:
                let uuidString = UUID().uuidString
                let recording = Recording(filename: "\(uuidString).wav")  // Your custom recording handler
                device.start(recording: recording)
            case .error(_):
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: {
                    self.startRecordingWhenReady(device: device)
                })
        }
    }
    
    
    func startRealTimeTranscription(from url: URL) {
        guard let recognizer = recognizer else {
            print("Speech recognizer is not available")
            return
        }
        
        let request = SFSpeechURLRecognitionRequest(url: url)
        
        request.requiresOnDeviceRecognition = false // Change this to true if you want on-device recognition
        request.taskHint = .dictation  // Hints that this is conversational speech
        
        recognizer.recognitionTask(with: request) { (result, error) in
            if let error = error {
                print("Error transcribing audio: \(error.localizedDescription)")
                // Handle error
            } else if let result = result {
                // Print the transcribed text in real time
                print("Real-time Transcription: \(result.bestTranscription.formattedString)")
            }
        }
        
        if friendDevice?.isRecording == true, let fileURL = friendDevice?.recording?.fileURL {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: {
                self.startRealTimeTranscription(from: fileURL)
            })
        }
        
    }
    
    func transcribeAudioFile(url: URL, completion: @escaping (String?) -> Void) {
        // Create a recognizer for the user's current locale
        
        let request = SFSpeechURLRecognitionRequest(url: url)
        
        request.requiresOnDeviceRecognition = false // Change this to true if you want on-device recognition
        request.taskHint = .dictation  // Hints that this is conversational speech

        // Check if the recognizer is available
        guard recognizer?.isAvailable == true else {
            completion(nil)
            return
        }

        // Perform the recognition
        recognizer?.recognitionTask(with: request) { (result, error) in
            if let error = error {
                print("Error transcribing audio: \(error.localizedDescription)")
                completion(nil)
            } else if let result = result, result.isFinal {
                // Return the transcribed text
                completion(result.bestTranscription.formattedString)
            }
        }
    }
}

extension FriendManager: BluetoothScannerDelegate {
    func deviceFound(device: CBPeripheral) {
        if device.name == "Friend" {
            print("found friend device")
            WearableDeviceRegistry.shared.registerDevice(wearable: Friend.self)
            self.bleManager = BLEManager(deviceRegistry: WearableDeviceRegistry.shared)
            self.bleManager?.delegate = self
            let friend_device = Friend(bleManager: bleManager!, name: "Friend")
            friend_device.id = device.identifier
            self.deviceCompletion?(friend_device, nil)
        }
    }
    
    func connectToDevice(device: Friend) {
        let deviceUUID = device.id
        bleManager!.reconnect(to: deviceUUID)
        self.connectionCompletion?(true)
        self.startRecordingWhenReady(device: device)
    }
}

extension FriendManager: BLEManagerDelegate {
    func lostConnection() {
        connectionCompletion?(false)
    }
}

extension FriendManager {
    func convertAudioFileToPCMArray(fileURL: URL, completionHandler: @escaping (Result<[Float], Error>) -> Void) {
        var options = FormatConverter.Options()
        options.format = .wav
        options.sampleRate = 16000
        options.bitDepth = 16
        options.channels = 1
        options.isInterleaved = false

        let tempURL = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString)
        let converter = FormatConverter(inputURL: fileURL, outputURL: tempURL, options: options)
        converter.start { error in
            if let error {
                completionHandler(.failure(error))
                return
            }

            let data = try! Data(contentsOf: tempURL) // Handle error here

            let floats = stride(from: 44, to: data.count, by: 2).map {
                return data[$0..<$0 + 2].withUnsafeBytes {
                    let short = Int16(littleEndian: $0.load(as: Int16.self))
                    return max(-1.0, min(Float(short) / 32767.0, 1.0))
                }
            }

            try? FileManager.default.removeItem(at: tempURL)

            completionHandler(.success(floats))
        }
    }

}

protocol BluetoothScannerDelegate: AnyObject {
    func deviceFound(device: CBPeripheral)
}

class BluetoothScanner: NSObject, CBCentralManagerDelegate {
    weak var delegate: BluetoothScannerDelegate?
    var centralManager: CBCentralManager!
    
    override init() {
        super.init()
        // Initialize CBCentralManager with self as the delegate
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }

    // This is called when the central manager's state is updated (e.g., Bluetooth is turned on/off)
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            // Bluetooth is powered on and available, you can start scanning
            print("ready to start scan")
            centralManager.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        case .poweredOff:
            print("Bluetooth is off.")
        case .resetting, .unauthorized, .unknown, .unsupported:
            print("Bluetooth not available.")
        @unknown default:
            print("Unknown state.")
        }
    }

    // This is called when a new peripheral (device) is discovered during scanning
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        if let name = peripheral.name, name == "Friend" {
            self.delegate?.deviceFound(device: peripheral)
        }
    }
}
