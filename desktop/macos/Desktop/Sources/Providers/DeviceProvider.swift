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

    static let shared = DeviceProvider(bluetoothManager: BluetoothManager.shared)
    typealias ConnectionFactory = @MainActor (BtDevice, UInt64) -> DeviceConnection?
    typealias StorageDataChecker = @MainActor () async -> (totalBytes: Int, currentOffset: Int)?

    // MARK: - Published State

    /// Whether currently scanning for devices
    @Published private(set) var isScanning = false

    /// The canonical Bluetooth lifecycle state. UI-facing convenience
    /// properties below are read-only projections of this snapshot.
    @Published private(set) var sessionSnapshot: DeviceSessionSnapshot

    var isConnecting: Bool { sessionSnapshot.phase.isConnecting }
    var isConnected: Bool { sessionSnapshot.phase.isReady }
    var connectedDevice: BtDevice? { sessionSnapshot.connectedDevice }
    var pairedDevice: BtDevice? { sessionSnapshot.pairedDevice }
    var isConnectedPublisher: AnyPublisher<Bool, Never> {
        $sessionSnapshot
            .map { $0.phase.isReady }
            .removeDuplicates()
            .eraseToAnyPublisher()
    }

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

    private let bluetoothManager: DeviceBluetoothManaging
    private let userDefaults: UserDefaults
    private let notificationCenter: NotificationCenter
    private let storageDataChecker: StorageDataChecker
    private let sessionCoordinator: DeviceSessionCoordinator

    /// The active connection is owned by the session coordinator. This
    /// projection remains internal for AudioSourceManager access.
    var activeConnection: DeviceConnection? { sessionCoordinator.activeConnection }

    private var batterySubscription: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()
    private var disconnectNotificationTimer: Timer?
    private var hasLowBatteryAlerted = false

    private let logger = Logger(subsystem: "me.omi.desktop", category: "DeviceProvider")

    // MARK: - UserDefaults Keys

    private enum UserDefaultsKeys {
        static let pairedDeviceId = "pairedDeviceId"
        static let pairedDeviceName = "pairedDeviceName"
        static let pairedDeviceType = "pairedDeviceType"
    }

    // MARK: - Initialization

    private var hasSetupBluetoothBindings = false

    init(
        bluetoothManager: DeviceBluetoothManaging,
        userDefaults: UserDefaults = .standard,
        notificationCenter: NotificationCenter = .default,
        connectionFactory: @escaping ConnectionFactory = {
            DeviceConnectionFactory.create(device: $0, sessionGeneration: $1)
        },
        storageDataChecker: @escaping StorageDataChecker = { await StorageSyncService.shared.checkForStorageData() },
        sessionScheduler: (any DeviceSessionScheduling)? = nil,
        reconnectDelay: Duration = .seconds(15),
        autoReconnectEnabled: Bool = true
    ) {
        let persistedDevice = Self.loadPairedDevice(from: userDefaults)
        let coordinator = DeviceSessionCoordinator(
            pairedDevice: persistedDevice,
            connectionFactory: connectionFactory,
            scheduler: sessionScheduler ?? DeviceSessionTaskScheduler(),
            reconnectDelay: reconnectDelay,
            autoReconnectEnabled: autoReconnectEnabled
        )

        self.bluetoothManager = bluetoothManager
        self.userDefaults = userDefaults
        self.notificationCenter = notificationCenter
        self.storageDataChecker = storageDataChecker
        self.sessionCoordinator = coordinator
        self.sessionSnapshot = coordinator.snapshot

        coordinator.onSnapshotChanged = { [weak self] snapshot in
            self?.sessionSnapshot = snapshot
        }
        coordinator.onReconnectRequested = { [weak self] request in
            Task { @MainActor in
                await self?.connect(
                    to: request.device,
                    reconnectRequest: request
                )
            }
        }
        coordinator.onDiscoveryRequested = { [weak self] in
            self?.startDiscovery(timeout: 5)
        }
        coordinator.onSessionEnded = { [weak self] in
            self?.resetSessionPresentation()
        }
        coordinator.onFallDetected = { [weak self] data in
            self?.sendFallDetectionNotification(data: data)
        }

        if let persistedDevice {
            logger.info("Loaded paired device: \(persistedDevice.displayName)")
        }
    }

    /// Initialize Bluetooth bindings - call this when Bluetooth features are needed
    /// This is separate from init to avoid triggering Bluetooth permission dialog at app startup
    func initializeBluetoothBindingsIfNeeded() {
        guard !hasSetupBluetoothBindings else { return }
        hasSetupBluetoothBindings = true

        bluetoothManager.prepareForStateUpdates()

        bluetoothState = bluetoothManager.currentBluetoothState
        isScanning = bluetoothManager.currentIsScanning
        discoveredDevices = bluetoothManager.currentDiscoveredDevices

        // Observe Bluetooth state changes
        bluetoothManager.bluetoothStatePublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                self?.bluetoothState = state
            }
            .store(in: &cancellables)

        // Observe scanning state
        bluetoothManager.isScanningPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] scanning in
                self?.isScanning = scanning
            }
            .store(in: &cancellables)

        // Observe discovered devices
        bluetoothManager.discoveredDevicesPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] devices in
                self?.discoveredDevices = devices
            }
            .store(in: &cancellables)
    }

    // MARK: - Persistence

    private static func loadPairedDevice(from userDefaults: UserDefaults) -> BtDevice? {
        guard let deviceId = userDefaults.string(forKey: UserDefaultsKeys.pairedDeviceId),
              !deviceId.isEmpty else {
            return nil
        }

        let deviceName = userDefaults.string(forKey: UserDefaultsKeys.pairedDeviceName) ?? "Unknown Device"
        let deviceTypeRaw = userDefaults.string(forKey: UserDefaultsKeys.pairedDeviceType) ?? "omi"
        let deviceType = DeviceType(rawValue: deviceTypeRaw) ?? .omi

        return BtDevice(
            id: deviceId,
            name: deviceName,
            type: deviceType,
            rssi: 0
        )
    }

    private func savePairedDevice(_ device: BtDevice?) {
        if let device = device {
            userDefaults.set(device.id, forKey: UserDefaultsKeys.pairedDeviceId)
            userDefaults.set(device.name, forKey: UserDefaultsKeys.pairedDeviceName)
            userDefaults.set(device.type.rawValue, forKey: UserDefaultsKeys.pairedDeviceType)
            logger.info("Saved paired device: \(device.displayName)")
        } else {
            userDefaults.removeObject(forKey: UserDefaultsKeys.pairedDeviceId)
            userDefaults.removeObject(forKey: UserDefaultsKeys.pairedDeviceName)
            userDefaults.removeObject(forKey: UserDefaultsKeys.pairedDeviceType)
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
        await connect(to: device, reconnectRequest: nil)
    }

    private func connect(
        to device: BtDevice,
        reconnectRequest: DeviceReconnectRequest?
    ) async {
        errorMessage = nil

        do {
            let connection: DeviceConnection
            if let reconnectRequest {
                connection = try await sessionCoordinator.reconnect(reconnectRequest)
            } else {
                connection = try await sessionCoordinator.connect(to: device)
            }
            let generation = connection.sessionGeneration

            // Save as paired device
            savePairedDevice(connection.device)

            // Start battery monitoring
            await startBatteryMonitoring(connection: connection, generation: generation)
            guard sessionCoordinator.isReady(generation: generation) else { return }

            // Check storage support
            await checkStorageSupport(connection: connection, generation: generation)
            guard sessionCoordinator.isReady(generation: generation) else { return }

            // Check for firmware updates
            await checkFirmwareUpdates(generation: generation)
            guard sessionCoordinator.isReady(generation: generation) else { return }

            // Clear any pending disconnect notification
            disconnectNotificationTimer?.invalidate()
            disconnectNotificationTimer = nil

            logger.info("Connected to \(device.displayName)")

            // TODO: Track analytics when AnalyticsManager supports device events
            // AnalyticsManager.shared.deviceConnected(deviceType: device.type.rawValue, deviceName: device.name)

        } catch DeviceSessionCoordinatorError.connectionAlreadyActive {
            logger.debug("Ignored duplicate connection request for \(device.displayName)")
        } catch DeviceSessionCoordinatorError.superseded {
            logger.debug("Connection attempt for \(device.displayName) was superseded")
        } catch {
            logger.error("Failed to connect to \(device.displayName): \(error.localizedDescription)")
            errorMessage = "Failed to connect: \(error.localizedDescription)"
        }
    }

    /// Disconnect from the current device
    func disconnect() async {
        guard activeConnection != nil else {
            logger.warning("No active connection to disconnect")
            return
        }

        await sessionCoordinator.disconnect(reconnectAfter: .zero)

        logger.info("Disconnected from device")
    }

    /// Unpair the current device (disconnect and clear pairing)
    func unpair() async {
        await sessionCoordinator.unpair()
        resetSessionPresentation()
        savePairedDevice(nil)

        logger.info("Unpaired device")
    }

    private func resetSessionPresentation() {
        // Cancel battery monitoring
        batterySubscription?.cancel()
        batterySubscription = nil

        batteryLevel = -1
        isDeviceStorageSupported = false
        hasFirmwareUpdate = false
        hasLowBatteryAlerted = false

        // TODO: Track analytics when AnalyticsManager supports device events
        // AnalyticsManager.shared.deviceDisconnected()

        // Schedule disconnect notification
        scheduleDisconnectNotification()
    }

    // MARK: - Auto-Reconnection

    /// Begin the coordinator-owned reconnection policy.
    func startReconnecting() {
        sessionCoordinator.startReconnecting()
    }

    /// Stop pending coordinator-owned reconnection work.
    func stopReconnecting() {
        sessionCoordinator.stopReconnecting()
    }

    // MARK: - Battery Monitoring

    private func startBatteryMonitoring(
        connection: DeviceConnection,
        generation: UInt64
    ) async {
        // Get initial battery level
        let level = await connection.getBatteryLevel()
        if sessionCoordinator.isReady(generation: generation), level >= 0 {
            batteryLevel = level
            checkLowBattery()
        }
        guard sessionCoordinator.isReady(generation: generation) else { return }

        // Start listening for battery updates
        batterySubscription?.cancel()
        batterySubscription = Task { [weak self, weak connection] in
            guard let connection else { return }
            do {
                for try await level in connection.getBatteryLevelStream() {
                    guard !Task.isCancelled, let self else { return }
                    guard self.sessionCoordinator.isReady(generation: generation) else { return }
                    self.batteryLevel = level
                    self.checkLowBattery()
                }
            } catch {
                self?.logger.debug("Battery stream ended: \(error.localizedDescription)")
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

    private func checkStorageSupport(
        connection: DeviceConnection,
        generation: UInt64
    ) async {
        let storageList = await connection.getStorageList()
        guard sessionCoordinator.isReady(generation: generation) else { return }
        isDeviceStorageSupported = !storageList.isEmpty

        // Check for pending storage data to sync
        if isDeviceStorageSupported {
            await checkPendingStorageSync(generation: generation)
        }
    }

    /// Check if device has pending storage data to sync
    private func checkPendingStorageSync(generation: UInt64) async {
        guard let (totalBytes, currentOffset) = await storageDataChecker() else {
            return
        }
        guard sessionCoordinator.isReady(generation: generation) else { return }

        let bytesToSync = totalBytes - currentOffset

        // Only notify if there's significant data (more than 10 seconds worth)
        let minBytesThreshold = 80 * 100 * 10 // 80 bytes/frame * 100 fps * 10 seconds
        if bytesToSync >= minBytesThreshold {
            let mbToSync = Double(bytesToSync) / (1024 * 1024)
            logger.info("Device has \(String(format: "%.1f", mbToSync)) MB of audio data pending sync")

            // Post notification that storage sync is available
            notificationCenter.post(
                name: .storageSyncAvailable,
                object: nil,
                userInfo: ["bytesToSync": bytesToSync]
            )
        }
    }

    // MARK: - Firmware Updates

    private func checkFirmwareUpdates(generation: UInt64) async {
        guard !isFirmwareUpdateInProgress else { return }
        guard sessionCoordinator.isReady(generation: generation) else { return }
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

        await sessionCoordinator.disconnect(reconnectAfter: .seconds(30))
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

    private func sendFallDetectionNotification(data: AccelerometerData) {
        logger.warning("Fall detected! Magnitude: \(data.magnitude)")

        let content = UNMutableNotificationContent()
        content.title = "Fall Detected"
        content.body = "A potential fall was detected by your omi device."
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "fallDetected-\(Date().timeIntervalSince1970)",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
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
        disconnectNotificationTimer?.invalidate()
        batterySubscription?.cancel()
    }
}
