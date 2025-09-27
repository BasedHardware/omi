import Foundation
import WatchConnectivity
import AVFoundation
import Flutter

class RecorderHostApiImpl: WatchRecorderHostAPI {
    let session: WCSession
    weak var flutterWatchAPI: WatchRecorderFlutterAPI?

    init(session: WCSession = .default, flutterWatchAPI: WatchRecorderFlutterAPI? = nil) {
        self.session = session
        self.flutterWatchAPI = flutterWatchAPI
    }

    func startRecording() {

        if session.isReachable {
            session.sendMessage(["method": "startRecording"], replyHandler: nil, errorHandler: { error in
                try? self.session.updateApplicationContext(["method": "startRecording"])
            })
        } else {
            try? session.updateApplicationContext(["method": "startRecording"])
        }
    }

    func stopRecording() {

        if session.isReachable {
            session.sendMessage(["method": "stopRecording"], replyHandler: nil, errorHandler: { error in
                try? self.session.updateApplicationContext(["method": "stopRecording"])
            })
        } else {
            try? session.updateApplicationContext(["method": "stopRecording"])
        }
    }

    func sendAudioData(audioData: FlutterStandardTypedData) {
        let data = audioData.data as Data
        session.sendMessage(["method": "sendAudioData", "audioData": data], replyHandler: nil, errorHandler: nil)
    }

    func sendAudioChunk(audioChunk: FlutterStandardTypedData, chunkIndex: Int64, isLast: Bool, sampleRate: Double) {
        let data = audioChunk.data as Data
        session.sendMessage([
            "method": "sendAudioChunk",
            "audioChunk": data,
            "chunkIndex": chunkIndex,
            "isLast": isLast,
            "sampleRate": sampleRate
        ], replyHandler: nil, errorHandler: nil)
    }

    func isWatchPaired() -> Bool { session.isPaired }
    func isWatchReachable() -> Bool { session.isReachable }
    func isWatchSessionSupported() -> Bool { WCSession.isSupported() }
    func isWatchAppInstalled() -> Bool { session.isWatchAppInstalled }

    func requestWatchMicrophonePermission() {
        if session.isReachable {
            session.sendMessage(["method": "requestMicrophonePermission"], replyHandler: nil, errorHandler: { error in
                try? self.session.updateApplicationContext(["method": "requestMicrophonePermission"])
            })
        } else {
            try? session.updateApplicationContext(["method": "requestMicrophonePermission"])
        }
    }

    func requestMainAppMicrophonePermission() {
        let audioSession = AVAudioSession.sharedInstance()
        let permissionStatus = audioSession.recordPermission

        switch permissionStatus {
        case .granted:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: true) { _ in
                }
            }
        case .denied:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: false) { _ in
                }
            }
        case .undetermined:
            audioSession.requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    self?.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: granted) { _ in
                    }
                }
            }
        @unknown default:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: false) { _ in
                }
            }
        }
    }

    func checkMainAppMicrophonePermission() -> Bool {
        let audioSession = AVAudioSession.sharedInstance()
        let hasPermission = audioSession.recordPermission == .granted
        return hasPermission
    }
    
    func getWatchBatteryLevel() -> Double {
        let batteryLevel = UserDefaults.standard.double(forKey: "watch_battery_level")
        return batteryLevel
    }
    
    func getWatchBatteryState() -> Int64 {
        let batteryState = UserDefaults.standard.integer(forKey: "watch_battery_state")
        return Int64(batteryState)
    }
    
    func requestWatchBatteryUpdate() {
        
        if session.isReachable {
            session.sendMessage(["method": "requestBattery"], replyHandler: nil, errorHandler: { error in
                // Fallback for background/unreachable scenarios
                self.session.transferUserInfo(["method": "requestBattery"])
            })
        } else {
            session.transferUserInfo(["method": "requestBattery"])
        }
    }
    
    func getWatchInfo() -> [String: String] {
        
        // Get cached watch info from UserDefaults (updated by watch messages)
        let name = UserDefaults.standard.string(forKey: "watch_device_name") ?? "Apple Watch"
        let model = UserDefaults.standard.string(forKey: "watch_device_model") ?? "Unknown"
        let systemVersion = UserDefaults.standard.string(forKey: "watch_system_version") ?? "Unknown"
        let localizedModel = UserDefaults.standard.string(forKey: "watch_localized_model") ?? "Unknown"
        
        let deviceInfo: [String: String] = [
            "name": name,
            "model": model,
            "systemVersion": systemVersion,
            "localizedModel": localizedModel
        ]
        
        // Also request fresh info from watch
        if session.isReachable {
            session.sendMessage(["method": "requestWatchInfo"], replyHandler: nil, errorHandler: { error in
                // Fallback for background/unreachable scenarios
                self.session.transferUserInfo(["method": "requestWatchInfo"])
            })
        } else {
            session.transferUserInfo(["method": "requestWatchInfo"])
        }
        
        return deviceInfo
    }
}


