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
            print("Host API: Sending startRecording via sendMessage")
            session.sendMessage(["method": "startRecording"], replyHandler: nil, errorHandler: { error in
                print("Host API: sendMessage failed, using fallback: \(error)")
                try? self.session.updateApplicationContext(["method": "startRecording"])
            })
        } else {
            print("Host API: Session not reachable, using updateApplicationContext")
            try? session.updateApplicationContext(["method": "startRecording"])
        }
    }

    func stopRecording() {
        print("Host API: stopRecording called")

        if session.isReachable {
            print("Host API: Sending stopRecording via sendMessage")
            session.sendMessage(["method": "stopRecording"], replyHandler: nil, errorHandler: { error in
                print("Host API: sendMessage failed, using fallback: \(error)")
                try? self.session.updateApplicationContext(["method": "stopRecording"])
            })
        } else {
            print("Host API: Session not reachable, using updateApplicationContext")
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
        print("Host API: requestWatchMicrophonePermission called")
        if session.isReachable {
            print("Host API: Sending requestMicrophonePermission via sendMessage")
            session.sendMessage(["method": "requestMicrophonePermission"], replyHandler: nil, errorHandler: { error in
                print("Host API: sendMessage failed for requestMicrophonePermission: \(error)")
                try? self.session.updateApplicationContext(["method": "requestMicrophonePermission"])
            })
        } else {
            print("Host API: Session not reachable, using updateApplicationContext for requestMicrophonePermission")
            try? session.updateApplicationContext(["method": "requestMicrophonePermission"])
        }
    }

    func requestMainAppMicrophonePermission() {
        print("Host API: requestMainAppMicrophonePermission called")
        let audioSession = AVAudioSession.sharedInstance()
        let permissionStatus = audioSession.recordPermission
        print("Host API: Current microphone permission status: \(permissionStatus.rawValue)")

        switch permissionStatus {
        case .granted:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: true) { _ in
                    print("Host API: Permission result sent to Flutter - Success")
                }
            }
        case .denied:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: false) { _ in
                    print("Host API: Permission result sent to Flutter - Success")
                }
            }
        case .undetermined:
            audioSession.requestRecordPermission { [weak self] granted in
                print("Host API: Microphone permission request result: \(granted)")
                DispatchQueue.main.async {
                    self?.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: granted) { _ in
                        print("Host API: Permission result sent to Flutter - Success")
                    }
                }
            }
        @unknown default:
            DispatchQueue.main.async {
                self.flutterWatchAPI?.onMainAppMicrophonePermissionResult(granted: false) { _ in
                    print("Host API: Permission result sent to Flutter - Success")
                }
            }
        }
    }

    func checkMainAppMicrophonePermission() -> Bool {
        let audioSession = AVAudioSession.sharedInstance()
        let hasPermission = audioSession.recordPermission == .granted
        print("Host API: checkMainAppMicrophonePermission result: \(hasPermission)")
        return hasPermission
    }
    
    func getWatchBatteryLevel() -> Double {
        let batteryLevel = UserDefaults.standard.double(forKey: "watch_battery_level")
        print("Host API: getWatchBatteryLevel result: \(batteryLevel)")
        return batteryLevel
    }
    
    func getWatchBatteryState() -> Int64 {
        let batteryState = UserDefaults.standard.integer(forKey: "watch_battery_state")
        print("Host API: getWatchBatteryState result: \(batteryState)")
        return Int64(batteryState)
    }
    
    func requestWatchBatteryUpdate() {
        print("Host API: requestWatchBatteryUpdate called")
        
        if session.isReachable {
            print("Host API: Sending battery request via sendMessage")
            session.sendMessage(["method": "requestBattery"], replyHandler: nil, errorHandler: { error in
                print("Host API: sendMessage failed for battery request: \(error)")
                // Fallback for background/unreachable scenarios
                self.session.transferUserInfo(["method": "requestBattery"])
            })
        } else {
            print("Host API: Session not reachable, using transferUserInfo for battery request")
            session.transferUserInfo(["method": "requestBattery"])
        }
    }
    
    func getWatchInfo() -> [String: String] {
        print("Host API: getWatchInfo called - requesting from watch")
        
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
            print("Host API: Sending watch info request via sendMessage")
            session.sendMessage(["method": "requestWatchInfo"], replyHandler: nil, errorHandler: { error in
                print("Host API: sendMessage failed for watch info request: \(error)")
                // Fallback for background/unreachable scenarios
                self.session.transferUserInfo(["method": "requestWatchInfo"])
            })
        } else {
            print("Host API: Session not reachable, using transferUserInfo for watch info request")
            session.transferUserInfo(["method": "requestWatchInfo"])
        }
        
        print("Host API: getWatchInfo result: \(deviceInfo)")
        return deviceInfo
    }
}


