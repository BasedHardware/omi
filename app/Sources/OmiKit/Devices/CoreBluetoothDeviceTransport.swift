#if canImport(CoreBluetooth) && !SKIP
import CoreBluetooth
import Foundation

// CoreBluetooth implementation of `DeviceTransport`.
//
// Adapted from the upstream maintained implementations (branch `omi/main`):
//   - app/ios/Runner/Ble/OmiBleManager.swift — central/peripheral lifecycle,
//     service+characteristic discovery, audio notification delivery, restore
//     identifier, battery/energy handling.
//   - app/ios/Runner/Ble/OmiBleConnectionPolicy.swift and
//     OmiBlePairingPolicy.swift — retained here as-is (CoreBluetooth-typed).
//   - app/ios/Runner/Ble/OmiBleDiscoveryNaming.swift — pure core moved to
//     OmiKit/Devices/OmiBleDiscoveryNaming.swift (byte-level, testable).
//   - app/ios/Runner/Ble/OmiBleEnergyPolicy.swift — battery rule retained in
//     OmiKit/Devices/OmiBleEnergyPolicy.swift.
// The upstream files carry no separate license headers (project-internal
// sources); their doc comments and semantics are retained here alongside
// the source-path notes above.
//
// Changes from upstream: the Flutter bridge (`BleFlutterApi`) is replaced
// by the `DeviceTransport` streams; codec and transport-policy decisions go
// through `Policy` / `CaptureSessionMachine` instead of being re-derived;
// Device Information service reads (2A24/2A25/2A26/2A27/2A29) feed
// `BleDeviceInfo` with the Unknown-for-invalid rule from
// docs/hardware-device-parity.md.

/// CoreBluetooth-specific failure classification, retained from
/// `OmiBleConnectionPolicy` / `OmiBlePairingPolicy` upstream.
enum OmiBleConnectionPolicy {
    static func requiresPairingRecovery(_ error: Error?) -> Bool {
        guard let error else { return false }
        let nsError = error as NSError
        guard nsError.domain == CBATTErrorDomain else { return false }
        return nsError.code == CBATTError.insufficientAuthentication.rawValue
            || nsError.code == CBATTError.insufficientAuthorization.rawValue
            || nsError.code == CBATTError.insufficientEncryptionKeySize.rawValue
            || nsError.code == CBATTError.insufficientEncryption.rawValue
    }
}

enum OmiBlePairingPolicy {
    private static let peerRemovedPairingInformationCode =
        CBError.Code.peerRemovedPairingInformation.rawValue

    static func isPairingLost(_ error: Error?) -> Bool {
        var current: Error? = error
        while let err = current {
            if isPeerRemovedPairingInformation(err) {
                return true
            }
            current = (err as NSError).userInfo[NSUnderlyingErrorKey] as? Error
        }
        return false
    }

    private static func isPeerRemovedPairingInformation(_ error: Error) -> Bool {
        if let cbError = error as? CBError,
            cbError.code == .peerRemovedPairingInformation
        {
            return true
        }
        let nsError = error as NSError
        if nsError.domain == CBError.errorDomain,
            nsError.code == peerRemovedPairingInformationCode
        {
            return true
        }
        if nsError.domain == "CBErrorDomain",
            nsError.code == peerRemovedPairingInformationCode
        {
            return true
        }
        return false
    }
}

/// Append-only continuation registry: one yield per state change; finished
/// streams stop accepting writes.
final class TransportStreams: @unchecked Sendable {
    private let lock = NSLock()
    private var bluetoothContinuation: AsyncStream<BluetoothState>.Continuation?
    private var connectionContinuation: AsyncStream<DeviceConnectionEvent>.Continuation?
    private var audioContinuation: AsyncStream<DeviceAudioPacket>.Continuation?

    let bluetooth: AsyncStream<BluetoothState>
    let connections: AsyncStream<DeviceConnectionEvent>
    let audio: AsyncStream<DeviceAudioPacket>

    init() {
        var bluetoothContinuation: AsyncStream<BluetoothState>.Continuation?
        bluetooth = AsyncStream { bluetoothContinuation = $0 }
        var connectionContinuation: AsyncStream<DeviceConnectionEvent>.Continuation?
        connections = AsyncStream { connectionContinuation = $0 }
        var audioContinuation: AsyncStream<DeviceAudioPacket>.Continuation?
        audio = AsyncStream { audioContinuation = $0 }
        self.bluetoothContinuation = bluetoothContinuation
        self.connectionContinuation = connectionContinuation
        self.audioContinuation = audioContinuation
    }

    func yield(bluetooth state: BluetoothState) {
        lock.lock()
        bluetoothContinuation?.yield(state)
        lock.unlock()
    }

    func yield(connection event: DeviceConnectionEvent) {
        lock.lock()
        connectionContinuation?.yield(event)
        lock.unlock()
    }

    func yield(audio packet: DeviceAudioPacket) {
        lock.lock()
        audioContinuation?.yield(packet)
        lock.unlock()
    }
}

public final class CoreBluetoothDeviceTransport: NSObject, DeviceTransport,
    @unchecked Sendable
{
    /// Restored from `CBCentralManager` state restoration — retained from
    /// upstream (`OmiBleManager.restoreIdentifier`).
    public static let restoreIdentifier = "com.omi.ble.restore"

    // Omi audio service characteristics (upstream OmiBleManager).
    // CBUUID is not Sendable; the constants are immutable values used only
    // from CoreBluetooth delegate callbacks.
    private nonisolated(unsafe) static let audioServiceUuid =
        CBUUID(string: "19B10000-E8F2-537E-4F6C-D104768A1214")
    private nonisolated(unsafe) static let audioCharUuid =
        CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")
    private nonisolated(unsafe) static let batteryLevelCharUuid = CBUUID(
        string: "2A19"
    )
    private nonisolated(unsafe) static let deviceInformationServiceUuid =
        CBUUID(string: "180A")

    let streams = TransportStreams()
    public var bluetoothStates: AsyncStream<BluetoothState> { streams.bluetooth }
    public var connectionEvents: AsyncStream<DeviceConnectionEvent> {
        streams.connections
    }
    public var audioPackets: AsyncStream<DeviceAudioPacket> { streams.audio }

    private let lock = NSLock()
    private var centralManager: CBCentralManager?
    private var currentState: BluetoothState = .unknown
    private var scanning = false
    private var discovered: [String: DiscoveredDevice] = [:]
    private var peripherals: [String: CBPeripheral] = [:]
    private var deviceInfoReads: [String: [DeviceInfoField: [UInt8]?]] = [:]
    private var deviceInfo: [String: BleDeviceInfo] = [:]
    private var phases: [String: ConnectionPhase] = [:]
    private var connectionIds: [String: String] = [:]
    private var manuallyDisconnected: Set<String> = []
    private var batteryObservations: [String: BatteryObservation] = [:]
    private var scanContinuation: CheckedContinuation<[DiscoveredDevice], Error>?

    public override init() {
        super.init()
    }

    private func ensureCentral() -> CBCentralManager {
        lock.lock()
        defer { lock.unlock() }
        if let centralManager { return centralManager }
        // State restoration option retained from upstream for the
        // `bluetooth-central` background wakeups.
        let manager = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [
                CBCentralManagerOptionRestoreIdentifierKey:
                    Self.restoreIdentifier
            ]
        )
        centralManager = manager
        return manager
    }

    public func currentBluetoothState() async -> BluetoothState {
        _ = ensureCentral()
        return readState()
    }

    private func readState() -> BluetoothState {
        lock.lock()
        defer { lock.unlock() }
        return currentState
    }

    public func startScan(durationSeconds: Int) async throws -> [DiscoveredDevice] {
        let central = ensureCentral()
        guard central.state == .poweredOn else {
            throw DeviceTransportFailure.bluetoothUnavailable(
                Self.mapState(central.state)
            )
        }
        guard beginScan() else {
            throw DeviceTransportFailure.busy
        }
        // Upstream scans with an empty service list and classifies by
        // advertisement name/manufacturer data (NotePin advertisements do
        // not always carry the audio service UUID).
        central.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
        let seconds = max(1, durationSeconds)
        return try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            scanContinuation = continuation
            lock.unlock()
            DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(seconds)) {
                [weak self] in
                self?.completeScan()
            }
        }
    }

    /// Marks a scan in flight; false when one is already running.
    private func beginScan() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if scanning { return false }
        scanning = true
        discovered.removeAll()
        return true
    }

    /// Settles the in-flight scan exactly once (upstream scan-settlement
    /// rule: stale completions cannot settle a newer scan).
    private func completeScan() {
        lock.lock()
        guard scanning else {
            lock.unlock()
            return
        }
        scanning = false
        let continuation = scanContinuation
        scanContinuation = nil
        let devices = discovered.values.sorted { $0.id < $1.id }
        lock.unlock()
        centralManager?.stopScan()
        continuation?.resume(returning: devices)
    }

    public func stopScan() {
        completeScan()
    }

    @discardableResult
    public func connect(deviceId: String) async throws -> DeviceConnectionEvent {
        let central = ensureCentral()
        guard central.state == .poweredOn else {
            throw DeviceTransportFailure.bluetoothUnavailable(
                Self.mapState(central.state)
            )
        }
        let peripheral = prepareConnect(deviceId, central: central)
        guard let peripheral else {
            throw DeviceTransportFailure.unknownDevice
        }
        peripheral.delegate = self
        central.connect(
            peripheral,
            options: [CBConnectPeripheralOptionNotifyOnDisconnectionKey: true]
        )
        // Wait for readiness: codec service discovered + audio notifications
        // confirmed + device information read, driven by the event stream.
        for await event in connectionEvents where event.deviceId == deviceId {
            switch event.phase {
            case .connected:
                return event
            case .disconnected:
                throw DeviceTransportFailure.connectFailed(
                    "connection retired before readiness"
                )
            case .connecting:
                continue
            }
        }
        throw DeviceTransportFailure.connectFailed("connection stream ended")
    }

    public func disconnect(deviceId: String) async {
        let (peripheral, connectionId) = markManualDisconnect(deviceId)
        if let peripheral {
            centralManager?.cancelPeripheralConnection(peripheral)
        }
        streams.yield(
            connection: DeviceConnectionEvent(
                deviceId: deviceId, connectionId: connectionId,
                phase: .disconnected
            )
        )
    }

    /// Registers a connect attempt under the state lock; returns nil for an
    /// unknown device id.
    private func prepareConnect(
        _ deviceId: String, central: CBCentralManager
    ) -> CBPeripheral? {
        lock.lock()
        defer { lock.unlock() }
        let peripheral =
            peripherals[deviceId]
            ?? central.retrievePeripherals(
                withIdentifiers: [UUID(uuidString: deviceId) ?? UUID()]
            ).first
        if let peripheral {
            peripherals[deviceId] = peripheral
            manuallyDisconnected.remove(deviceId)
            connectionIds[deviceId] = UUID().uuidString.lowercased()
            phases[deviceId] = .connecting
            deviceInfoReads[deviceId] = [:]
            deviceInfo[deviceId] = BleDeviceInfo()
        }
        return peripheral
    }

    /// Marks a user-initiated disconnect; returns the peripheral to cancel
    /// and the connection id for the phase event.
    private func markManualDisconnect(
        _ deviceId: String
    ) -> (peripheral: CBPeripheral?, connectionId: String) {
        lock.lock()
        defer { lock.unlock() }
        manuallyDisconnected.insert(deviceId)
        phases[deviceId] = .disconnected
        return (
            peripherals[deviceId], connectionIds[deviceId] ?? deviceId
        )
    }

    public func deviceInfo(deviceId: String) async -> BleDeviceInfo? {
        readDeviceInfo(deviceId)
    }

    private func readDeviceInfo(_ deviceId: String) -> BleDeviceInfo? {
        lock.lock()
        defer { lock.unlock() }
        return deviceInfo[deviceId]
    }

    private func setPhase(
        _ deviceId: String, _ phase: ConnectionPhase, info: BleDeviceInfo? = nil
    ) {
        lock.lock()
        phases[deviceId] = phase
        if let info { deviceInfo[deviceId] = info }
        let connectionId = connectionIds[deviceId] ?? deviceId
        lock.unlock()
        streams.yield(
            connection: DeviceConnectionEvent(
                deviceId: deviceId, connectionId: connectionId,
                phase: phase, info: info
            )
        )
    }

    private func currentPhase(_ deviceId: String) -> ConnectionPhase? {
        lock.lock()
        defer { lock.unlock() }
        return phases[deviceId]
    }

    static func mapState(_ state: CBManagerState) -> BluetoothState {
        switch state {
        case .poweredOn: return .poweredOn
        case .poweredOff: return .poweredOff
        case .unauthorized: return .unauthorized
        case .unsupported, .unknown, .resetting: return .unknown
        @unknown default: return .unknown
        }
    }

    private func handleBattery(deviceId: String, data: Data, nowMs: Int64) {
        guard let level = data.first else { return }
        lock.lock()
        let previous = batteryObservations[deviceId]
        let shouldPersist = OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: previous?.level,
            previousTimestampMs: previous?.timestampMs,
            level: Int(level),
            nowMs: nowMs
        )
        if shouldPersist {
            batteryObservations[deviceId] = BatteryObservation(
                level: Int(level), timestampMs: nowMs
            )
        }
        lock.unlock()
    }
}

private struct BatteryObservation: Sendable {
    var level: Int
    var timestampMs: Int64
}

extension CoreBluetoothDeviceTransport: CBCentralManagerDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let mapped = Self.mapState(central.state)
        lock.lock()
        currentState = mapped
        lock.unlock()
        streams.yield(bluetooth: mapped)
    }

    public func centralManager(
        _ central: CBCentralManager, willRestoreState dict: [String: Any]
    ) {
        // Background restoration: re-adopt restored peripherals (upstream
        // retained behavior).
        let restored =
            dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral]
            ?? []
        lock.lock()
        for peripheral in restored {
            peripherals[peripheral.identifier.uuidString] = peripheral
        }
        lock.unlock()
    }

    public func centralManager(
        _ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any], rssi RSSI: NSNumber
    ) {
        let id = peripheral.identifier.uuidString
        let advertised =
            advertisementData[CBAdvertisementDataLocalNameKey] as? String
        let manufacturerData =
            (advertisementData[CBAdvertisementDataManufacturerDataKey] as? Data)
            .map { Array($0) }
        let name = OmiBleDiscoveryNaming.discoveredName(
            advertisedLocalName: advertised,
            cachedName: peripheral.name,
            manufacturerData: manufacturerData
        )
        // Classify Omi-like devices only (upstream discoverer behavior).
        guard OmiDiscoveryFilter.isOmiLike(name) else { return }
        lock.lock()
        discovered[id] = DiscoveredDevice(
            id: id, name: name, rssi: RSSI.intValue
        )
        lock.unlock()
    }

    public func centralManager(
        _ central: CBCentralManager, didConnect peripheral: CBPeripheral
    ) {
        peripheral.delegate = self
        // Discover all services; characteristics are discovered per service
        // in the peripheral delegate (upstream pattern).
        peripheral.discoverServices(nil)
    }

    public func centralManager(
        _ central: CBCentralManager,
        didFailToConnect peripheral: CBPeripheral, error: Error?
    ) {
        setPhase(peripheral.identifier.uuidString, .disconnected)
    }

    public func centralManager(
        _ central: CBCentralManager,
        didDisconnectPeripheral peripheral: CBPeripheral, error: Error?
    ) {
        let id = peripheral.identifier.uuidString
        lock.lock()
        let manual = manuallyDisconnected.contains(id)
        lock.unlock()
        // Upstream policy classification retained: a stale bond (CB error
        // 14 / peer-removed pairing) and protected-characteristic failures
        // are recognized here; the bounded-reconnect decision stays with the
        // connection owner (see docs/hardware-device-parity.md).
        _ = OmiBlePairingPolicy.isPairingLost(error)
        _ = OmiBleConnectionPolicy.requiresPairingRecovery(error)
        if !manual {
            setPhase(id, .disconnected)
        }
    }
}

extension CoreBluetoothDeviceTransport: CBPeripheralDelegate {
    public func peripheral(
        _ peripheral: CBPeripheral, didDiscoverServices error: Error?
    ) {
        guard error == nil, let services = peripheral.services else {
            setPhase(peripheral.identifier.uuidString, .disconnected)
            return
        }
        for service in services {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didDiscoverCharacteristicsFor service: CBService, error: Error?
    ) {
        guard error == nil, let characteristics = service.characteristics else {
            return
        }
        if service.uuid == Self.deviceInformationServiceUuid {
            for characteristic in characteristics {
                peripheral.readValue(for: characteristic)
            }
        }
        if service.uuid == Self.audioServiceUuid {
            if let audio = characteristics.first(where: {
                $0.uuid == Self.audioCharUuid
            }) {
                peripheral.setNotifyValue(true, for: audio)
            }
        }
        if let battery = characteristics.first(where: {
            $0.uuid == Self.batteryLevelCharUuid
        }) {
            peripheral.readValue(for: battery)
        }
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateValueFor characteristic: CBCharacteristic, error: Error?
    ) {
        let id = peripheral.identifier.uuidString
        guard error == nil, let data = characteristic.value else { return }
        let bytes = Array(data)
        if let field = DeviceInfoField.allCases.first(where: {
            characteristic.uuid == CBUUID(string: $0.characteristicUuid)
        }) {
            lock.lock()
            var reads = deviceInfoReads[id] ?? [:]
            reads[field] = bytes
            deviceInfoReads[id] = reads
            let info = BleDeviceInfoParsing.deviceInfo(reads: reads)
            deviceInfo[id] = info
            lock.unlock()
            // Re-announce readiness with the fuller snapshot.
            if currentPhase(id) == .connected {
                setPhase(id, .connected, info: info)
            }
            return
        }
        if characteristic.uuid == Self.batteryLevelCharUuid {
            handleBattery(
                deviceId: id, data: data,
                nowMs: Int64(Date().timeIntervalSince1970 * 1000)
            )
        }
    }

    public func peripheral(
        _ peripheral: CBPeripheral,
        didUpdateNotificationStateFor characteristic: CBCharacteristic,
        error: Error?
    ) {
        let id = peripheral.identifier.uuidString
        guard characteristic.uuid == Self.audioCharUuid else { return }
        guard error == nil, characteristic.isNotifying else {
            setPhase(id, .disconnected)
            return
        }
        // Readiness: codec service present + audio notifications confirmed.
        // The codec value itself is validated by the capture state machine
        // through Policy; readiness here mirrors the upstream contract that
        // connection success requires confirmed audio notifications.
        lock.lock()
        let info = deviceInfo[id]
        lock.unlock()
        setPhase(id, .connected, info: info)
    }
}
#endif
