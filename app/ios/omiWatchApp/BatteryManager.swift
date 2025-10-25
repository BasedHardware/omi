import WatchKit
import WatchConnectivity
import os.log

/// Enhanced Battery Manager for watchOS 26
/// Provides battery monitoring with improved reliability and logging
class BatteryManager: NSObject {
    static let shared = BatteryManager()

    private var batteryTimer: Timer?
    private let batteryUpdateInterval: TimeInterval = 180.0 // 3 minutes
    private let logger = Logger(subsystem: "com.omi.watchapp", category: "BatteryManager")

    // Track last sent values to avoid redundant updates
    private var lastSentBatteryLevel: Float = -1
    private var lastSentBatteryState: Int = -1

    private override init() {
        super.init()
        WKInterfaceDevice.current().isBatteryMonitoringEnabled = true
        logger.info("BatteryManager initialized")
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
    
    func sendBatteryLevel(force: Bool = false) {
        let level = WKInterfaceDevice.current().batteryLevel * 100  // 0.0–100.0
        let state = WKInterfaceDevice.current().batteryState.rawValue

        // Only send if battery state changed significantly or forced
        if !force &&
            abs(level - lastSentBatteryLevel) < 1.0 &&
            state == lastSentBatteryState {
            logger.debug("Battery level unchanged, skipping update")
            return
        }

        lastSentBatteryLevel = level
        lastSentBatteryState = state

        let data: [String: Any] = [
            "method": "batteryUpdate",
            "batteryLevel": level,
            "batteryState": state,
            "timestamp": Date().timeIntervalSince1970
        ]

        logger.info("Sending battery update: \(level)%, state: \(state)")
        sendMessageWithFallback(data)
    }

    private func sendMessageWithFallback(_ message: [String: Any]) {
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(message, replyHandler: nil, errorHandler: { error in
                self.logger.warning("Battery message failed, using transferUserInfo: \(error.localizedDescription)")
                self.sendBatteryLevelViaTransfer(message)
            })
        } else {
            logger.debug("Session not reachable, using transferUserInfo")
            sendBatteryLevelViaTransfer(message)
        }
    }

    private func sendBatteryLevelViaTransfer(_ data: [String: Any]) {
        WCSession.default.transferUserInfo(data)
        logger.info("Battery info sent via transferUserInfo")
    }
    
    func sendWatchInfo() {
        let device = WKInterfaceDevice.current()

        let data: [String: Any] = [
            "method": "watchInfoUpdate",
            "name": device.name,
            "model": device.model,
            "systemVersion": device.systemVersion,
            "localizedModel": device.localizedModel,
            "screenBounds": [
                "width": WKInterfaceDevice.current().screenBounds.width,
                "height": WKInterfaceDevice.current().screenBounds.height
            ],
            "timestamp": Date().timeIntervalSince1970
        ]

        logger.info("Sending watch info: \(device.model) - watchOS \(device.systemVersion)")
        sendMessageWithFallback(data)
    }

    private func sendWatchInfoViaTransfer(_ data: [String: Any]) {
        WCSession.default.transferUserInfo(data)
        logger.info("Watch info sent via transferUserInfo")
    }

    /// Get current battery information as dictionary
    func getBatteryInfo() -> [String: Any] {
        let level = WKInterfaceDevice.current().batteryLevel * 100
        let state = WKInterfaceDevice.current().batteryState

        return [
            "level": level,
            "state": state.rawValue,
            "isCharging": state == .charging,
            "isFull": state == .full
        ]
    }
}
