import CoreBluetooth
import Flutter

/// Native CoreBluetooth manager that handles BLE lifecycle, state restoration,
/// reconnection, service discovery, and audio batching.
///
/// Replaces flutter_blue_plus on iOS for better battery efficiency and background reliability.
final class OmiBleManager: NSObject {
    static let shared = OmiBleManager()

    static let restoreIdentifier = "com.omi.ble.restore"

    // MARK: - Properties

    private var centralManager: CBCentralManager!
    private(set) var flutterApi: BleFlutterApi?

    /// Connected/connecting peripherals keyed by UUID string.
    private var peripherals: [String: CBPeripheral] = [:]

    /// Discovered services per peripheral, keyed by peripheral UUID.
    private var discoveredServices: [String: [CBService]] = [:]

    /// Pending read completions keyed by "peripheralUuid:serviceUuid:charUuid".
    private var readCompletions: [String: (Result<FlutterStandardTypedData, Error>) -> Void] = [:]

    /// Pending write completions keyed by "peripheralUuid:serviceUuid:charUuid".
    private var writeCompletions: [String: (Result<Void, Error>) -> Void] = [:]

    /// Whether the user explicitly disconnected (suppress auto-reconnect).
    private var manuallyDisconnected: Set<String> = []

    /// Scanning state.
    private var isScanning = false
    private var scanTimer: Timer?
    /// Queued scan request if Bluetooth wasn't ready when startScan was called.
    private var pendingScan: (timeout: Int, serviceUuids: [String])?

    // MARK: - Initialization

    private override init() {
        super.init()
        NSLog("[OmiBle] Initializing OmiBleManager with restore ID: \(OmiBleManager.restoreIdentifier)")
        centralManager = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [
                CBCentralManagerOptionRestoreIdentifierKey: OmiBleManager.restoreIdentifier,
                CBCentralManagerOptionShowPowerAlertKey: true,
            ]
        )
        NSLog("[OmiBle] CBCentralManager created")
    }

    func setFlutterApi(_ api: BleFlutterApi) {
        flutterApi = api
    }

    // MARK: - Scanning

    func startScan(timeout: Int, serviceUuids: [String]) {
        NSLog("[OmiBle] startScan called, state=\(getBluetoothState()), timeout=\(timeout), serviceUuids=\(serviceUuids)")

        // Queue the scan if Bluetooth isn't ready yet — it will fire once poweredOn
        guard centralManager.state == .poweredOn else {
            NSLog("[OmiBle] BT not ready, queuing scan")
            pendingScan = (timeout: timeout, serviceUuids: serviceUuids)
            return
        }

        pendingScan = nil
        let cbuuids: [CBUUID]? = serviceUuids.isEmpty ? nil : serviceUuids.map { CBUUID(string: $0) }
        isScanning = true
        NSLog("[OmiBle] Starting BLE scan with services=\(String(describing: cbuuids))")
        centralManager.scanForPeripherals(withServices: cbuuids, options: [
            CBCentralManagerScanOptionAllowDuplicatesKey: false,
        ])

        scanTimer?.invalidate()
        if timeout > 0 {
            scanTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(timeout), repeats: false) { [weak self] _ in
                self?.stopScan()
            }
        }
    }

    func stopScan() {
        guard isScanning else { return }
        isScanning = false
        scanTimer?.invalidate()
        scanTimer = nil
        centralManager.stopScan()
    }

    // MARK: - Connection

    func connectPeripheral(uuid: String) {
        manuallyDisconnected.remove(uuid)

        if let peripheral = peripherals[uuid] {
            if peripheral.state == .connected {
                flutterApi?.onPeripheralConnected(peripheralUuid: uuid) { _ in }
                return
            }
            centralManager.connect(peripheral, options: nil)
            return
        }

        // Try to retrieve a known peripheral
        guard let cbUuid = UUID(uuidString: uuid) else { return }
        let retrieved = centralManager.retrievePeripherals(withIdentifiers: [cbUuid])
        if let peripheral = retrieved.first {
            peripheral.delegate = self
            peripherals[uuid] = peripheral
            centralManager.connect(peripheral, options: nil)
        }
    }

    func disconnectPeripheral(uuid: String) {
        manuallyDisconnected.insert(uuid)
        guard let peripheral = peripherals[uuid] else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    func disconnectAllPeripherals() {
        for (uuid, peripheral) in peripherals {
            manuallyDisconnected.insert(uuid)
            centralManager.cancelPeripheralConnection(peripheral)
        }
    }

    func reconnectKnownPeripheral(uuid: String) {
        manuallyDisconnected.remove(uuid)

        guard let cbUuid = UUID(uuidString: uuid) else { return }
        let retrieved = centralManager.retrievePeripherals(withIdentifiers: [cbUuid])
        if let peripheral = retrieved.first {
            peripheral.delegate = self
            peripherals[uuid] = peripheral
            // iOS handles this at the chipset level — zero CPU/radio cost while waiting.
            centralManager.connect(peripheral, options: nil)
        }
    }

    func isPeripheralConnected(uuid: String) -> Bool {
        return peripherals[uuid]?.state == .connected
    }

    // MARK: - Service Discovery

    func discoverServices(peripheralUuid: String) {
        guard let peripheral = peripherals[peripheralUuid], peripheral.state == .connected else { return }
        peripheral.discoverServices(nil)
    }

    // MARK: - Characteristic Operations

    func readCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        completion: @escaping (Result<FlutterStandardTypedData, Error>) -> Void
    ) {
        guard let characteristic = findCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid) else {
            completion(.failure(PigeonError(code: "NOT_FOUND", message: "Characteristic not found", details: nil)))
            return
        }

        let key = "\(peripheralUuid):\(serviceUuid):\(characteristicUuid)".lowercased()
        readCompletions[key] = completion

        peripherals[peripheralUuid]?.readValue(for: characteristic)
    }

    func writeCharacteristic(
        peripheralUuid: String,
        serviceUuid: String,
        characteristicUuid: String,
        data: FlutterStandardTypedData,
        completion: @escaping (Result<Void, Error>) -> Void
    ) {
        guard let characteristic = findCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid) else {
            completion(.failure(PigeonError(code: "NOT_FOUND", message: "Characteristic not found", details: nil)))
            return
        }

        let key = "\(peripheralUuid):\(serviceUuid):\(characteristicUuid)".lowercased()
        let writeType: CBCharacteristicWriteType = characteristic.properties.contains(.writeWithoutResponse) ? .withoutResponse : .withResponse

        if writeType == .withResponse {
            writeCompletions[key] = completion
        }

        peripherals[peripheralUuid]?.writeValue(data.data, for: characteristic, type: writeType)

        if writeType == .withoutResponse {
            completion(.success(()))
        }
    }

    func subscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) {
        guard let characteristic = findCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid) else { return }
        peripherals[peripheralUuid]?.setNotifyValue(true, for: characteristic)
    }

    func unsubscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) {
        guard let characteristic = findCharacteristic(peripheralUuid: peripheralUuid, serviceUuid: serviceUuid, characteristicUuid: characteristicUuid) else { return }
        peripherals[peripheralUuid]?.setNotifyValue(false, for: characteristic)
    }

    // MARK: - Bluetooth State

    func getBluetoothState() -> String {
        switch centralManager.state {
        case .poweredOn: return "on"
        case .poweredOff: return "off"
        case .unauthorized: return "unauthorized"
        case .unsupported: return "unsupported"
        case .resetting: return "resetting"
        case .unknown: return "unknown"
        @unknown default: return "unknown"
        }
    }

    // MARK: - Private Helpers

    private func findCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String) -> CBCharacteristic? {
        guard let services = discoveredServices[peripheralUuid] else { return nil }
        let sUuid = CBUUID(string: serviceUuid)
        let cUuid = CBUUID(string: characteristicUuid)

        guard let service = services.first(where: { $0.uuid == sUuid }) else { return nil }
        return service.characteristics?.first(where: { $0.uuid == cUuid })
    }

    private func peripheralUuidString(_ peripheral: CBPeripheral) -> String {
        return peripheral.identifier.uuidString
    }

    /// Normalize a CBUUID to its full 128-bit string representation.
    /// CoreBluetooth returns "180A" for standard 16-bit UUIDs but Dart sends
    /// "0000180a-0000-1000-8000-00805f9b34fb". This ensures consistent keys.
    private func fullUuidString(_ uuid: CBUUID) -> String {
        if uuid.data.count == 2 {
            // 16-bit UUID → expand to 128-bit Bluetooth Base UUID
            let short = uuid.uuidString // e.g. "180A"
            return "0000\(short)-0000-1000-8000-00805F9B34FB".lowercased()
        } else if uuid.data.count == 4 {
            // 32-bit UUID → expand
            let short = uuid.uuidString
            return "\(short)-0000-1000-8000-00805F9B34FB".lowercased()
        }
        return uuid.uuidString.lowercased()
    }

    // MARK: - Audio Batch Helpers

    private func cleanupPeripheral(_ peripheralUuid: String) {
        discoveredServices.removeValue(forKey: peripheralUuid)

        // Clean up pending completions
        let completionKeys = readCompletions.keys.filter { $0.hasPrefix(peripheralUuid.lowercased()) }
        for key in completionKeys {
            readCompletions[key]?(.failure(PigeonError(code: "DISCONNECTED", message: "Peripheral disconnected", details: nil)))
            readCompletions.removeValue(forKey: key)
        }
        let writeKeys = writeCompletions.keys.filter { $0.hasPrefix(peripheralUuid.lowercased()) }
        for key in writeKeys {
            writeCompletions[key]?(.failure(PigeonError(code: "DISCONNECTED", message: "Peripheral disconnected", details: nil)))
            writeCompletions.removeValue(forKey: key)
        }
    }
}

// MARK: - CBCentralManagerDelegate

extension OmiBleManager: CBCentralManagerDelegate {

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let state = getBluetoothState()
        NSLog("[OmiBle] centralManagerDidUpdateState: \(state), flutterApi=\(flutterApi != nil)")
        flutterApi?.onBluetoothStateChanged(state: state) { _ in }

        // Execute queued scan if Bluetooth just became ready
        if central.state == .poweredOn, let pending = pendingScan {
            NSLog("[OmiBle] Executing queued scan (timeout=\(pending.timeout))")
            startScan(timeout: pending.timeout, serviceUuids: pending.serviceUuids)
        }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        // Restore previously connected peripherals after app relaunch
        if let restoredPeripherals = dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral] {
            var uuids: [String] = []
            for peripheral in restoredPeripherals {
                let uuid = peripheralUuidString(peripheral)
                peripheral.delegate = self
                peripherals[uuid] = peripheral
                uuids.append(uuid)

                // Re-establish connection if not already connected
                if peripheral.state != .connected {
                    central.connect(peripheral, options: nil)
                }
            }
            flutterApi?.onStateRestored(peripheralUuids: uuids) { _ in }
        }
    }

    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        let uuid = peripheralUuidString(peripheral)
        peripheral.delegate = self
        peripherals[uuid] = peripheral

        let serviceUuids = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID])?.map { $0.uuidString } ?? []

        let blePeripheral = BlePeripheral(
            uuid: uuid,
            name: peripheral.name ?? "",
            rssi: Int64(RSSI.intValue),
            serviceUuids: serviceUuids
        )

        flutterApi?.onPeripheralDiscovered(peripheral: blePeripheral) { _ in }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        let uuid = peripheralUuidString(peripheral)
        NSLog("[OmiBle] didConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid)")
        peripheral.delegate = self
        flutterApi?.onPeripheralConnected(peripheralUuid: uuid) { _ in }
        peripheral.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        NSLog("[OmiBle] didFailToConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)
        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: error?.localizedDescription) { _ in }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        NSLog("[OmiBle] didDisconnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)
        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: error?.localizedDescription) { _ in }

        // Auto-reconnect unless manually disconnected
        if !manuallyDisconnected.contains(uuid) {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(200)) { [weak self] in
                guard let self = self else { return }
                // iOS handles this at the BLE chipset level — zero CPU/radio cost while waiting
                self.centralManager.connect(peripheral, options: nil)
            }
        }
    }
}

// MARK: - CBPeripheralDelegate

extension OmiBleManager: CBPeripheralDelegate {

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        let uuid = peripheralUuidString(peripheral)

        guard let services = peripheral.services else { return }
        discoveredServices[uuid] = services

        // Discover characteristics for all services
        for service in services {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        let uuid = peripheralUuidString(peripheral)

        // Check if all services have had their characteristics discovered
        guard let services = peripheral.services else { return }
        let allDiscovered = services.allSatisfy { $0.characteristics != nil }

        if allDiscovered {
            let bleServices = services.map { svc in
                BleService(
                    uuid: self.fullUuidString(svc.uuid),
                    characteristicUuids: svc.characteristics?.map { self.fullUuidString($0.uuid) } ?? []
                )
            }
            flutterApi?.onServicesDiscovered(peripheralUuid: uuid, services: bleServices) { _ in }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        guard let service = characteristic.service else { return }

        let serviceUuid = fullUuidString(service.uuid)
        let charUuid = fullUuidString(characteristic.uuid)
        let key = "\(uuid):\(serviceUuid):\(charUuid)".lowercased()

        // Handle pending read completion
        if let completion = readCompletions[key] {
            readCompletions.removeValue(forKey: key)
            if let error = error {
                completion(.failure(error))
            } else {
                let data = characteristic.value ?? Data()
                completion(.success(FlutterStandardTypedData(bytes: data)))
            }
            return
        }

        // Handle notification
        guard let data = characteristic.value, !data.isEmpty else { return }

        let typedData = FlutterStandardTypedData(bytes: data)
        flutterApi?.onCharacteristicValueUpdated(
            peripheralUuid: uuid,
            serviceUuid: serviceUuid,
            characteristicUuid: charUuid,
            value: typedData
        ) { _ in }
    }

    func peripheral(_ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        guard let service = characteristic.service else { return }

        let key = "\(uuid):\(fullUuidString(service.uuid)):\(fullUuidString(characteristic.uuid))".lowercased()

        if let completion = writeCompletions[key] {
            writeCompletions.removeValue(forKey: key)
            if let error = error {
                completion(.failure(error))
            } else {
                completion(.success(()))
            }
        }
    }
}
