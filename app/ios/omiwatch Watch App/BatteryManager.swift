import WatchKit
import WatchConnectivity

class BatteryManager: NSObject {
    static let shared = BatteryManager()
    
    private var batteryTimer: Timer?
    private let batteryUpdateInterval: TimeInterval = 180.0 // 3 minutes
    
    private override init() {
        super.init()
        WKInterfaceDevice.current().isBatteryMonitoringEnabled = true
    }
    
    func startBatteryMonitoring() {
        // Send initial battery level
        sendBatteryLevel()
        
        // Set up timer for periodic updates
        batteryTimer = Timer.scheduledTimer(withTimeInterval: batteryUpdateInterval, repeats: true) { [weak self] _ in
            self?.sendBatteryLevel()
        }
    }
    
    func stopBatteryMonitoring() {
        batteryTimer?.invalidate()
        batteryTimer = nil
    }
    
    func sendBatteryLevel() {
        let level = WKInterfaceDevice.current().batteryLevel * 100  // 0.0–100.0
        let state = WKInterfaceDevice.current().batteryState.rawValue
        
        let data: [String: Any] = [
            "method": "batteryUpdate",
            "batteryLevel": level,
            "batteryState": state
        ]
        
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(data, replyHandler: nil, errorHandler: { error in
                // Fallback to transferUserInfo for background delivery
                self.sendBatteryLevelViaTransfer(data)
            })
        } else {
            // Use transferUserInfo when not reachable
            sendBatteryLevelViaTransfer(data)
        }
    }
    
    private func sendBatteryLevelViaTransfer(_ data: [String: Any]) {
        WCSession.default.transferUserInfo(data)
        print("BatteryManager: Sent battery info via transferUserInfo")
    }
    
    func sendWatchInfo() {
        let device = WKInterfaceDevice.current()
        
        let data: [String: Any] = [
            "method": "watchInfoUpdate",
            "name": device.name,
            "model": device.model,
            "systemVersion": device.systemVersion,
            "localizedModel": device.localizedModel
        ]
        
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(data, replyHandler: nil, errorHandler: { error in
                // Fallback to transferUserInfo if sendMessage fails
                self.sendWatchInfoViaTransfer(data)
            })
        } else {
            // Use transferUserInfo when not reachable
            sendWatchInfoViaTransfer(data)
        }
    }
    
    private func sendWatchInfoViaTransfer(_ data: [String: Any]) {
        WCSession.default.transferUserInfo(data)
    }
}
