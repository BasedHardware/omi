import CoreBluetooth
import AVFoundation
import Flutter
import UIKit

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

    /// Peripherals with a stale iOS bond (CB error 14). Suppresses native auto-reconnect
    /// until Dart explicitly calls manageDevice again after the user forgets the device.
    private var pairingLostBlocked: Set<String> = []

    /// Low-frequency RSSI sampling continues for the life of each link.
    private var rssiTimers: [String: Timer] = [:]

    /// Peripheral whose live RSSI graph is currently subscribed by Flutter.
    private var diagnosticsRssiPeripheralUuid: String?
    /// Whether the diagnostics UI currently has an RSSI subscription.
    /// The UUID above remains the authoritative per-peripheral gate.
    var isRssiStreamingEnabled = false

    /// Connection start time per peripheral UUID.
    private var connectionStartTimes: [String: Int64] = [:]

    /// Tracks peripherals that have connected at least once (for reconnection counting).
    private var everConnected: Set<String> = []

    /// Characteristic discovery callbacks arrive once per service and may overlap.
    /// Deduplicate native setup for each physical connection; an explicit Dart
    /// manageDevice call may still replay readiness to the current Flutter engine.
    private var readyNotified: Set<String> = []
    /// Monotonic start time of the latest GATT discovery. Retain it on errors so
    /// a late callback cannot clear the retry bound for a newer attempt.
    private var discoveryStartedAt: [String: TimeInterval] = [:]
    /// One retry is allowed per explicit Flutter connection request.
    private var readyRequests: Set<String> = []
    private var failedReadyRequests: Set<String> = []
    private var discoveryRetries: [String: Int] = [:]
    private var discoveryRetryTasks: [String: DispatchWorkItem] = [:]

    /// Suppresses duplicate recovery callbacks while CoreBluetooth tears down a
    /// link whose protected characteristic rejected the current bond.
    private var pairingRecoveryInFlight: Set<String> = []

    /// Most recent RSSI sample per peripheral, captured in didReadRSSI. Used to
    /// annotate disconnect events so we can tell range/interference-driven drops
    /// apart from disconnects with healthy signal.
    private var lastRssi: [String: Int64] = [:]

    /// Sliding window of recent (timestamp_ms, rssi) samples per peripheral, used
    /// to classify the trajectory before a disconnect (fading vs. sudden vs. gap).
    /// Capped at rssiHistoryLimit — beyond that we drop the oldest.
    private var rssiHistory: [String: [(ts: Int64, rssi: Int64)]] = [:]
    private var lastPacketIndex: [String: Int] = [:]
    private var audioReceived: [String: Int64] = [:]
    private var audioExpected: [String: Int64] = [:]
    private var pendingAudioRecovery: [String: Int64] = [:]
    private var chargingState: [String: Bool] = [:]
    private static let diagnosticsServiceUuid = CBUUID(string: "19B10040-E8F2-537E-4F6C-D104768A1214")
    private static let diagnosticsCharUuid = CBUUID(string: "19B10041-E8F2-537E-4F6C-D104768A1214")
    private static let audioCharUuid = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")

    /// Timestamp of the most recently persisted unexpected disconnect per peripheral.
    /// On the next successful didConnect we backfill `timeToReconnectMs` on that event.
    private var pendingReconnectForEvent: [String: Int64] = [:]

    /// Scanning state.
    private var isScanning = false
    private var scanTimer: Timer?
    /// Queued scan request if Bluetooth wasn't ready when startScan was called.
    private var pendingScan: (timeout: Int, serviceUuids: [String])?

    /// Last battery point written during this process, used to avoid rewriting
    /// the complete UserDefaults history for every notification.
    private var lastPersistedBatteryLevel: [String: Int] = [:]
    private var lastPersistedBatteryTimestampMs: [String: Int64] = [:]
    private var lastPersistedBatteryCharging: [String: Bool] = [:]
    /// UUIDs whose persisted battery history has already been consulted in
    /// this process. This keeps relaunch rehydration to one read per device
    /// without putting UserDefaults on the hot notification path.
    private var batteryBaselineRehydrated: Set<String> = []

    /// Native batch/flash-drain traffic during the current background window.
    /// These packets do not cross Pigeon, so Dart counters cannot observe them.
    private var nativeBackgroundBytesConsumed: [String: Int64] = [:]
    private var nativeBackgroundPacketsConsumed: [String: Int64] = [:]
    private var isBackgroundTelemetryWindowActive = false

    // MARK: - Initialization

    private override init() {
        super.init()
        let defaults = UserDefaults.standard
        if defaults.bool(forKey: "ble_diagnostics_run_open") {
            appendLifecycleEvent("previous_run_unclean")
        }
        defaults.set(true, forKey: "ble_diagnostics_run_open")
        appendLifecycleEvent("app_launch")
        NotificationCenter.default.addObserver(self, selector: #selector(markCleanExit), name: UIApplication.willTerminateNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(powerModeChanged), name: .NSProcessInfoPowerStateDidChange, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(permissionStateChanged), name: UIApplication.didBecomeActiveNotification, object: nil)
        permissionStateChanged()
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

    func markBackgroundTelemetryStart() {
        guard !isBackgroundTelemetryWindowActive else { return }
        nativeBackgroundBytesConsumed.removeAll()
        nativeBackgroundPacketsConsumed.removeAll()
        isBackgroundTelemetryWindowActive = true
    }

    func markBackgroundTelemetryEnd() {
        isBackgroundTelemetryWindowActive = false
    }

    private func recordNativeBackgroundPacket(uuid: String, bytes: Int) {
        guard isBackgroundTelemetryWindowActive else { return }
        nativeBackgroundBytesConsumed[uuid, default: 0] += Int64(bytes)
        nativeBackgroundPacketsConsumed[uuid, default: 0] += 1
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
        pendingScan = nil
        guard isScanning else { return }
        isScanning = false
        scanTimer?.invalidate()
        scanTimer = nil
        centralManager.stopScan()
    }

    // MARK: - Connection

    func connectPeripheral(uuid: String) {
        manuallyDisconnected.remove(uuid)
        pairingLostBlocked.remove(uuid)

        let peripheral: CBPeripheral?
        if let knownPeripheral = peripherals[uuid] {
            peripheral = knownPeripheral
        } else if let cbUuid = UUID(uuidString: uuid) {
            peripheral = centralManager.retrievePeripherals(withIdentifiers: [cbUuid]).first
        } else {
            peripheral = nil
        }

        if let peripheral {
            peripheral.delegate = self
            peripherals[uuid] = peripheral
            failedReadyRequests.remove(uuid)
            readyRequests.insert(uuid)
            discoveryRetries[uuid] = 0
            let completedServices = completedBleServices(for: peripheral)
            switch OmiBleConnectionPolicy.readyRecoveryAction(
                peripheralState: peripheral.state,
                nativeReady: readyNotified.contains(uuid),
                hasCompleteServices: completedServices != nil,
                discoveryInFlight: OmiBleConnectionPolicy.discoveryIsActive(
                    startedAt: discoveryStartedAt[uuid],
                    now: ProcessInfo.processInfo.systemUptime
                )
            ) {
            case .replayReady:
                // A prior ready callback may have raced Dart startup or belonged
                // to a retired Flutter engine. Reconcile on explicit manageDevice.
                if let completedServices {
                    notifyFlutterDeviceReady(uuid: uuid, services: completedServices, source: "replay")
                }
                finishReadyRequest(uuid: uuid)
            case .hydrateReady:
                if let completedServices {
                    completeDeviceReady(peripheral, uuid: uuid, bleServices: completedServices, source: "restored_cache")
                }
            case .discoverServices:
                // Restored links may have no usable GATT snapshot yet. This is
                // one request-bound discovery, with no polling or reconnect.
                readyNotified.remove(uuid)
                discoverServices(for: peripheral, uuid: uuid)
            case .awaitDiscovery:
                // Restoration or didConnect already started the GATT work.
                scheduleDiscoveryRetry(for: peripheral, uuid: uuid)
            case .connect:
                centralManager.connect(peripheral, options: nil)
            }
            return
        }
    }

    private func discoverServices(for peripheral: CBPeripheral, uuid: String) {
        discoveryStartedAt[uuid] = ProcessInfo.processInfo.systemUptime
        peripheral.discoverServices(nil)
        scheduleDiscoveryRetry(for: peripheral, uuid: uuid)
    }

    private func scheduleDiscoveryRetry(for peripheral: CBPeripheral, uuid: String) {
        guard OmiBleConnectionPolicy.discoveryFailureAction(
            peripheralState: peripheral.state,
            nativeReady: readyNotified.contains(uuid),
            requestPending: readyRequests.contains(uuid),
            retries: discoveryRetries[uuid] ?? 0
        ) != .ignore, let startedAt = discoveryStartedAt[uuid] else { return }
        discoveryRetryTasks.removeValue(forKey: uuid)?.cancel()
        let elapsed = ProcessInfo.processInfo.systemUptime - startedAt
        let delay = max(0, OmiBleConnectionPolicy.discoveryRetryAfter - elapsed)
        let task = DispatchWorkItem { [weak self, weak peripheral] in
            guard let self, let peripheral else { return }
            guard self.discoveryStartedAt[uuid] == startedAt else { return }
            self.discoveryRetryTasks.removeValue(forKey: uuid)
            self.retryDiscoveryIfNeeded(for: peripheral, uuid: uuid, reason: "timeout")
        }
        discoveryRetryTasks[uuid] = task
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: task)
    }

    private func retryDiscoveryIfNeeded(for peripheral: CBPeripheral, uuid: String, reason: String) {
        let action = OmiBleConnectionPolicy.discoveryFailureAction(
            peripheralState: peripheral.state,
            nativeReady: readyNotified.contains(uuid),
            requestPending: readyRequests.contains(uuid),
            retries: discoveryRetries[uuid] ?? 0
        )
        guard action != .ignore else { return }
        if let bleServices = completedBleServices(for: peripheral) {
            completeDeviceReady(peripheral, uuid: uuid, bleServices: bleServices, source: "restored_cache")
            return
        }
        guard action == .retry else {
            reportDiscoveryFailure(uuid: uuid, reason: reason)
            return
        }
        discoveryRetries[uuid] = 1
        discoveryRetryTasks.removeValue(forKey: uuid)?.cancel()
        logBle(uuid: uuid, event: "discovery_retry", detail: reason)
        discoverServices(for: peripheral, uuid: uuid)
    }

    private func reportDiscoveryFailure(uuid: String, reason: String) {
        guard failedReadyRequests.insert(uuid).inserted else { return }
        finishReadyRequest(uuid: uuid)
        discoveryStartedAt.removeValue(forKey: uuid)
        logBle(uuid: uuid, event: "discovery_failed", detail: reason)
        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: "gatt_discovery_failed") { [weak self] result in
            if case .failure(let error) = result {
                self?.logBle(uuid: uuid, event: "ready_delivery_failed", detail: "terminal:\(error.code)")
            }
        }
    }

    private func finishReadyRequest(uuid: String) {
        readyRequests.remove(uuid)
        discoveryRetries.removeValue(forKey: uuid)
        discoveryRetryTasks.removeValue(forKey: uuid)?.cancel()
    }

    private func completedBleServices(for peripheral: CBPeripheral) -> [BleService]? {
        guard let services = peripheral.services, !services.isEmpty,
              services.allSatisfy({ $0.characteristics != nil }) else { return nil }
        return services.map { service in
            BleService(
                uuid: fullUuidString(service.uuid),
                characteristicUuids: service.characteristics?.map { fullUuidString($0.uuid) } ?? []
            )
        }
    }

    private func completeDeviceReady(_ peripheral: CBPeripheral, uuid: String, bleServices: [BleService], source: String) {
        guard peripheral.state == .connected, !failedReadyRequests.contains(uuid), let services = peripheral.services,
              readyNotified.insert(uuid).inserted else { return }
        discoveredServices[uuid] = services
        discoveryStartedAt.removeValue(forKey: uuid)
        finishReadyRequest(uuid: uuid)
        notifyFlutterDeviceReady(uuid: uuid, services: bleServices, source: source)
        LimitlessFlashDrainEngine.shared.onDeviceReady(uuid)
        if let diagnostic = services.first(where: { $0.uuid == Self.diagnosticsServiceUuid })?
            .characteristics?.first(where: { $0.uuid == Self.diagnosticsCharUuid }) {
            peripheral.readValue(for: diagnostic)
        }
        if source == "restored_cache" { logBle(uuid: uuid, event: "ready_from_restored_cache", detail: "") }
    }

    private func notifyFlutterDeviceReady(uuid: String, services: [BleService], source: String) {
        guard let flutterApi else {
            logBle(uuid: uuid, event: "ready_delivery_unavailable", detail: source)
            return
        }
        flutterApi.onDeviceReady(peripheralUuid: uuid, services: services) { [weak self] result in
            if case .failure(let error) = result {
                self?.logBle(uuid: uuid, event: "ready_delivery_failed", detail: "\(source):\(error.code)")
            }
        }
        if source == "replay" { logBle(uuid: uuid, event: "ready_replayed", detail: "") }
    }

    func disconnectPeripheral(uuid: String) {
        manuallyDisconnected.insert(uuid)
        pairingLostBlocked.remove(uuid)
        finishReadyRequest(uuid: uuid)
        persistDisconnectEvent(uuid: uuid, reason: "manual", reasonCode: 0, isManual: true, eventType: "disconnect")
        guard let peripheral = peripherals[uuid] else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    func disconnectAllPeripherals() {
        for (uuid, peripheral) in peripherals {
            manuallyDisconnected.insert(uuid)
            finishReadyRequest(uuid: uuid)
            centralManager.cancelPeripheralConnection(peripheral)
        }
    }

    func isPeripheralConnected(uuid: String) -> Bool {
        return peripherals[uuid]?.state == .connected
    }

    /// Re-issue `connect()` on any previously-connected peripheral that isn't
    /// currently connected and wasn't manually disconnected. Scan-discovered
    /// peripherals that never completed a connection are excluded via the
    /// `everConnected` guard so we don't try to connect to unrelated devices
    /// picked up during a scan. Safe to call whenever the app returns to the
    /// foreground — `centralManager.connect` is idempotent and pending connects
    /// cost nothing while iOS waits at the chipset level.
    func reconnectStalePeripherals() {
        guard centralManager.state == .poweredOn else { return }
        for (uuid, peripheral) in peripherals {
            guard everConnected.contains(uuid) else { continue }
            if manuallyDisconnected.contains(uuid) { continue }
            // Only skip if already connected. For peripherals in .connecting state,
            // re-issue connect() to kick CoreBluetooth — the pending attempt may be
            // silently waiting in congested RF. connect() is idempotent on iOS.
            if peripheral.state == .connected { continue }
            NSLog("[OmiBle] Re-issuing connect on foreground for \(uuid), state=\(peripheral.state.rawValue)")
            peripheral.delegate = self
            centralManager.connect(peripheral, options: nil)
        }
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
        let writeType: CBCharacteristicWriteType = characteristic.properties.contains(.write) ? .withResponse : .withoutResponse

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

    // MARK: - RSSI Diagnostics

    func setRssiStreamingEnabled(_ enabled: Bool, uuid: String) {
        isRssiStreamingEnabled = enabled
        if enabled {
            diagnosticsRssiPeripheralUuid = uuid
            if let peripheral = peripherals[uuid], peripheral.state == .connected {
                startRssiDiagnosticsPolling(for: peripheral)
            }
            return
        }

        if diagnosticsRssiPeripheralUuid == uuid {
            diagnosticsRssiPeripheralUuid = nil
            isRssiStreamingEnabled = false
            if let peripheral = peripherals[uuid], peripheral.state == .connected {
                startRssiDiagnosticsPolling(for: peripheral)
            }
        }
    }

    private func startRssiDiagnosticsPolling(for peripheral: CBPeripheral) {
        let uuid = peripheralUuidString(peripheral)
        stopRssiDiagnosticsPolling(uuid: uuid)
        peripheral.readRSSI()
        let interval = 10.0
        rssiTimers[uuid] = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self, weak peripheral] _ in
            guard let self, let peripheral else { return }
            let uuid = self.peripheralUuidString(peripheral)
            guard peripheral.state == .connected else {
                self.stopRssiDiagnosticsPolling(uuid: uuid)
                return
            }
            peripheral.readRSSI()
        }
    }

    private func stopRssiDiagnosticsPolling(uuid: String) {
        rssiTimers.removeValue(forKey: uuid)?.invalidate()
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

    // MARK: - Diagnostics Persistence

    private static let batteryHistoryKeyPrefix = "battery_history_"
    private static let maxBatteryHistoryEntries = 2000
    private static let batteryHistoryRetentionMs: Int64 = 7 * 24 * 3600 * 1000

    private static let batteryLevelCharUuid = CBUUID(string: "2A19")

    private static let diagnosticsKeyPrefix = "ble_diagnostics_disconnect_history_"
    private static let reconnectCountKeyPrefix = "ble_diagnostics_reconnect_count_"
    private static let failToConnectCountKeyPrefix = "ble_diagnostics_fail_to_connect_count_"
    private static let maxDisconnectHistory = 500
    private static let disconnectRetentionMs: Int64 = 7 * 24 * 3600 * 1000
    private static let rssiHistoryLimit = 120

    private static func historyKey(_ uuid: String) -> String { "\(diagnosticsKeyPrefix)\(uuid)" }
    private static func reconnectKey(_ uuid: String) -> String { "\(reconnectCountKeyPrefix)\(uuid)" }
    private static func failToConnectKey(_ uuid: String) -> String { "\(failToConnectCountKeyPrefix)\(uuid)" }

    @objc private func markCleanExit() {
        UserDefaults.standard.set(false, forKey: "ble_diagnostics_run_open")
    }

    @objc private func powerModeChanged() {
        appendLifecycleEvent(ProcessInfo.processInfo.isLowPowerModeEnabled ? "low_power_on" : "low_power_off")
    }

    @objc private func permissionStateChanged() {
        let defaults = UserDefaults.standard
        let mic = String(AVAudioSession.sharedInstance().recordPermission.rawValue)
        let bluetooth = String(CBManager.authorization.rawValue)
        for (name, value) in [("mic", mic), ("bluetooth", bluetooth)] {
            let key = "ble_diagnostics_permission_\(name)"
            if defaults.string(forKey: key) != value {
                defaults.set(value, forKey: key)
                appendLifecycleEvent("\(name)_permission_\(value)")
            }
        }
    }

    private func appendLifecycleEvent(_ name: String) {
        let defaults = UserDefaults.standard
        var events = defaults.array(forKey: "ble_diagnostics_lifecycle") as? [[String: Any]] ?? []
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        events.append(["ts": now, "event": name])
        events.removeAll { ($0["ts"] as? Int64 ?? 0) < now - Self.disconnectRetentionMs }
        defaults.set(Array(events.suffix(500)), forKey: "ble_diagnostics_lifecycle")
    }

    private func logBle(uuid: String, event: String, detail: String) {
        let defaults = UserDefaults.standard
        let key = "ble_diagnostics_log_\(uuid)"
        var entries = defaults.array(forKey: key) as? [[String: Any]] ?? []
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        entries.append(["ts": now, "event": event, "detail": detail])
        entries.removeAll { ($0["ts"] as? Int64 ?? 0) < now - 24 * 3600 * 1000 }
        defaults.set(Array(entries.suffix(500)), forKey: key)
    }

    private func recordAudioPacket(uuid: String, value: Data) {
        guard value.count >= 3 else { return }
        let index = Int(value[0]) | (Int(value[1]) << 8)
        let previous = lastPacketIndex[uuid]
        let delta = previous.map { (index - $0 + 65_536) % 65_536 } ?? 1
        if delta == 0 { return } // Duplicate packet.
        audioReceived[uuid, default: 0] += 1
        audioExpected[uuid, default: 0] += Int64(delta > 4096 ? 1 : delta) // Stream restart becomes a new baseline.
        lastPacketIndex[uuid] = index
        if let marker = pendingAudioRecovery.removeValue(forKey: uuid) {
            let key = Self.historyKey(uuid)
            let defaults = UserDefaults.standard
            var history = defaults.array(forKey: key) as? [[String: Any]] ?? []
            if let i = history.lastIndex(where: { ($0["timestamp"] as? Int64) == marker }) {
                history[i]["lostAudioSeconds"] = Double(max(0, Int64(Date().timeIntervalSince1970 * 1000) - marker)) / 1000
                defaults.set(history, forKey: key)
            }
        }
    }

    private func recordFirmwareDiagnostics(uuid: String, data: Data) {
        guard let value = OmiBleFirmwareDiagnostics.parse(data, timestampMs: Int64(Date().timeIntervalSince1970 * 1000)) else { return }
        let defaults = UserDefaults.standard
        chargingState[uuid] = value["charging"] as? Bool
        let key = "ble_diagnostics_firmware_\(uuid)"
        var reads = defaults.array(forKey: key) as? [[String: Any]] ?? []
        reads.append(value)
        defaults.set(Array(reads.suffix(20)), forKey: key)
        logBle(uuid: uuid, event: "firmware_diagnostics_read", detail: "v\(data[0])")
    }

    func getExtendedDeviceDiagnostics(uuid: String) -> String {
        let defaults = UserDefaults.standard
        let data: [String: Any] = [
            "disconnect_history_v2": defaults.array(forKey: Self.historyKey(uuid)) ?? [],
            "battery_history_v2": defaults.array(forKey: Self.batteryHistoryKey(uuid)) ?? [],
            "rssi_samples": (rssiHistory[uuid] ?? []).map { ["ts": $0.ts, "rssi": $0.rssi] },
            "audio_packets_received": audioReceived[uuid] ?? 0,
            "audio_packets_expected": audioExpected[uuid] ?? 0,
            "connected_at": connectionStartTimes[uuid] ?? 0,
            "firmware_diagnostics": defaults.array(forKey: "ble_diagnostics_firmware_\(uuid)") ?? [],
            "lifecycle_events": defaults.array(forKey: "ble_diagnostics_lifecycle") ?? [],
            "ble_log": defaults.array(forKey: "ble_diagnostics_log_\(uuid)") ?? [],
            "counters_since": defaults.object(forKey: "ble_diagnostics_counters_since_\(uuid)") ?? NSNull(),
        ]
        guard let encoded = try? JSONSerialization.data(withJSONObject: data),
              let result = String(data: encoded, encoding: .utf8) else { return "{}" }
        return result
    }

    /// Sample the UIApplication state from whatever thread we're on. The BLE
    /// callbacks run on the main queue already (centralManager was created with
    /// queue: nil) so this is safe, but we guard anyway for restoration paths.
    private func currentAppState() -> String {
        let state: UIApplication.State
        if Thread.isMainThread {
            state = UIApplication.shared.applicationState
        } else {
            state = DispatchQueue.main.sync { UIApplication.shared.applicationState }
        }
        switch state {
        case .active: return "foreground"
        case .inactive: return "inactive"
        case .background: return "background"
        @unknown default: return ""
        }
    }

    private static func bleReasonString(from error: Error?) -> String {
        if OmiBlePairingPolicy.isPairingLost(error) {
            return "pairing_lost"
        }
        guard let cbError = error as? CBError else { return "clean_disconnect" }
        switch cbError.code {
        case .connectionTimeout: return "connection_timeout"
        case .peripheralDisconnected: return "remote_device_terminated"
        case .connectionFailed: return "connection_failed_instant_passed"
        case .peerRemovedPairingInformation: return "pairing_lost"
        default: return "gatt_error_\(cbError.code.rawValue)"
        }
    }

    private func markPairingLost(uuid: String) {
        pairingLostBlocked.insert(uuid)
        manuallyDisconnected.insert(uuid)
    }

    private func shouldAutoReconnect(uuid: String, pairingLost: Bool) -> Bool {
        !manuallyDisconnected.contains(uuid) && !pairingLost && !pairingLostBlocked.contains(uuid)
    }

    /// Append a disconnect/fail event to the per-device history ring buffer.
    /// `eventType` is "disconnect" for an established link lost, or "fail_to_connect"
    /// for a connect attempt that never reached didConnect.
    private func persistDisconnectEvent(
        uuid: String,
        reason: String?,
        reasonCode: Int,
        isManual: Bool,
        eventType: String
    ) {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.historyKey(uuid)
        var history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let startedAt = connectionStartTimes[uuid] ?? 0
        let durationMs: Int64 = (eventType == "disconnect" && startedAt > 0) ? (now - startedAt) : 0

        let trend = OmiBleRssiDiagnostics.trend(samples: rssiHistory[uuid] ?? [], nowMs: now)
        let event: [String: Any] = [
            "timestamp": now,
            "reason": isManual ? "manual" : (reason ?? "unknown"),
            "reasonCode": reasonCode,
            "isManual": isManual,
            "eventType": eventType,
            "lastRssi": lastRssi[uuid] ?? 0,
            "lastRssiAgeMs": OmiBleRssiDiagnostics.ageMs(samples: rssiHistory[uuid] ?? [], nowMs: now),
            "audioPacketsReceived": audioReceived[uuid] ?? 0,
            "audioPacketsExpected": audioExpected[uuid] ?? 0,
            "connectionDurationMs": durationMs,
            "appState": currentAppState(),
            "timeToReconnectMs": 0,
            "rssiTrend": trend,
        ]
        history.append(event)
        history.removeAll { ($0["timestamp"] as? Int64 ?? 0) < now - Self.disconnectRetentionMs }

        if history.count > OmiBleManager.maxDisconnectHistory {
            history = Array(history.suffix(OmiBleManager.maxDisconnectHistory))
        }

        defaults.set(history, forKey: key)
        logBle(uuid: uuid, event: eventType, detail: event["reason"] as? String ?? "unknown")

        // Remember this event's timestamp so the next successful didConnect can
        // backfill timeToReconnectMs. Only track unexpected (non-manual) events.
        if !isManual {
            pendingReconnectForEvent[uuid] = now
            if eventType == "disconnect" { pendingAudioRecovery[uuid] = now }
        }
    }

    /// On successful didConnect, find the most recent unexpected event for this
    /// peripheral and write the reconnect-latency value into it.
    private func backfillTimeToReconnect(uuid: String) {
        guard let markerTs = pendingReconnectForEvent.removeValue(forKey: uuid) else { return }
        let defaults = UserDefaults.standard
        let key = OmiBleManager.historyKey(uuid)
        guard var history = defaults.array(forKey: key) as? [[String: Any]] else { return }

        // Walk backwards for the matching timestamp. History is small (≤20).
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        for i in stride(from: history.count - 1, through: 0, by: -1) {
            if let ts = history[i]["timestamp"] as? Int64, ts == markerTs {
                var event = history[i]
                event["timeToReconnectMs"] = max(Int64(0), now - markerTs)
                history[i] = event
                defaults.set(history, forKey: key)
                return
            }
        }
    }

    private func incrementReconnectionCount(uuid: String) {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.reconnectKey(uuid)
        let count = defaults.integer(forKey: key)
        defaults.set(count + 1, forKey: key)
    }

    private func incrementFailToConnectCount(uuid: String) {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.failToConnectKey(uuid)
        let count = defaults.integer(forKey: key)
        defaults.set(count + 1, forKey: key)
    }

    func getDeviceDiagnostics(uuid: String) -> BleDeviceDiagnostics {
        let defaults = UserDefaults.standard
        let history = defaults.array(forKey: OmiBleManager.historyKey(uuid)) as? [[String: Any]] ?? []
        let reconnectCount = defaults.integer(forKey: OmiBleManager.reconnectKey(uuid))
        let failToConnectCount = defaults.integer(forKey: OmiBleManager.failToConnectKey(uuid))

        let events = history.map { obj -> BleDisconnectEvent in
            BleDisconnectEvent(
                timestamp: obj["timestamp"] as? Int64 ?? 0,
                reason: obj["reason"] as? String ?? "unknown",
                reasonCode: Int64(obj["reasonCode"] as? Int ?? -1),
                isManual: obj["isManual"] as? Bool ?? false,
                eventType: obj["eventType"] as? String ?? "disconnect",
                lastRssi: obj["lastRssi"] as? Int64 ?? 0,
                connectionDurationMs: obj["connectionDurationMs"] as? Int64 ?? 0,
                appState: obj["appState"] as? String ?? "",
                timeToReconnectMs: obj["timeToReconnectMs"] as? Int64 ?? 0,
                rssiTrend: obj["rssiTrend"] as? String ?? ""
            )
        }

        let connectedAt = connectionStartTimes[uuid] ?? 0

        return BleDeviceDiagnostics(
            disconnectHistory: events,
            reconnectionCount: Int64(reconnectCount),
            connectedAt: connectedAt,
            failToConnectCount: Int64(failToConnectCount),
            nativeBackgroundBytesConsumed: nativeBackgroundBytesConsumed[uuid] ?? 0,
            nativeBackgroundPacketsConsumed: nativeBackgroundPacketsConsumed[uuid] ?? 0
        )
    }

    // MARK: - Battery History

    private static func batteryHistoryKey(_ uuid: String) -> String { "\(batteryHistoryKeyPrefix)\(uuid)" }

    /// The in-memory throttle baseline is lost on process restart; restore it
    /// from the newest persisted history entry before evaluating the first
    /// notification. Without this, a relaunch can rewrite the entire history
    /// ring even when the battery level has not meaningfully changed.
    private func rehydrateBatteryBaselineIfNeeded(uuid: String) {
        guard batteryBaselineRehydrated.insert(uuid).inserted else { return }
        guard let history = UserDefaults.standard.array(forKey: OmiBleManager.batteryHistoryKey(uuid)) as? [[String: Any]],
              let last = history.last,
              let ts = last["ts"] as? Int64,
              let level = last["level"] as? Int
        else { return }
        lastPersistedBatteryLevel[uuid] = level
        lastPersistedBatteryTimestampMs[uuid] = ts
        lastPersistedBatteryCharging[uuid] = last["charging"] as? Bool
    }

    private func persistBatteryReading(uuid: String, level: Int) {
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        rehydrateBatteryBaselineIfNeeded(uuid: uuid)
        let charging = chargingState[uuid]
        guard lastPersistedBatteryCharging[uuid] != charging || OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: lastPersistedBatteryLevel[uuid],
            previousTimestampMs: lastPersistedBatteryTimestampMs[uuid],
            level: level,
            nowMs: now
        ) else { return }

        let defaults = UserDefaults.standard
        let key = OmiBleManager.batteryHistoryKey(uuid)
        var history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let cutoff = now - OmiBleManager.batteryHistoryRetentionMs
        history.removeAll { ($0["ts"] as? Int64 ?? 0) < cutoff }

        history.append(["ts": now, "level": level, "charging": charging as Any? ?? NSNull()])

        if history.count > OmiBleManager.maxBatteryHistoryEntries {
            history = Array(history.suffix(OmiBleManager.maxBatteryHistoryEntries))
        }

        defaults.set(history, forKey: key)
        lastPersistedBatteryLevel[uuid] = level
        lastPersistedBatteryTimestampMs[uuid] = now
        lastPersistedBatteryCharging[uuid] = charging
    }

    func getBatteryHistory(uuid: String) -> [BleBatteryPoint] {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.batteryHistoryKey(uuid)
        let history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let cutoff = now - OmiBleManager.batteryHistoryRetentionMs

        return history.compactMap { obj in
            guard let ts = obj["ts"] as? Int64, let level = obj["level"] as? Int, ts >= cutoff else { return nil }
            return BleBatteryPoint(timestamp: ts, level: Int64(level))
        }
    }

    // MARK: - Audio Batch Helpers

    private func cleanupPeripheral(_ peripheralUuid: String) {
        stopRssiDiagnosticsPolling(uuid: peripheralUuid)
        if diagnosticsRssiPeripheralUuid == peripheralUuid {
            diagnosticsRssiPeripheralUuid = nil
            isRssiStreamingEnabled = false
        }
        discoveredServices.removeValue(forKey: peripheralUuid)
        readyNotified.remove(peripheralUuid)
        failedReadyRequests.remove(peripheralUuid)
        discoveryStartedAt.removeValue(forKey: peripheralUuid)
        finishReadyRequest(uuid: peripheralUuid)

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
        if state == "on" || state == "off" { appendLifecycleEvent("bluetooth_\(state)") }
        if state == "unauthorized" { appendLifecycleEvent("bluetooth_permission_denied") }
        NSLog("[OmiBle] centralManagerDidUpdateState: \(state), flutterApi=\(flutterApi != nil)")
        flutterApi?.onBluetoothStateChanged(state: state) { _ in }

        // Execute queued scan if Bluetooth just became ready
        if central.state == .poweredOn, let pending = pendingScan {
            NSLog("[OmiBle] Executing queued scan (timeout=\(pending.timeout))")
            startScan(timeout: pending.timeout, serviceUuids: pending.serviceUuids)
        }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        appendLifecycleEvent("corebluetooth_restored")
        // CoreBluetooth can relaunch the process directly into the background;
        // applicationDidEnterBackground is not delivered for that lifecycle.
        // Start the native accounting window here so restored notifications are
        // represented in diagnostics instead of silently dropped.
        if UIApplication.shared.applicationState != .active {
            markBackgroundTelemetryStart()
        }

        // Restore previously connected peripherals after app relaunch
        if let restoredPeripherals = dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral] {
            var uuids: [String] = []
            for peripheral in restoredPeripherals {
                let uuid = peripheralUuidString(peripheral)
                peripheral.delegate = self
                peripherals[uuid] = peripheral
                // State-restored peripherals have already connected in a prior
                // process lifetime; count a later connection as a reconnect.
                everConnected.insert(uuid)
                uuids.append(uuid)

                // Re-establish connection if not already connected. CoreBluetooth
                // may restore a complete GATT snapshot, so use it immediately.
                if peripheral.state == .connected {
                    if let bleServices = completedBleServices(for: peripheral) {
                        completeDeviceReady(peripheral, uuid: uuid, bleServices: bleServices, source: "restored_cache")
                    } else {
                        discoverServices(for: peripheral, uuid: uuid)
                    }
                } else if !pairingLostBlocked.contains(uuid) {
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
            name: OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: advertisementData[CBAdvertisementDataLocalNameKey] as? String,
                cachedName: peripheral.name,
                advertisementData: advertisementData
            ),
            rssi: Int64(RSSI.intValue),
            serviceUuids: serviceUuids
        )

        flutterApi?.onPeripheralDiscovered(peripheral: blePeripheral) { _ in }
    }

    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        let uuid = peripheralUuidString(peripheral)
        NSLog("[OmiBle] didConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid)")

        // Track reconnections (not first connect)
        if everConnected.contains(uuid) {
            incrementReconnectionCount(uuid: uuid)
            // Backfill the prior unexpected event with how long it took to recover.
            backfillTimeToReconnect(uuid: uuid)
        }
        everConnected.insert(uuid)
        readyNotified.remove(uuid)
        discoveryStartedAt.removeValue(forKey: uuid)
        pairingRecoveryInFlight.remove(uuid)
        connectionStartTimes[uuid] = Int64(Date().timeIntervalSince1970 * 1000)
        lastRssi.removeValue(forKey: uuid)
        rssiHistory.removeValue(forKey: uuid)
        chargingState.removeValue(forKey: uuid)
        lastPacketIndex.removeValue(forKey: uuid)
        audioReceived[uuid] = 0
        audioExpected[uuid] = 0
        if UserDefaults.standard.object(forKey: "ble_diagnostics_counters_since_\(uuid)") == nil {
            UserDefaults.standard.set(connectionStartTimes[uuid], forKey: "ble_diagnostics_counters_since_\(uuid)")
        }
        startRssiDiagnosticsPolling(for: peripheral)
        logBle(uuid: uuid, event: "connected", detail: "")

        peripheral.delegate = self
        discoverServices(for: peripheral, uuid: uuid)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let isManual = manuallyDisconnected.contains(uuid)
        let pairingLost = OmiBlePairingPolicy.isPairingLost(error)
            || pairingRecoveryInFlight.remove(uuid) != nil
        NSLog("[OmiBle] didFailToConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)

        if pairingLost {
            markPairingLost(uuid: uuid)
        }

        if !isManual {
            let reason = Self.bleReasonString(from: error)
            let code = (error as? CBError)?.code.rawValue ?? -1
            persistDisconnectEvent(
                uuid: uuid,
                reason: reason,
                reasonCode: Int(code),
                isManual: false,
                eventType: "fail_to_connect"
            )
            incrementFailToConnectCount(uuid: uuid)
        }

        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: pairingLost ? "pairing_lost" : error?.localizedDescription) { _ in }

        // Retry previously-connected peripherals — otherwise a failed connect silently
        // drops the user. iOS queues this at the chipset level; it's free while waiting.
        if !isManual, shouldAutoReconnect(uuid: uuid, pairingLost: pairingLost), everConnected.contains(uuid) {
            DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(200)) { [weak self] in
                guard let self = self else { return }
                self.centralManager.connect(peripheral, options: nil)
            }
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let isManual = manuallyDisconnected.contains(uuid)
        let pairingLost = OmiBlePairingPolicy.isPairingLost(error)
            || pairingRecoveryInFlight.remove(uuid) != nil
        NSLog("[OmiBle] didDisconnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)

        if pairingLost {
            markPairingLost(uuid: uuid)
        }

        // Finalize the in-progress batch recording so it's saved + ingestable right away
        // (a plain BLE disconnect never delivers another packet to trigger the gap finalize).
        OmiBatchAudioWriter.shared.stop("disconnected")
        LimitlessFlashDrainEngine.shared.onDeviceDisconnected(uuid)

        if !isManual {
            let reason = Self.bleReasonString(from: error)
            let code = (error as? CBError)?.code.rawValue ?? -1
            // Persist BEFORE clearing connectionStartTimes — the persist step reads
            // it to compute connection_duration_ms.
            persistDisconnectEvent(
                uuid: uuid,
                reason: reason,
                reasonCode: Int(code),
                isManual: false,
                eventType: "disconnect"
            )
        }
        connectionStartTimes.removeValue(forKey: uuid)

        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: pairingLost ? "pairing_lost" : error?.localizedDescription) { _ in }

        // Auto-reconnect unless manually disconnected
        if !isManual, shouldAutoReconnect(uuid: uuid, pairingLost: pairingLost) {
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
        guard !readyNotified.contains(uuid), !failedReadyRequests.contains(uuid) else { return }

        guard error == nil, let services = peripheral.services, !services.isEmpty else {
            logBle(uuid: uuid, event: "service_discovery_failed", detail: error?.localizedDescription ?? "no_services")
            retryDiscoveryIfNeeded(for: peripheral, uuid: uuid, reason: "services_error")
            return
        }
        discoveredServices[uuid] = services

        if let bleServices = completedBleServices(for: peripheral) {
            completeDeviceReady(peripheral, uuid: uuid, bleServices: bleServices, source: "discovery")
            return
        }

        // CoreBluetooth may have restored characteristics for some services.
        for service in services where service.characteristics == nil {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        guard !readyNotified.contains(uuid), !failedReadyRequests.contains(uuid) else { return }

        if let error {
            logBle(uuid: uuid, event: "characteristic_discovery_failed", detail: error.localizedDescription)
            retryDiscoveryIfNeeded(for: peripheral, uuid: uuid, reason: "characteristics_error")
            return
        }

        // Check if all services have had their characteristics discovered.
        if let bleServices = completedBleServices(for: peripheral) {
            completeDeviceReady(peripheral, uuid: uuid, bleServices: bleServices, source: "discovery")
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didReadRSSI RSSI: NSNumber, error: Error?) {
        guard error == nil else { return }
        let uuid = peripheralUuidString(peripheral)
        let value = Int64(RSSI.intValue)
        // Always remember the latest sample — used to annotate disconnect events
        // so we can tell signal-driven drops apart from drops with healthy RSSI.
        lastRssi[uuid] = value

        // Append to the trajectory window used by rssiTrend classification.
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        var samples = rssiHistory[uuid] ?? []
        samples.append((ts: now, rssi: value))
        if samples.count > OmiBleManager.rssiHistoryLimit {
            samples.removeFirst(samples.count - OmiBleManager.rssiHistoryLimit)
        }
        rssiHistory[uuid] = samples

        // Forward to Flutter only while the diagnostics screen has subscribed.
        if isRssiStreamingEnabled, diagnosticsRssiPeripheralUuid == uuid {
            flutterApi?.onRssiUpdate(peripheralUuid: uuid, rssi: value) { _ in }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        guard let service = characteristic.service else { return }

        if OmiBleConnectionPolicy.requiresPairingRecovery(error) {
            beginPairingRecovery(for: peripheral, uuid: uuid)
        }

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

        if characteristic.uuid == Self.diagnosticsCharUuid {
            if error == nil, let value = characteristic.value { recordFirmwareDiagnostics(uuid: uuid, data: value) }
            return
        }

        // Handle notification
        guard let data = characteristic.value, !data.isEmpty else { return }

        if characteristic.uuid == Self.audioCharUuid { recordAudioPacket(uuid: uuid, value: data) }

        if characteristic.uuid == OmiBleManager.batteryLevelCharUuid, let firstByte = data.first {
            persistBatteryReading(uuid: uuid, level: Int(firstByte))
        }

        // Limitless Transcribe Later: while batch mode targets this pendant's RX
        // characteristic, the flash-drain engine consumes the packet natively.
        if LimitlessFlashDrainEngine.shared.handle(
            peripheralUuid: uuid,
            serviceUuid: serviceUuid,
            characteristicUuid: charUuid,
            value: data
        ) {
            recordNativeBackgroundPacket(uuid: uuid, bytes: data.count)
            return
        }

        // Batch (offline) mode: store audio natively and skip the Dart forward so the
        // Flutter engine stays idle. Returns true only for the configured audio
        // characteristic while batch mode is on; everything else falls through.
        if OmiBatchAudioWriter.shared.handle(
            peripheralUuid: uuid,
            serviceUuid: serviceUuid,
            characteristicUuid: charUuid,
            value: data
        ) {
            recordNativeBackgroundPacket(uuid: uuid, bytes: data.count)
            return
        }

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

        if OmiBleConnectionPolicy.requiresPairingRecovery(error) {
            beginPairingRecovery(for: peripheral, uuid: uuid)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let charUuid = fullUuidString(characteristic.uuid)
        if let error = error {
            NSLog("[OmiBle] Failed to update notification state for \(charUuid): \(error.localizedDescription)")
            if OmiBleConnectionPolicy.requiresPairingRecovery(error) {
                beginPairingRecovery(for: peripheral, uuid: uuid)
            }
        } else {
            NSLog("[OmiBle] Notification state updated for \(charUuid): isNotifying=\(characteristic.isNotifying)")
        }
    }

    private func beginPairingRecovery(for peripheral: CBPeripheral, uuid: String) {
        guard pairingRecoveryInFlight.insert(uuid).inserted else { return }
        NSLog("[OmiBle] GATT authentication failed for \(uuid); pairing recovery required")
        manuallyDisconnected.insert(uuid)
        flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: "pairing_lost") { _ in }
        centralManager.cancelPeripheralConnection(peripheral)
    }
}
