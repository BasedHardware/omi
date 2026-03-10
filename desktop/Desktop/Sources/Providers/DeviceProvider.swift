import Combine
import CoreBluetooth
import Foundation
import os.log
import SwiftUI
import UserNotifications

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when device has storage data available to sync
    static let storageSyncAvailable = Notification.Name("storageSyncAvailable")
}

/// State management for Bluetooth device connectivity
/// Ported from: omi/app/lib/providers/device_provider.dart
@MainActor
final class DeviceProvider: ObservableObject {

    // MARK: - Singleton

    static let shared = DeviceProvider()

    // MARK: - Published State

    /// Whether currently scanning for devices
    @Published private(set) var isScanning = false

    /// Whether currently connecting to a device
    @Published private(set) var isConnecting = false

    /// Whether a device is connected
    @Published private(set) var isConnected = false

    /// Currently connected device
    @Published private(set) var connectedDevice: BtDevice?

    /// Paired device (persisted across sessions)
    @Published private(set) var pairedDevice: BtDevice?

    /// Current battery level (0-100, or -1 if unavailable)
    @Published private(set) var batteryLevel: Int = -1

    /// List of discovered devices during scan
    @Published private(set) var discoveredDevices: [BtDevice] = []

    /// Current Bluetooth state
    @Published private(set) var bluetoothState: CBManagerState = .unknown

    /// Whether the device supports storage
    @Published private(set) var isDeviceStorageSupported = false

    /// Whether a firmware update is available
    @Published private(set) var hasFirmwareUpdate = false

    /// Latest firmware version (if update available)
    @Published private(set) var latestFirmwareVersion: String = ""

    /// Whether firmware update is in progress
    @Published private(set) var isFirmwareUpdateInProgress = false

    /// Error message for UI display
    @Published var errorMessage: String?

    // MARK: - Private Properties

    private var bluetoothManager: BluetoothManager { BluetoothManager.shared }
    /// The active device connection (internal for AudioSourceManager access)
    private(set) var activeConnection: DeviceConnection?
    private var batterySubscription: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()
    private var reconnectionTimer: Timer?
    private var reconnectAt: Date?
    private var disconnectNotificationTimer: Timer?
    private var hasLowBatteryAlerted = false

    private let logger = Logger(subsystem: "me.omi.desktop", category: "DeviceProvider")
    private let connectionCheckInterval: TimeInterval = 15.0

    // MARK: - UserDefaults Keys

    private enum UserDefaultsKeys {
        static let pairedDeviceId = "pairedDeviceId"
        static let pairedDeviceName = "pairedDeviceName"
        static let pairedDeviceType = "pairedDeviceType"
    }

    // MARK: - Initialization

    private var hasSetupBluetoothBindings = false

    private init() {
        setupNotificationBindings()
        loadPairedDevice()
    }

    /// Initialize Bluetooth bindings - call this when Bluetooth features are needed
    /// This is separate from init to avoid triggering Bluetooth permission dialog at app startup
    func initializeBluetoothBindingsIfNeeded() {
        guard !hasSetupBluetoothBindings else { return }
        hasSetupBluetoothBindings = true

        // Force CBCentralManager creation to start receiving state updates
        // This triggers the Bluetooth permission dialog on first use
        _ = bluetoothManager.centralManager

        // Observe Bluetooth state changes
        bluetoothManager.$bluetoothState
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                self?.bluetoothState = state
            }
            .store(in: &cancellables)

        // Observe scanning state
        bluetoothManager.$isScanning
            .receive(on: DispatchQueue.main)
            .sink { [weak self] scanning in
                self?.isScanning = scanning
            }
            .store(in: &cancellables)

        // Observe discovered devices
        bluetoothManager.$discoveredDevices
            .receive(on: DispatchQueue.main)
            .sink { [weak self] devices in
                self?.discoveredDevices = devices
            }
            .store(in: &cancellables)
    }

    private func setupNotificationBindings() {

        // Observe BLE connection events
        NotificationCenter.default.publisher(for: .bleDeviceConnected)
            .receive(on: DispatchQueue.main)
            .compactMap { $0.userInfo?["peripheralId"] as? UUID }
            .sink { [weak self] peripheralId in
                self?.handleDeviceConnected(peripheralId: peripheralId)
            }
            .store(in: &cancellables)

        NotificationCenter.default.publisher(for: .bleDeviceDisconnected)
            .receive(on: DispatchQueue.main)
            .compactMap { $0.userInfo?["peripheralId"] as? UUID }
            .sink { [weak self] peripheralId in
                self?.handleDeviceDisconnected(peripheralId: peripheralId)
            }
            .store(in: &cancellables)
    }

    // MARK: - Persistence

    private func loadPairedDevice() {
        guard let deviceId = UserDefaults.standard.string(forKey: UserDefaultsKeys.pairedDeviceId),
              !deviceId.isEmpty else {
            return
        }

        let deviceName = UserDefaults.standard.string(forKey: UserDefaultsKeys.pairedDeviceName) ?? "Unknown Device"
        let deviceTypeRaw = UserDefaults.standard.string(forKey: UserDefaultsKeys.pairedDeviceType) ?? "omi"
        let deviceType = DeviceType(rawValue: deviceTypeRaw) ?? .omi

        pairedDevice = BtDevice(
            id: deviceId,
            name: deviceName,
            type: deviceType,
            rssi: 0
        )

        logger.info("Loaded paired device: \(deviceName) (\(deviceId))")
    }

    private func savePairedDevice(_ device: BtDevice?) {
        if let device = device {
            UserDefaults.standard.set(device.id, forKey: UserDefaultsKeys.pairedDeviceId)
            UserDefaults.standard.set(device.name, forKey: UserDefaultsKeys.pairedDeviceName)
            UserDefaults.standard.set(device.type.rawValue, forKey: UserDefaultsKeys.pairedDeviceType)
            logger.info("Saved paired device: \(device.displayName)")
        } else {
            UserDefaults.standard.removeObject(forKey: UserDefaultsKeys.pairedDeviceId)
            UserDefaults.standard.removeObject(forKey: UserDefaultsKeys.pairedDeviceName)
            UserDefaults.standard.removeObject(forKey: UserDefaultsKeys.pairedDeviceType)
            logger.info("Cleared paired device")
        }
    }

    // MARK: - Discovery

    /// Start scanning for devices
    /// - Parameter timeout: Scan duration in seconds
    func startDiscovery(timeout: TimeInterval = 5.0) {
        // Initialize Bluetooth bindings if not already done
        initializeBluetoothBindingsIfNeeded()

        guard bluetoothState == .poweredOn else {
            errorMessage = "Bluetooth is not available"
            return
        }

        bluetoothManager.startScanning(timeout: timeout)
    }

    /// Stop scanning for devices
    func stopDiscovery() {
        initializeBluetoothBindingsIfNeeded()
        bluetoothManager.stopScanning()
    }

    // MARK: - Connection

    /// Connect to a device
    /// - Parameter device: The device to connect to
    func connect(to device: BtDevice) async {
        guard !isConnecting else {
            logger.warning("Already connecting to a device")
            return
        }

        guard !isConnected else {
            logger.warning("Already connected to a device")
            return
        }

        isConnecting = true
        errorMessage = nil

        do {
            // Create connection using factory
            guard let connection = DeviceConnectionFactory.create(device: device) else {
                throw DeviceConnectionError.connectionFailed("Failed to create connection")
            }

            // Connect
            try await connection.connect()

            // Store the connection
            activeConnection = connection

            // Update state
            connectedDevice = connection.device
            pairedDevice = connection.device
            isConnected = true

            // Save as paired device
            savePairedDevice(connection.device)

            // Start battery monitoring
            await startBatteryMonitoring()

            // Check storage support
            await checkStorageSupport()

            // Check for firmware updates
            await checkFirmwareUpdates()

            // Cancel reconnection timer
            reconnectionTimer?.invalidate()
            reconnectionTimer = nil

            // Clear any pending disconnect notification
            disconnectNotificationTimer?.invalidate()
            disconnectNotificationTimer = nil

            logger.info("Connected to \(device.displayName)")

            // TODO: Track analytics when AnalyticsManager supports device events
            // AnalyticsManager.shared.deviceConnected(deviceType: device.type.rawValue, deviceName: device.name)

        } catch {
            logger.error("Failed to connect to \(device.displayName): \(error.localizedDescription)")
            errorMessage = "Failed to connect: \(error.localizedDescription)"
            activeConnection = nil
        }

        isConnecting = false
    }

    /// Disconnect from the current device
    func disconnect() async {
        guard let connection = activeConnection else {
            logger.warning("No active connection to disconnect")
            return
        }

        await connection.disconnect()
        handleDisconnection()

        logger.info("Disconnected from device")
    }

    /// Unpair the current device (disconnect and clear pairing)
    func unpair() async {
        if let connection = activeConnection {
            await connection.unpair()
        }

        handleDisconnection()
        savePairedDevice(nil)
        pairedDevice = nil

        logger.info("Unpaired device")
    }

    private func handleDisconnection() {
        // Cancel battery monitoring
        batterySubscription?.cancel()
        batterySubscription = nil

        // Clear state
        activeConnection = nil
        connectedDevice = nil
        isConnected = false
        batteryLevel = -1
        isDeviceStorageSupported = false
        hasFirmwareUpdate = false
        hasLowBatteryAlerted = false

        // TODO: Track analytics when AnalyticsManager supports device events
        // AnalyticsManager.shared.deviceDisconnected()

        // Schedule disconnect notification
        scheduleDisconnectNotification()

        // Start reconnection attempts
        startReconnectionTimer()
    }

    // MARK: - Auto-Reconnection

    /// Start periodic reconnection attempts
    func startReconnectionTimer() {
        guard pairedDevice != nil else { return }
        guard reconnectionTimer == nil else { return }

        reconnectionTimer = Timer.scheduledTimer(
            withTimeInterval: connectionCheckInterval,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor in
                await self?.attemptReconnection()
            }
        }

        // Attempt immediately
        Task {
            await attemptReconnection()
        }
    }

    /// Stop reconnection attempts
    func stopReconnectionTimer() {
        reconnectionTimer?.invalidate()
        reconnectionTimer = nil
    }

    private func attemptReconnection() async {
        // Skip if already connected or connecting
        guard !isConnected && !isConnecting else { return }

        // Skip if reconnection is delayed
        if let reconnectAt = reconnectAt, reconnectAt > Date() {
            return
        }

        // Skip if no paired device
        guard let pairedDevice = pairedDevice else {
            stopReconnectionTimer()
            return
        }

        logger.debug("Attempting reconnection to \(pairedDevice.displayName)")

        // Try direct connection first
        await connect(to: pairedDevice)

        if isConnected {
            stopReconnectionTimer()
            return
        }

        // If direct connection failed, scan for the device
        startDiscovery(timeout: 5.0)

        // Wait for scan to complete
        try? await Task.sleep(nanoseconds: 5_500_000_000)

        // Check if device was found during scan
        if let foundDevice = discoveredDevices.first(where: { $0.id == pairedDevice.id }) {
            await connect(to: foundDevice)
        }
    }

    // MARK: - Battery Monitoring

    private func startBatteryMonitoring() async {
        guard let connection = activeConnection else { return }

        // Get initial battery level
        let level = await connection.getBatteryLevel()
        if level >= 0 {
            batteryLevel = level
            checkLowBattery()
        }

        // Start listening for battery updates
        batterySubscription?.cancel()
        batterySubscription = Task {
            do {
                for try await level in connection.getBatteryLevelStream() {
                    await MainActor.run {
                        self.batteryLevel = level
                        self.checkLowBattery()
                    }
                }
            } catch {
                logger.debug("Battery stream ended: \(error.localizedDescription)")
            }
        }
    }

    private func checkLowBattery() {
        guard batteryLevel >= 0 && batteryLevel < 20 && !hasLowBatteryAlerted else {
            if batteryLevel >= 20 {
                hasLowBatteryAlerted = false
            }
            return
        }

        hasLowBatteryAlerted = true

        // Send low battery notification
        let content = UNMutableNotificationContent()
        content.title = "Low Battery Alert"
        content.body = "Your omi device is running low on battery. Time for a recharge! 🔋"
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "lowBattery",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }

    // MARK: - Storage Support

    private func checkStorageSupport() async {
        guard let connection = activeConnection else {
            isDeviceStorageSupported = false
            return
        }

        let storageList = await connection.getStorageList()
        isDeviceStorageSupported = !storageList.isEmpty

        // Check for pending storage data to sync
        if isDeviceStorageSupported {
            await checkPendingStorageSync()
        }
    }

    /// Check if device has pending storage data to sync
    private func checkPendingStorageSync() async {
        guard let (totalBytes, currentOffset) = await StorageSyncService.shared.checkForStorageData() else {
            return
        }

        let bytesToSync = totalBytes - currentOffset

        // Only notify if there's significant data (more than 10 seconds worth)
        let minBytesThreshold = 80 * 100 * 10 // 80 bytes/frame * 100 fps * 10 seconds
        if bytesToSync >= minBytesThreshold {
            let mbToSync = Double(bytesToSync) / (1024 * 1024)
            logger.info("Device has \(String(format: "%.1f", mbToSync)) MB of audio data pending sync")

            // Post notification that storage sync is available
            NotificationCenter.default.post(
                name: .storageSyncAvailable,
                object: nil,
                userInfo: ["bytesToSync": bytesToSync]
            )
        }
    }

    // MARK: - Firmware Updates

    private func checkFirmwareUpdates() async {
        guard !isFirmwareUpdateInProgress else { return }
        guard let device = connectedDevice else { return }

        // TODO: Implement firmware update check via API
        // For now, just log that we would check
        logger.debug("Would check firmware updates for \(device.displayName)")

        // Example implementation:
        // let (hasUpdate, version) = await APIClient.shared.checkFirmwareUpdate(
        //     modelNumber: device.modelNumber,
        //     currentFirmware: device.firmwareRevision
        // )
        // hasFirmwareUpdate = hasUpdate
        // latestFirmwareVersion = version
    }

    /// Set firmware update in progress state
    func setFirmwareUpdateInProgress(_ inProgress: Bool) {
        isFirmwareUpdateInProgress = inProgress
    }

    /// Prepare for DFU (firmware update)
    func prepareDFU() async {
        guard connectedDevice != nil else { return }

        await disconnect()

        // Delay reconnection to allow DFU
        reconnectAt = Date().addingTimeInterval(30)
    }

    // MARK: - Notifications

    private func scheduleDisconnectNotification() {
        disconnectNotificationTimer?.invalidate()
        disconnectNotificationTimer = Timer.scheduledTimer(
            withTimeInterval: 30.0,
            repeats: false
        ) { [weak self] _ in
            Task { @MainActor in
                self?.sendDisconnectNotification()
            }
        }
    }

    private func sendDisconnectNotification() {
        let content = UNMutableNotificationContent()
        content.title = "Your omi Device Disconnected"
        content.body = "Please reconnect to continue using your omi."
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "deviceDisconnected",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }

    // MARK: - Event Handlers

    private func handleDeviceConnected(peripheralId: UUID) {
        // Check if this is our paired device
        guard let pairedDevice = pairedDevice,
              pairedDevice.id == peripheralId.uuidString else {
            return
        }

        // If we're not already handling the connection, connect now
        if !isConnecting && !isConnected {
            Task {
                await connect(to: pairedDevice)
            }
        }
    }

    private func handleDeviceDisconnected(peripheralId: UUID) {
        // Check if this is our connected device
        guard let connectedDevice = connectedDevice,
              connectedDevice.id == peripheralId.uuidString else {
            return
        }

        // Handle the disconnection
        handleDisconnection()
    }

    // MARK: - Audio Stream

    /// Get an audio stream from the connected device
    func getAudioStream() -> AsyncThrowingStream<Data, Error>? {
        guard let connection = activeConnection else { return nil }
        return connection.getAudioStream()
    }

    /// Get the audio codec of the connected device
    func getAudioCodec() async -> BleAudioCodec {
        guard let connection = activeConnection else { return .pcm8 }
        return await connection.getAudioCodec()
    }

    // MARK: - Device Features

    /// Get the features supported by the connected device
    func getFeatures() async -> OmiFeatures {
        guard let connection = activeConnection else { return [] }
        return await connection.getFeatures()
    }

    /// Check if the connected device supports WiFi sync
    func isWifiSyncSupported() async -> Bool {
        guard let connection = activeConnection else { return false }
        return await connection.isWifiSyncSupported()
    }

    // MARK: - Device Settings

    /// Set the LED dim ratio (0-100)
    func setLedDimRatio(_ ratio: Int) async {
        guard let connection = activeConnection else { return }
        await connection.setLedDimRatio(ratio)
    }

    /// Get the LED dim ratio
    func getLedDimRatio() async -> Int? {
        guard let connection = activeConnection else { return nil }
        return await connection.getLedDimRatio()
    }

    /// Set the microphone gain (0-100)
    func setMicGain(_ gain: Int) async {
        guard let connection = activeConnection else { return }
        await connection.setMicGain(gain)
    }

    /// Get the microphone gain
    func getMicGain() async -> Int? {
        guard let connection = activeConnection else { return nil }
        return await connection.getMicGain()
    }

    // MARK: - WiFi Sync

    /// Setup WiFi sync with credentials
    func setupWifiSync(ssid: String, password: String) async -> WifiSyncSetupResult {
        guard let connection = activeConnection else {
            return .connectionFailed()
        }
        return await connection.setupWifiSync(ssid: ssid, password: password)
    }

    /// Start WiFi sync
    func startWifiSync() async -> Bool {
        guard let connection = activeConnection else { return false }
        return await connection.startWifiSync()
    }

    /// Stop WiFi sync
    func stopWifiSync() async -> Bool {
        guard let connection = activeConnection else { return false }
        return await connection.stopWifiSync()
    }

    // MARK: - Button Stream

    /// Get a stream of button press events
    func getButtonStream() -> AsyncThrowingStream<[UInt8], Error>? {
        guard let connection = activeConnection else { return nil }
        return connection.getButtonStream()
    }

    // MARK: - Accelerometer Stream

    /// Get a stream of accelerometer data
    func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error>? {
        guard let connection = activeConnection else { return nil }
        return connection.getAccelerometerStream()
    }

    // MARK: - Cleanup

    deinit {
        reconnectionTimer?.invalidate()
        disconnectNotificationTimer?.invalidate()
        batterySubscription?.cancel()
    }
}

// MARK: - DeviceConnectionDelegate

extension DeviceProvider: DeviceConnectionDelegate {
    nonisolated func deviceConnection(_ connection: DeviceConnection, didDisconnectUnexpectedly device: BtDevice) {
        Task { @MainActor in
            logger.warning("Device disconnected unexpectedly: \(device.displayName)")
            handleDisconnection()
        }
    }

    nonisolated func deviceConnection(_ connection: DeviceConnection, didDetectFall data: AccelerometerData) {
        Task { @MainActor in
            logger.warning("Fall detected! Magnitude: \(data.magnitude)")

            // Send fall detection notification
            let content = UNMutableNotificationContent()
            content.title = "Fall Detected"
            content.body = "A potential fall was detected by your omi device."
            content.sound = .default

            let request = UNNotificationRequest(
                identifier: "fallDetected-\(Date().timeIntervalSince1970)",
                content: content,
                trigger: nil
            )

            try? await UNUserNotificationCenter.current().add(request)
        }
    }
}
