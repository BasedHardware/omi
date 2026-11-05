@preconcurrency import CoreBluetooth
import Foundation

/// CoreBluetooth for the Omi wearable: scan, connect, restore, battery, codec, audio, button.
/// Speaks the Omi protocol directly; the Flutter app needed a generic GATT proxy because Dart
/// drove the protocol. Events are delivered on the main queue through `events`.
public final class OmiDeviceManager: NSObject, @unchecked Sendable {
    public enum BluetoothState: Equatable, Sendable { case unknown, poweredOff, unauthorized, unsupported, ready }

    public struct Discovery: Identifiable, Equatable, Sendable {
        public let id: UUID
        public let name: String
        public let rssi: Int

        public init(id: UUID, name: String, rssi: Int) {
            self.id = id
            self.name = name
            self.rssi = rssi
        }
    }

    public enum Event: Sendable {
        case bluetooth(BluetoothState)
        case discovered(Discovery)
        case connecting(UUID)
        case connected(id: UUID, name: String)
        case disconnected(id: UUID, error: String?)
        case battery(Int)
        case codec(OmiGATT.Codec)
        case info(model: String?, firmware: String?, manufacturer: String?, hardware: String? = nil)
        /// One codec frame with the 3-byte header removed.
        case audio(Data)
        case button(Data)
        /// What the firmware supports (features service); old firmware never sends it.
        case features(OmiGATT.Features)
        case charging(Bool)
        case ledBrightness(Int)
        case micGain(Int)
        case serialNumber(String)
        /// Signal strength of the connected Omi in dBm (answers `readRSSI`).
        case rssi(Int)
    }

    public let events: AsyncStream<Event>
    private let continuation: AsyncStream<Event>.Continuation
    /// Offline storage, unbounded: a dropped data notification would corrupt the transfer.
    public let storageEvents: AsyncStream<OmiStorage.Event>
    private let storageContinuation: AsyncStream<OmiStorage.Event>.Continuation
    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var discovered: [UUID: CBPeripheral] = [:]
    private var wantsScan = false
    /// A device to connect that CoreBluetooth does not know yet: connected when a scan finds it.
    private var wanted: UUID?
    private var deviceInfo: [CBUUID: String] = [:]

    public init(restore: Bool = true) {
        (events, continuation) = AsyncStream.makeStream(of: Event.self, bufferingPolicy: .bufferingNewest(2048))
        (storageEvents, storageContinuation) = AsyncStream.makeStream(of: OmiStorage.Event.self)
        super.init()
        var options: [String: Any] = [CBCentralManagerOptionShowPowerAlertKey: true]
        #if os(iOS)
            if restore { options[CBCentralManagerOptionRestoreIdentifierKey] = OmiGATT.restoreIdentifier }
        #endif
        central = CBCentralManager(delegate: self, queue: .main, options: options)
    }

    public func startScan() {
        wantsScan = true
        guard central.state == .poweredOn else { return }
        // Foreground scan without a service filter: Omi firmware variants differ in what they advertise.
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
    }

    public func stopScan() {
        wantsScan = false
        if central.state == .poweredOn { central.stopScan() }
    }

    /// Connects `id`, waiting as long as it takes for it to come into range. Ignored until
    /// Bluetooth is on (the caller connects again on `.bluetooth(.ready)`). A device CoreBluetooth
    /// does not know is looked for with a scan first.
    public func connect(_ id: UUID) {
        guard central.state == .poweredOn else { return }
        let known = peripheral?.identifier == id ? peripheral : nil
        guard let target = known ?? discovered[id] ?? central.retrievePeripherals(withIdentifiers: [id]).first else {
            wanted = id
            startScan()
            return
        }
        wanted = nil
        stopScan()
        if let peripheral, peripheral !== target { central.cancelPeripheralConnection(peripheral) }
        peripheral = target
        target.delegate = self
        if target.state == .connected {
            // Handed back by state restoration: already linked, only the services are missing.
            centralManager(central, didConnect: target)
            return
        }
        continuation.yield(.connecting(id))
        central.connect(target, options: [CBConnectPeripheralOptionNotifyOnDisconnectionKey: true])
    }

    public func disconnect() {
        wanted = nil
        if let peripheral { central.cancelPeripheralConnection(peripheral) }
        peripheral = nil
    }

    public func readBattery() {
        guard let characteristic = characteristic(OmiGATT.batteryLevel) else { return }
        peripheral?.readValue(for: characteristic)
    }

    /// Asks CoreBluetooth for the connected Omi's signal strength; the answer arrives as `.rssi`.
    public func readRSSI() {
        guard let peripheral, peripheral.state == .connected else { return }
        peripheral.readRSSI()
    }

    /// A storage command (`OmiStorage.Command.bytes`); replies arrive on `storageEvents`.
    public func writeStorage(_ command: Data) {
        guard let characteristic = characteristic(OmiGATT.storageControl) else { return }
        peripheral?.writeValue(command, for: characteristic, type: .withResponse)
    }

    public func readStorageStatus() {
        guard let characteristic = characteristic(OmiGATT.storageStatus) else { return }
        peripheral?.readValue(for: characteristic)
    }

    /// Writes a setting or a haptic pulse (no-op when the firmware lacks the characteristic).
    public func write(_ control: OmiGATT.Control, _ payload: Data) {
        guard let characteristic = characteristic(control.characteristic) else { return }
        peripheral?.writeValue(payload, for: characteristic, type: .withResponse)
    }

    private func characteristic(_ uuid: CBUUID) -> CBCharacteristic? {
        peripheral?.services?.flatMap { $0.characteristics ?? [] }.first { $0.uuid == uuid }
    }

    private static func state(_ state: CBManagerState) -> BluetoothState {
        switch state {
        case .poweredOn: .ready
        case .poweredOff: .poweredOff
        case .unauthorized: .unauthorized
        case .unsupported: .unsupported
        default: .unknown
        }
    }
}

extension OmiDeviceManager: CBCentralManagerDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn, wantsScan { startScan() }
        continuation.yield(.bluetooth(Self.state(central.state)))
    }

    public func centralManager(_: CBCentralManager, willRestoreState dict: [String: Any]) {
        guard let restored = (dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral])?.first else { return }
        peripheral = restored
        restored.delegate = self
    }

    public func centralManager(
        _: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? peripheral.name
        let services = advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []
        guard OmiGATT.isOmi(name: name, advertisedServices: services) else { return }
        discovered[peripheral.identifier] = peripheral
        continuation.yield(.discovered(Discovery(id: peripheral.identifier, name: name ?? "Omi", rssi: RSSI.intValue)))
        if peripheral.identifier == wanted { connect(peripheral.identifier) }
    }

    public func centralManager(_: CBCentralManager, didConnect peripheral: CBPeripheral) {
        // Read fresh on every connection: after a firmware update the revision differs.
        deviceInfo = [:]
        continuation.yield(.connected(id: peripheral.identifier, name: peripheral.name ?? "Omi"))
        peripheral.discoverServices([
            OmiGATT.audioService, OmiGATT.batteryService, OmiGATT.buttonService, OmiGATT.deviceInfoService,
            OmiGATT.storageService, OmiGATT.timeSyncService, OmiGATT.settingsService, OmiGATT.featuresService,
            OmiGATT.hapticService,
        ])
    }

    public func centralManager(_: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: (any Error)?) {
        continuation.yield(.disconnected(id: peripheral.identifier, error: error?.localizedDescription))
    }

    /// Reconnecting is the caller's decision (`DeviceStore`), so it can be tested without radios.
    public func centralManager(_: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: (any Error)?) {
        continuation.yield(.disconnected(id: peripheral.identifier, error: error?.localizedDescription))
    }
}

extension OmiDeviceManager: CBPeripheralDelegate {
    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices _: (any Error)?) {
        for service in peripheral.services ?? [] {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error _: (any Error)?) {
        for characteristic in service.characteristics ?? [] {
            switch characteristic.uuid {
            case OmiGATT.audioCodec, OmiGATT.modelNumber, OmiGATT.firmwareRevision, OmiGATT.manufacturerName, OmiGATT.hardwareRevision:
                peripheral.readValue(for: characteristic)
            case OmiGATT.batteryLevel:
                peripheral.readValue(for: characteristic)
                if characteristic.properties.contains(.notify) { peripheral.setNotifyValue(true, for: characteristic) }
            case OmiGATT.audioData, OmiGATT.buttonData, OmiGATT.storageControl:
                peripheral.setNotifyValue(true, for: characteristic)
            case OmiGATT.storageStatus, OmiGATT.features, OmiGATT.ledDimRatio, OmiGATT.micGain, OmiGATT.serialNumber:
                peripheral.readValue(for: characteristic)
            case OmiGATT.chargingStatus:
                peripheral.readValue(for: characteristic)
                if characteristic.properties.contains(.notify) { peripheral.setNotifyValue(true, for: characteristic) }
            case OmiGATT.timeSyncWrite:
                // Every connect, like the Flutter app: offline recordings carry this clock.
                peripheral.writeValue(OmiStorage.timeSyncPayload(Date()), for: characteristic, type: .withResponse)
            default:
                break
            }
        }
    }

    public func peripheral(_: CBPeripheral, didReadRSSI RSSI: NSNumber, error: (any Error)?) {
        guard error == nil else { return }
        continuation.yield(.rssi(RSSI.intValue))
    }

    public func peripheral(_: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: (any Error)?) {
        if characteristic.uuid == OmiGATT.storageControl, error == nil, characteristic.isNotifying {
            storageContinuation.yield(.ready)
        }
    }

    public func peripheral(_: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: (any Error)?) {
        guard error == nil, let value = characteristic.value else { return }
        switch characteristic.uuid {
        case OmiGATT.storageControl:
            if let notification = OmiStorage.Notification(value) { storageContinuation.yield(.notification(notification)) }
        case OmiGATT.storageStatus:
            if let status = OmiStorage.Status(value) { storageContinuation.yield(.status(status)) }
        case OmiGATT.audioData:
            if let frame = OmiGATT.audioPayload(value) { continuation.yield(.audio(frame.payload)) }
        case OmiGATT.audioCodec:
            // An empty read means the oldest firmware: pcm8.
            let codec = value.first.flatMap { OmiGATT.Codec(rawValue: Int($0)) } ?? .pcm8
            continuation.yield(.codec(codec))
        case OmiGATT.batteryLevel:
            if let level = value.first { continuation.yield(.battery(Int(level))) }
        case OmiGATT.buttonData:
            continuation.yield(.button(value))
        case OmiGATT.features:
            continuation.yield(.features(OmiGATT.Features(value)))
        case OmiGATT.chargingStatus:
            if let charging = OmiGATT.isCharging(value) { continuation.yield(.charging(charging)) }
        case OmiGATT.ledDimRatio:
            if let level = OmiGATT.settingValue(value) { continuation.yield(.ledBrightness(level)) }
        case OmiGATT.micGain:
            if let level = OmiGATT.settingValue(value) { continuation.yield(.micGain(level)) }
        case OmiGATT.serialNumber:
            if let serial = OmiGATT.serialNumber(value) { continuation.yield(.serialNumber(serial)) }
        case OmiGATT.modelNumber, OmiGATT.firmwareRevision, OmiGATT.manufacturerName, OmiGATT.hardwareRevision:
            deviceInfo[characteristic.uuid] = String(data: value, encoding: .utf8)?.trimmingCharacters(in: .controlCharacters)
            continuation.yield(.info(
                model: deviceInfo[OmiGATT.modelNumber],
                firmware: deviceInfo[OmiGATT.firmwareRevision],
                manufacturer: deviceInfo[OmiGATT.manufacturerName],
                hardware: deviceInfo[OmiGATT.hardwareRevision]
            ))
        default:
            break
        }
    }
}

/// What the app needs from the wearable driver (real: `OmiDeviceManager`; tests: a fake).
public protocol DeviceDriving: AnyObject, Sendable {
    var events: AsyncStream<OmiDeviceManager.Event> { get }
    func startScan()
    func stopScan()
    /// A pending connect: completes whenever the device comes into range. Does nothing while
    /// Bluetooth is not ready and never retries after a disconnect on its own.
    func connect(_ id: UUID)
    func disconnect()
    func readBattery()
    /// Offline storage (`OmiStorage`).
    var storageEvents: AsyncStream<OmiStorage.Event> { get }
    func writeStorage(_ command: Data)
    func readStorageStatus()
    /// Settings and haptics (`OmiGATT.Control`).
    func write(_ control: OmiGATT.Control, _ payload: Data)
    /// Signal strength of the connected device (diagnostics); answered with `.rssi`.
    func readRSSI()
}

/// Drivers without offline storage (test fakes) get none.
public extension DeviceDriving {
    var storageEvents: AsyncStream<OmiStorage.Event> {
        AsyncStream { $0.finish() }
    }

    func writeStorage(_: Data) {}
    func readStorageStatus() {}
    func write(_: OmiGATT.Control, _: Data) {}
    func readRSSI() {}
}

extension OmiDeviceManager: DeviceDriving {}
