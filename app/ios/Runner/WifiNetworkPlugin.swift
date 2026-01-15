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
    private func connectToWifi(ssid: String, password: String?, result: @escaping FlutterResult) {
        NSLog("WifiNetworkPlugin: Connecting to SSID: \(ssid), hasPassword: \(password != nil)")
        attemptConnection(ssid: ssid, password: password, isRetry: false, result: result)
    }

    /// Attempt to connect, with optional retry after clearing cached config
    private func attemptConnection(ssid: String, password: String?, isRetry: Bool, result: @escaping FlutterResult) {
        // Create configuration based on whether password is provided
        let configuration: NEHotspotConfiguration
        if let password = password, !password.isEmpty {
            // WPA/WPA2 network with password
            configuration = NEHotspotConfiguration(ssid: ssid, passphrase: password, isWEP: false)
        } else {
            // Open network (no password)
            configuration = NEHotspotConfiguration(ssid: ssid)
        }
        configuration.joinOnce = false  // Allow saving for seamless future connections

        NEHotspotConfigurationManager.shared.apply(configuration) { [weak self] error in
            if let error = error as NSError? {
                NSLog("WifiNetworkPlugin: Connection error (isRetry=\(isRetry)): \(error)")

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
                        // If this is the first attempt, try removing cached config and retry
                        // This handles the case where old (wrong) credentials are cached
                        if !isRetry {
                            NSLog("WifiNetworkPlugin: Invalid config, removing cached config and retrying...")
                            NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                                self?.attemptConnection(ssid: ssid, password: password, isRetry: true, result: result)
                            }
                            return
                        }
                        result(["success": false, "error": "Invalid SSID or password", "errorCode": 3])
                        return

                    case NEHotspotConfigurationError.joinOnceNotSupported.rawValue,
                         NEHotspotConfigurationError.systemConfiguration.rawValue:
                        result(["success": false, "error": "Not supported", "errorCode": 1])
                        return

                    default:
                        // For other errors (like authentication failures), try clearing cache and retry once
                        if !isRetry {
                            NSLog("WifiNetworkPlugin: Connection failed, removing cached config and retrying...")
                            NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                                self?.attemptConnection(ssid: ssid, password: password, isRetry: true, result: result)
                            }
                            return
                        }
                        result(["success": false, "error": error.localizedDescription, "errorCode": 4])
                        return
                    }
                }

                // For non-hotspot errors, also try retry once
                if !isRetry {
                    NSLog("WifiNetworkPlugin: Non-hotspot error, removing cached config and retrying...")
                    NEHotspotConfigurationManager.shared.removeConfiguration(forSSID: ssid)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self?.attemptConnection(ssid: ssid, password: password, isRetry: true, result: result)
                    }
                    return
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
