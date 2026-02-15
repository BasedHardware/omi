import Flutter
import NetworkExtension

/// Plugin for managing WiFi network connections to Omi device's AP.
/// Uses NEHotspotConfiguration to connect to networks programmatically.
///
/// Connection flow:
/// 1. Remove any existing config for the SSID
/// 2. Apply new config (iOS shows "Join WiFi?" dialog)
/// 3. Start monitoring loop - check if connected to target SSID
/// 4. If not connected after 3 seconds, re-apply the config
/// 5. Repeat until connected or timeout (30 seconds)
class WifiNetworkPlugin: NSObject {
    private let channel: FlutterMethodChannel

    // Connection state
    private var connectLoop = false
    private var connectionStartTime: Date?
    private static let connectionTimeout: TimeInterval = 30.0
    private static let retryInterval: TimeInterval = 3.0

    init(messenger: FlutterBinaryMessenger) {
        channel = FlutterMethodChannel(name: "com.omi.wifi_network", binaryMessenger: messenger)
        super.init()
        channel.setMethodCallHandler(handle)
    }

    private func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "connectToWifi":
            guard let args = call.arguments as? [String: Any],
                  let ssid = args["ssid"] as? String else {
                result(["success": false, "error": "Invalid arguments", "errorCode": 0])
                return
            }
            let password = args["password"] as? String
            connectToWifi(ssid: ssid, password: password, result: result)

        case "disconnectFromWifi":
            guard let args = call.arguments as? [String: Any],
                  let ssid = args["ssid"] as? String else {
                result(false)
                return
            }
            disconnectFromWifi(ssid: ssid, result: result)

        case "isConnectedToWifi":
            guard let args = call.arguments as? [String: Any],
                  let ssid = args["ssid"] as? String else {
                result(false)
                return
            }
            isConnectedToWifi(ssid: ssid, result: result)

        default:
            result(FlutterMethodNotImplemented)
        }
    }

    /// Connect to a WiFi network, optionally with a password.
    /// Uses a retry loop that re-applies the config until connected or timeout.
    private func connectToWifi(ssid: String, password: String?, result: @escaping FlutterResult) {
        NSLog("WifiNetworkPlugin: Connecting to SSID: \(ssid), hasPassword: \(password != nil)")

        // Initialize connection state
        connectLoop = true
        connectionStartTime = Date()

        applyConfigAndMonitor(ssid: ssid, password: password, result: result)
    }

    /// Apply the WiFi configuration and start monitoring for connection
    private func applyConfigAndMonitor(ssid: String, password: String?, result: @escaping FlutterResult) {
        guard connectLoop else {
            NSLog("WifiNetworkPlugin: Connection loop cancelled")
            return
        }

        // Check if we've exceeded the timeout
        if let startTime = connectionStartTime {
            let elapsed = Date().timeIntervalSince(startTime)
            if elapsed >= WifiNetworkPlugin.connectionTimeout {
                NSLog("WifiNetworkPlugin: Connection timeout after \(elapsed) seconds")
                connectLoop = false
                NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
                result(["success": false, "error": "Connection timeout. Please try again.", "errorCode": -2])
                return
            }
        }

        // Create configuration
        let configuration: NEHotspotConfiguration
        if let password = password, !password.isEmpty {
            configuration = NEHotspotConfiguration(ssid: ssid, passphrase: password, isWEP: false)
        } else {
            configuration = NEHotspotConfiguration(ssid: ssid)
        }

        configuration.joinOnce = false


        NEHotspotConfigurationManager.shared.apply(configuration) { [weak self] error in
            guard let self = self, self.connectLoop else { return }

            if let error = error as NSError? {
                NSLog("WifiNetworkPlugin: Apply error: \(error.domain) code=\(error.code)")

                if error.domain == NEHotspotConfigurationErrorDomain {
                    switch error.code {
                    case NEHotspotConfigurationError.alreadyAssociated.rawValue:
                        NSLog("WifiNetworkPlugin: Already connected to \(ssid)")
                        self.connectLoop = false
                        result(["success": true])
                        return

                    case NEHotspotConfigurationError.userDenied.rawValue:
                        NSLog("WifiNetworkPlugin: User denied WiFi connection")
                        self.connectLoop = false
                        result(["success": false, "error": "User denied WiFi connection", "errorCode": 2])
                        return

                    case NEHotspotConfigurationError.invalidWPAPassphrase.rawValue:
                        self.connectLoop = false
                        result(["success": false, "error": "Invalid WiFi password (must be 8-63 characters)", "errorCode": 3])
                        return

                    case NEHotspotConfigurationError.applicationIsNotInForeground.rawValue:
                        self.connectLoop = false
                        result(["success": false, "error": "App must be in foreground to connect", "errorCode": 4])
                        return

                    default:
                        NSLog("WifiNetworkPlugin: Error \(error.code), will check connection and retry if needed")
                    }
                }
            }

            self.monitorConnection(ssid: ssid, password: password, result: result)
        }
    }

    /// Monitor connection status and re-apply config if not connected
    private func monitorConnection(ssid: String, password: String?, result: @escaping FlutterResult) {
        guard connectLoop else { return }

        NEHotspotNetwork.fetchCurrent { [weak self] network in
            guard let self = self, self.connectLoop else { return }

            let currentSSID = network?.ssid

            if currentSSID == ssid {
                NSLog("WifiNetworkPlugin: Successfully connected to \(ssid)")
                self.connectLoop = false
                result(["success": true])
                return
            }

            guard let startTime = self.connectionStartTime else {
                self.connectLoop = false
                result(["success": false, "error": "Connection state error", "errorCode": 4])
                return
            }

            let elapsed = Date().timeIntervalSince(startTime)

            if elapsed >= WifiNetworkPlugin.connectionTimeout {
                NSLog("WifiNetworkPlugin: Connection timeout after \(elapsed) seconds")
                self.connectLoop = false
                NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)

                let errorMsg: String
                if let current = currentSSID {
                    errorMsg = "Phone stayed on '\(current)' instead of switching to device WiFi."
                } else {
                    errorMsg = "Failed to join device WiFi network."
                }
                result(["success": false, "error": errorMsg, "errorCode": 5])
                return
            }

            DispatchQueue.main.asyncAfter(deadline: .now() + WifiNetworkPlugin.retryInterval) { [weak self] in
                guard let self = self, self.connectLoop else { return }

                // Re-apply the configuration
                self.applyConfigAndMonitor(ssid: ssid, password: password, result: result)
            }
        }
    }

    /// Disconnect from a WiFi network by removing its configuration.
    private func disconnectFromWifi(ssid: String, result: @escaping FlutterResult) {
        NSLog("WifiNetworkPlugin: Disconnecting from SSID: \(ssid)")
        connectLoop = false
        NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
        result(true)
    }

    /// Check if we're currently connected to the specified SSID.
    private func isConnectedToWifi(ssid: String, result: @escaping FlutterResult) {
        NEHotspotNetwork.fetchCurrent { network in
            let isConnected = network?.ssid == ssid
            result(isConnected)
        }
    }
}
