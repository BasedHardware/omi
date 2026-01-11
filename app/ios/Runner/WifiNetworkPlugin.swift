import Flutter
import NetworkExtension

/// Plugin for managing WiFi network connections to Omi device's AP.
/// Uses NEHotspotConfiguration to connect to open networks programmatically.
class WifiNetworkPlugin: NSObject {
    private let channel: FlutterMethodChannel

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
            connectToWifi(ssid: ssid, result: result)

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

    /// Connect to an open WiFi network (no password).
    private func connectToWifi(ssid: String, result: @escaping FlutterResult) {
        NSLog("WifiNetworkPlugin: Connecting to SSID: \(ssid)")

        // Create configuration for open network (no password)
        let configuration = NEHotspotConfiguration(ssid: ssid)
        configuration.joinOnce = true

        NEHotspotConfigurationManager.shared.apply(configuration) { error in
            if let error = error as NSError? {
                NSLog("WifiNetworkPlugin: Connection error: \(error)")

                if error.domain == NEHotspotConfigurationErrorDomain {
                    switch error.code {
                    case NEHotspotConfigurationError.alreadyAssociated.rawValue:
                        // Already connected - this is success
                        NSLog("WifiNetworkPlugin: Already connected to \(ssid)")
                        result(["success": true])
                        return

                    case NEHotspotConfigurationError.userDenied.rawValue:
                        result(["success": false, "error": "User denied connection", "errorCode": 2])
                        return

                    case NEHotspotConfigurationError.invalid.rawValue,
                         NEHotspotConfigurationError.invalidSSID.rawValue:
                        result(["success": false, "error": "Invalid SSID", "errorCode": 3])
                        return

                    case NEHotspotConfigurationError.joinOnceNotSupported.rawValue,
                         NEHotspotConfigurationError.systemConfiguration.rawValue:
                        result(["success": false, "error": "Not supported", "errorCode": 1])
                        return

                    default:
                        result(["success": false, "error": error.localizedDescription, "errorCode": 4])
                        return
                    }
                }

                result(["success": false, "error": error.localizedDescription, "errorCode": 0])
            } else {
                NSLog("WifiNetworkPlugin: Successfully connected to \(ssid)")
                result(["success": true])
            }
        }
    }

    /// Disconnect from a WiFi network by removing its configuration.
    private func disconnectFromWifi(ssid: String, result: @escaping FlutterResult) {
        NSLog("WifiNetworkPlugin: Disconnecting from SSID: \(ssid)")
        NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
        result(true)
    }

    /// Check if we have a configuration for the specified SSID.
    /// Note: This doesn't guarantee we're currently connected, just that we've configured it.
    private func isConnectedToWifi(ssid: String, result: @escaping FlutterResult) {
        NEHotspotConfigurationManager.shared.getConfiguredSSIDs { ssids in
            let isConfigured = ssids.contains(ssid)
            NSLog("WifiNetworkPlugin: Is configured for \(ssid): \(isConfigured)")
            result(isConfigured)
        }
    }
}
