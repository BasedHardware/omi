package com.friend.ios

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.wifi.WifiConfiguration
import android.net.wifi.WifiManager
import android.net.wifi.WifiNetworkSpecifier
import android.os.Build
import android.util.Log
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * Plugin for managing WiFi network connections to Omi device's AP.
 *
 * For Android 10+ (API 29+): Uses WifiNetworkSpecifier with ConnectivityManager
 * For Android 9 and below: Uses deprecated WifiConfiguration APIs
 */
class WifiNetworkPlugin(private val context: Context) : MethodChannel.MethodCallHandler {

    companion object {
        private const val TAG = "WifiNetworkPlugin"
        private const val CHANNEL_NAME = "com.omi.wifi_network"

        fun registerWith(flutterEngine: FlutterEngine, context: Context) {
            val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL_NAME)
            channel.setMethodCallHandler(WifiNetworkPlugin(context))
        }
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var connectedNetwork: Network? = null
    private var currentSsid: String? = null

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "connectToWifi" -> {
                val ssid = call.argument<String>("ssid")
                if (ssid == null) {
                    result.success(mapOf("success" to false, "error" to "Invalid arguments", "errorCode" to 0))
                    return
                }
                val password = call.argument<String>("password")
                connectToWifi(ssid, password, result)
            }
            "disconnectFromWifi" -> {
                val ssid = call.argument<String>("ssid")
                if (ssid == null) {
                    result.success(false)
                    return
                }
                disconnectFromWifi(result)
            }
            "isConnectedToWifi" -> {
                val ssid = call.argument<String>("ssid")
                if (ssid == null) {
                    result.success(false)
                    return
                }
                isConnectedToWifi(ssid, result)
            }
            else -> result.notImplemented()
        }
    }

    /**
     * Connect to a WiFi network, optionally with a password.
     */
    private fun connectToWifi(ssid: String, password: String?, result: MethodChannel.Result) {
        Log.d(TAG, "Connecting to SSID: $ssid, hasPassword: ${password != null}")

        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Android 10+ uses WifiNetworkSpecifier
            connectWithNetworkSpecifier(ssid, password, connectivityManager, result)
        } else {
            // Android 9 and below uses deprecated WifiConfiguration
            connectWithWifiConfiguration(ssid, password, result)
        }
    }

    /**
     * Connect using WifiNetworkSpecifier (Android 10+).
     * This shows a system bottom sheet for the user to confirm connection.
     */
    private fun connectWithNetworkSpecifier(
        ssid: String,
        password: String?,
        connectivityManager: ConnectivityManager,
        result: MethodChannel.Result
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            result.success(mapOf("success" to false, "error" to "Not supported", "errorCode" to 1))
            return
        }

        // Clean up any existing callback
        cleanupNetworkCallback(connectivityManager)

        try {
            val specifierBuilder = WifiNetworkSpecifier.Builder()
                .setSsid(ssid)

            // Add password if provided (WPA2)
            if (!password.isNullOrEmpty()) {
                specifierBuilder.setWpa2Passphrase(password)
            }

            val specifier = specifierBuilder.build()

            val request = NetworkRequest.Builder()
                .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .setNetworkSpecifier(specifier)
                .build()

            var hasResponded = false

            networkCallback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    super.onAvailable(network)
                    Log.d(TAG, "Network available: $network")
                    connectedNetwork = network
                    currentSsid = ssid

                    // Bind process to this network for socket operations
                    // This is critical - without this, sockets will use the default network
                    connectivityManager.bindProcessToNetwork(network)

                    if (!hasResponded) {
                        hasResponded = true
                        result.success(mapOf("success" to true))
                    }
                }

                override fun onUnavailable() {
                    super.onUnavailable()
                    Log.d(TAG, "Network unavailable")
                    if (!hasResponded) {
                        hasResponded = true
                        result.success(mapOf("success" to false, "error" to "Network unavailable", "errorCode" to 3))
                    }
                }

                override fun onLost(network: Network) {
                    super.onLost(network)
                    Log.d(TAG, "Network lost: $network")
                    if (network == connectedNetwork) {
                        connectedNetwork = null
                        currentSsid = null
                        connectivityManager.bindProcessToNetwork(null)
                    }
                }

                override fun onCapabilitiesChanged(
                    network: Network,
                    networkCapabilities: NetworkCapabilities
                ) {
                    super.onCapabilitiesChanged(network, networkCapabilities)
                    Log.d(TAG, "Network capabilities changed for $network")
                }
            }

            connectivityManager.requestNetwork(request, networkCallback!!)
            Log.d(TAG, "Network request submitted for SSID: $ssid")

        } catch (e: Exception) {
            Log.e(TAG, "Error connecting to WiFi: ${e.message}", e)
            result.success(mapOf("success" to false, "error" to e.message, "errorCode" to 4))
        }
    }

    /**
     * Connect using WifiConfiguration (Android 9 and below).
     * This is deprecated but needed for backwards compatibility.
     */
    @Suppress("DEPRECATION")
    private fun connectWithWifiConfiguration(ssid: String, password: String?, result: MethodChannel.Result) {
        try {
            val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager

            // Ensure WiFi is enabled
            if (!wifiManager.isWifiEnabled) {
                // On Android 9, we can't programmatically enable WiFi
                result.success(mapOf("success" to false, "error" to "WiFi is disabled", "errorCode" to 1))
                return
            }

            // Create configuration based on whether password is provided
            val config = WifiConfiguration().apply {
                SSID = "\"$ssid\""
                if (!password.isNullOrEmpty()) {
                    // WPA/WPA2 network
                    preSharedKey = "\"$password\""
                    allowedKeyManagement.set(WifiConfiguration.KeyMgmt.WPA_PSK)
                } else {
                    // Open network
                    allowedKeyManagement.set(WifiConfiguration.KeyMgmt.NONE)
                }
            }

            // Add and enable the network
            val netId = wifiManager.addNetwork(config)
            if (netId == -1) {
                result.success(mapOf("success" to false, "error" to "Failed to add network", "errorCode" to 4))
                return
            }

            // Disconnect from current network, connect to new one, and reconnect
            wifiManager.disconnect()
            val success = wifiManager.enableNetwork(netId, true)
            wifiManager.reconnect()

            if (success) {
                currentSsid = ssid
                Log.d(TAG, "Successfully connected to SSID: $ssid")
                result.success(mapOf("success" to true))
            } else {
                Log.e(TAG, "Failed to enable network for SSID: $ssid")
                result.success(mapOf("success" to false, "error" to "Failed to enable network", "errorCode" to 4))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error connecting to WiFi: ${e.message}", e)
            result.success(mapOf("success" to false, "error" to e.message, "errorCode" to 4))
        }
    }

    /**
     * Disconnect from the device's WiFi and restore default network.
     */
    private fun disconnectFromWifi(result: MethodChannel.Result) {
        Log.d(TAG, "Disconnecting from WiFi")

        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

        // Unbind process from the network
        connectivityManager.bindProcessToNetwork(null)

        // Unregister the network callback (this triggers disconnect on Android 10+)
        cleanupNetworkCallback(connectivityManager)

        connectedNetwork = null
        currentSsid = null

        result.success(true)
    }

    /**
     * Check if currently connected to the specified SSID.
     */
    private fun isConnectedToWifi(ssid: String, result: MethodChannel.Result) {
        val isConnected = currentSsid == ssid && connectedNetwork != null
        Log.d(TAG, "Is connected to $ssid: $isConnected")
        result.success(isConnected)
    }

    /**
     * Clean up network callback to prevent leaks.
     */
    private fun cleanupNetworkCallback(connectivityManager: ConnectivityManager) {
        networkCallback?.let {
            try {
                connectivityManager.unregisterNetworkCallback(it)
                Log.d(TAG, "Unregistered network callback")
            } catch (e: Exception) {
                Log.w(TAG, "Error unregistering network callback: ${e.message}")
            }
            networkCallback = null
        }
    }
}
