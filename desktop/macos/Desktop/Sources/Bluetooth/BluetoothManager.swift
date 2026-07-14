import Combine
import CoreBluetooth
import Foundation
import os.log

enum BluetoothCentralEvent: Equatable, Sendable {
    case connected(lease: BluetoothConnectionLease)
    case failedToConnect(lease: BluetoothConnectionLease, reason: String)
    case disconnected(lease: BluetoothConnectionLease, reason: String?)
}

@MainActor
protocol DeviceBluetoothManaging: AnyObject {
    var currentBluetoothState: CBManagerState { get }
    var currentIsScanning: Bool { get }
    var currentDiscoveredDevices: [BtDevice] { get }
    var bluetoothStatePublisher: AnyPublisher<CBManagerState, Never> { get }
    var isScanningPublisher: AnyPublisher<Bool, Never> { get }
    var discoveredDevicesPublisher: AnyPublisher<[BtDevice], Never> { get }
    var centralEventPublisher: AnyPublisher<BluetoothCentralEvent, Never> { get }

    func prepareForStateUpdates()
    func startScanning(timeout: TimeInterval)
    func stopScanning()
}

/// Manages Bluetooth scanning and device discovery
/// Ported from: omi/app/lib/services/devices.dart and bluetooth_discoverer.dart
@MainActor
final class BluetoothManager: NSObject, ObservableObject {

    // MARK: - Published State

    @Published private(set) var bluetoothState: CBManagerState = .unknown
    @Published private(set) var isScanning = false
    @Published private(set) var discoveredDevices: [BtDevice] = []

    // MARK: - Private Properties

    /// The underlying CBCentralManager
    /// Created lazily to avoid triggering Bluetooth permission dialog at app startup
    private lazy var centralManager: CBCentralManager = {
        let manager = CBCentralManager(delegate: nil, queue: nil)
        manager.delegate = self
        return manager
    }()
    private var scanTimer: Timer?
    private var discoveredPeripherals: [UUID: CBPeripheral] = [:]
    private let centralEventSubject = PassthroughSubject<BluetoothCentralEvent, Never>()
    private let connectionLeases = BluetoothConnectionLeaseRegistry()

    private let logger = Logger(subsystem: "me.omi.desktop", category: "BluetoothManager")

    // MARK: - Singleton

    static let shared = BluetoothManager()

    // MARK: - Initialization

    private override init() {
        super.init()
    }

    // MARK: - Public Methods

    /// Start scanning for supported BLE devices
    /// - Parameter timeout: Scan duration in seconds (default: 5)
    func startScanning(timeout: TimeInterval = 5.0) {
        guard centralManager.state == .poweredOn else {
            logger.warning("Cannot scan: Bluetooth not powered on (state: \(String(describing: self.bluetoothState)))")
            return
        }

        guard !isScanning else {
            logger.debug("Already scanning")
            return
        }

        logger.info("Starting BLE scan for \(timeout) seconds")

        // Clear previous results
        discoveredDevices.removeAll()
        discoveredPeripherals.removeAll()

        isScanning = true

        // Scan for devices advertising our supported service UUIDs
        // Passing nil scans for all devices (needed for name-based detection like PLAUD)
        centralManager.scanForPeripherals(
            withServices: nil,
            options: [
                CBCentralManagerScanOptionAllowDuplicatesKey: false
            ]
        )

        // Set up timeout
        scanTimer?.invalidate()
        scanTimer = Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { [weak self] _ in
            Task { @MainActor in
                self?.stopScanning()
            }
        }
    }

    /// Stop the current scan
    func stopScanning() {
        guard isScanning else { return }

        logger.info("Stopping BLE scan. Found \(self.discoveredDevices.count) devices")

        scanTimer?.invalidate()
        scanTimer = nil

        centralManager.stopScan()
        isScanning = false

        // Sort devices by signal strength
        discoveredDevices.sort { $0.rssi > $1.rssi }
    }

    /// Get the CBPeripheral for a discovered device
    /// - Parameter device: The BtDevice to get the peripheral for
    /// - Returns: The CBPeripheral, or nil if not found
    func peripheral(for device: BtDevice) -> CBPeripheral? {
        guard let uuid = UUID(uuidString: device.id) else { return nil }
        return discoveredPeripherals[uuid]
    }

    /// Check if Bluetooth is available and ready
    var isBluetoothReady: Bool {
        bluetoothState == .poweredOn
    }

    func beginConnection(
        to peripheral: CBPeripheral,
        sessionGeneration: UInt64
    ) throws -> BluetoothConnectionLease {
        guard bluetoothState == .poweredOn else {
            throw BluetoothConnectionLeaseError.centralUnavailable
        }
        let lease = try connectionLeases.begin(
            peripheralID: peripheral.identifier,
            sessionGeneration: sessionGeneration
        )
        centralManager.connect(peripheral, options: nil)
        return lease
    }

    func cancelConnection(
        to peripheral: CBPeripheral,
        lease: BluetoothConnectionLease
    ) {
        guard connectionLeases.requestCancellation(lease) else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    /// Trigger the Bluetooth permission dialog by attempting to scan
    /// This bypasses the poweredOn guard because we need to trigger the system prompt
    func triggerPermissionPrompt() {
        let authStatus = CBCentralManager.authorization
        logger.info("Triggering Bluetooth permission prompt (state: \(self.bluetoothStateDescription), auth: \(self.authorizationDescription))")
        log("BLUETOOTH_TRIGGER: state=\(bluetoothStateDescription), stateRaw=\(bluetoothState.rawValue), auth=\(authorizationDescription), authRaw=\(authStatus.rawValue)")
        // Attempting to scan triggers the permission dialog on macOS
        // even if Bluetooth is not yet authorized
        centralManager.scanForPeripherals(withServices: nil, options: nil)
        // Stop immediately - we just want to trigger the prompt
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.centralManager.stopScan()
            log("BLUETOOTH_TRIGGER_DONE: state=\(self.bluetoothStateDescription), auth=\(self.authorizationDescription)")
        }
    }

    /// Human-readable CBManagerAuthorization description
    var authorizationDescription: String {
        switch CBCentralManager.authorization {
        case .notDetermined: return "Not Determined"
        case .restricted: return "Restricted"
        case .denied: return "Denied"
        case .allowedAlways: return "Allowed Always"
        @unknown default: return "Unknown"
        }
    }

    /// Human-readable Bluetooth state description
    var bluetoothStateDescription: String {
        switch bluetoothState {
        case .unknown: return "Unknown"
        case .resetting: return "Resetting"
        case .unsupported: return "Unsupported"
        case .unauthorized: return "Unauthorized"
        case .poweredOff: return "Powered Off"
        case .poweredOn: return "Powered On"
        @unknown default: return "Unknown"
        }
    }
}

extension BluetoothManager: DeviceBluetoothManaging, BluetoothCentralConnectionControlling {
    var currentBluetoothState: CBManagerState { bluetoothState }
    var currentIsScanning: Bool { isScanning }
    var currentDiscoveredDevices: [BtDevice] { discoveredDevices }
    var bluetoothStatePublisher: AnyPublisher<CBManagerState, Never> {
        $bluetoothState.eraseToAnyPublisher()
    }
    var isScanningPublisher: AnyPublisher<Bool, Never> {
        $isScanning.eraseToAnyPublisher()
    }
    var discoveredDevicesPublisher: AnyPublisher<[BtDevice], Never> {
        $discoveredDevices.eraseToAnyPublisher()
    }
    var centralEventPublisher: AnyPublisher<BluetoothCentralEvent, Never> {
        centralEventSubject.eraseToAnyPublisher()
    }

    func prepareForStateUpdates() {
        _ = centralManager
    }
}

// MARK: - CBCentralManagerDelegate

extension BluetoothManager: CBCentralManagerDelegate {

    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        Task { @MainActor in
            let oldState = self.bluetoothState
            let oldStateDesc = self.bluetoothStateDescription
            self.bluetoothState = central.state
            let newStateDesc = self.bluetoothStateDescription
            self.logger.info("Bluetooth state updated: \(oldStateDesc) -> \(newStateDesc) (raw: \(oldState.rawValue) -> \(central.state.rawValue))")

            // Log detailed state info for debugging
            log("BLUETOOTH_STATE: \(oldStateDesc) -> \(newStateDesc), raw=\(central.state.rawValue), authorization=\(self.authorizationDescription) (\(CBCentralManager.authorization.rawValue))")

            // Track state change in analytics
            AnalyticsManager.shared.bluetoothStateChanged(
                oldState: oldStateDesc,
                newState: newStateDesc,
                oldStateRaw: oldState.rawValue,
                newStateRaw: central.state.rawValue,
                authorization: self.authorizationDescription,
                authorizationRaw: CBCentralManager.authorization.rawValue
            )

            // Stop scanning if Bluetooth becomes unavailable
            if central.state != .poweredOn && self.isScanning {
                self.stopScanning()
            }

            if central.state != .poweredOn {
                let reason = "Bluetooth central became \(newStateDesc)"
                for lease in self.connectionLeases.reset() {
                    self.centralEventSubject.send(
                        .disconnected(lease: lease, reason: reason)
                    )
                }
            }
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        Task { @MainActor in
            // Check if this is a supported device
            guard let device = BtDevice.from(
                peripheral: peripheral,
                advertisementData: advertisementData,
                rssi: RSSI
            ) else {
                return
            }

            // Store the peripheral reference
            self.discoveredPeripherals[peripheral.identifier] = peripheral

            // Update or add to discovered devices
            if let index = self.discoveredDevices.firstIndex(where: { $0.id == device.id }) {
                // Update RSSI for existing device
                self.discoveredDevices[index].rssi = RSSI.intValue
            } else {
                self.logger.debug("Discovered \(device.type.displayName): \(device.displayName) (RSSI: \(RSSI))")
                self.discoveredDevices.append(device)
            }
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didConnect peripheral: CBPeripheral
    ) {
        Task { @MainActor in
            self.logger.info("Connected to \(peripheral.name ?? peripheral.identifier.uuidString)")

            guard let resolution = self.connectionLeases.markConnected(
                peripheralID: peripheral.identifier
            ) else {
                self.logger.warning("Ignoring unleased CoreBluetooth connect callback for \(peripheral.identifier)")
                central.cancelPeripheralConnection(peripheral)
                return
            }

            self.centralEventSubject.send(
                .connected(lease: resolution.lease)
            )
            if resolution.shouldCancel {
                central.cancelPeripheralConnection(peripheral)
            }
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didFailToConnect peripheral: CBPeripheral,
        error: Error?
    ) {
        Task { @MainActor in
            self.logger.error("Failed to connect to \(peripheral.name ?? peripheral.identifier.uuidString): \(error?.localizedDescription ?? "unknown error")")

            guard let lease = self.connectionLeases.finish(
                peripheralID: peripheral.identifier
            ) else {
                self.logger.warning("Ignoring unleased CoreBluetooth connection failure for \(peripheral.identifier)")
                return
            }

            self.centralEventSubject.send(
                .failedToConnect(
                    lease: lease,
                    reason: error?.localizedDescription ?? "Unknown error"
                )
            )
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral,
        error: Error?
    ) {
        Task { @MainActor in
            if let error = error {
                self.logger.warning("Disconnected from \(peripheral.name ?? peripheral.identifier.uuidString) with error: \(error.localizedDescription)")
            } else {
                self.logger.info("Disconnected from \(peripheral.name ?? peripheral.identifier.uuidString)")
            }

            guard let lease = self.connectionLeases.finish(
                peripheralID: peripheral.identifier
            ) else {
                self.logger.warning("Ignoring unleased CoreBluetooth disconnect callback for \(peripheral.identifier)")
                return
            }

            self.centralEventSubject.send(
                .disconnected(
                    lease: lease,
                    reason: error?.localizedDescription
                )
            )
        }
    }
}
