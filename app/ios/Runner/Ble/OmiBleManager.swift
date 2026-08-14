import CoreBluetooth
import Flutter
import UIKit

/// Keep in sync with `app/lib/services/devices/ble_reconnect_policy.dart`.
enum OmiBleReconnectPolicy {
    static let timeoutBackoffMs: [Int] = [200, 2_000, 10_000, 30_000, 60_000]
    static let backoffCapMs = 60_000
    static let batteryMinDeltaPercent = 5
    static let batteryMinIntervalMs: Int64 = 15 * 60 * 1_000
    static let batteryLowThresholdPercent = 20

    /// 0 = first parked connect (no delay). Later background timeout/fail
    /// attempts walk 200ms → 2s → 10s → 30s → 60s.
    static func reconnectDelayMs(attempt: Int, isBackground: Bool, isTimeoutOrFailToConnect: Bool) -> Int {
        if attempt <= 0 || !isBackground || !isTimeoutOrFailToConnect {
            return 0
        }
        let idx = min(max(attempt - 1, 0), timeoutBackoffMs.count - 1)
        return min(timeoutBackoffMs[idx], backoffCapMs)
    }

    static func shouldPersistBatteryReading(
        previousLevel: Int?,
        lastPersistedAtMs: Int64?,
        newLevel: Int,
        nowMs: Int64
    ) -> Bool {
        guard let previousLevel, let lastPersistedAtMs else { return true }
        let delta = abs(previousLevel - newLevel)
        let elapsed = nowMs - lastPersistedAtMs
        let crossedLow =
            (newLevel < batteryLowThresholdPercent && previousLevel >= batteryLowThresholdPercent) ||
            (newLevel >= batteryLowThresholdPercent && previousLevel < batteryLowThresholdPercent)
        return delta >= batteryMinDeltaPercent || elapsed >= batteryMinIntervalMs || crossedLow
    }
}

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

    /// Consecutive reconnect attempts since the last audio notification.
    private var reconnectAttempt: [String: Int] = [:]
    /// In-flight delayed reconnects — at most one parked connect per peripheral.
    private var pendingReconnectWork: [String: DispatchWorkItem] = [:]
    /// Deadline + peripheral for delayed reconnects, so a CoreBluetooth wake
    /// can fire overdue work if `asyncAfter` was lost to suspend.
    private var pendingReconnectDeadline: [String: Date] = [:]
    private var pendingReconnectPeripheral: [String: CBPeripheral] = [:]

    /// Last battery sample actually written to the plist ring, per peripheral.
    private var lastPersistedBatteryLevel: [String: Int] = [:]
    private var lastPersistedBatteryAtMs: [String: Int64] = [:]

    /// RSSI keep-alive timer — periodic reads prevent connection supervision timeout.
    private var rssiTimer: Timer?

    /// When true, RSSI reads are forwarded to Flutter for the diagnostics graph.
    var isRssiStreamingEnabled = false

    /// Connection start time per peripheral UUID.
    private var connectionStartTimes: [String: Int64] = [:]

    /// Tracks peripherals that have connected at least once (for reconnection counting).
    private var everConnected: Set<String> = []

    /// Most recent RSSI sample per peripheral, captured in didReadRSSI. Used to
    /// annotate disconnect events so we can tell range/interference-driven drops
    /// apart from disconnects with healthy signal.
    private var lastRssi: [String: Int64] = [:]

    /// Sliding window of recent (timestamp_ms, rssi) samples per peripheral, used
    /// to classify the trajectory before a disconnect (fading vs. sudden vs. gap).
    /// Capped at rssiHistoryLimit — beyond that we drop the oldest.
    private var rssiHistory: [String: [(ts: Int64, rssi: Int64)]] = [:]

    /// Timestamp of the most recently persisted unexpected disconnect per peripheral.
    /// On the next successful didConnect we backfill `timeToReconnectMs` on that event.
    private var pendingReconnectForEvent: [String: Int64] = [:]

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

        if let peripheral = peripherals[uuid] {
            if peripheral.state == .connected {
                NSLog("[OmiBle] connectPeripheral: \(uuid) already connected, skipping")
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
        cancelPendingReconnect(uuid: uuid)
        reconnectAttempt[uuid] = 0
        persistDisconnectEvent(uuid: uuid, reason: "manual", reasonCode: 0, isManual: true, eventType: "disconnect")
        guard let peripheral = peripherals[uuid] else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    func disconnectAllPeripherals() {
        for (uuid, peripheral) in peripherals {
            manuallyDisconnected.insert(uuid)
            cancelPendingReconnect(uuid: uuid)
            reconnectAttempt[uuid] = 0
            centralManager.cancelPeripheralConnection(peripheral)
        }
    }

    func isPeripheralConnected(uuid: String) -> Bool {
        return peripherals[uuid]?.state == .connected
    }

    private func cancelPendingReconnect(uuid: String) {
        pendingReconnectWork[uuid]?.cancel()
        pendingReconnectWork.removeValue(forKey: uuid)
        pendingReconnectDeadline.removeValue(forKey: uuid)
        pendingReconnectPeripheral.removeValue(forKey: uuid)
    }

    private func isTimeoutOrFailToConnectReason(_ reason: String) -> Bool {
        return reason == "connection_timeout" ||
            reason == "fail_to_connect" ||
            reason == "connection_failed_instant_passed"
    }

    /// Fire overdue delayed reconnects. CoreBluetooth wake / restore / poweredOn
    /// and foreground entry call this because `DispatchQueue.main.asyncAfter`
    /// does not wake a suspended process.
    func flushDueReconnects() {
        let now = Date()
        let due = pendingReconnectDeadline.compactMap { uuid, deadline -> String? in
            now >= deadline ? uuid : nil
        }
        for uuid in due {
            guard let peripheral = pendingReconnectPeripheral[uuid] else {
                cancelPendingReconnect(uuid: uuid)
                continue
            }
            fireReconnect(uuid: uuid, peripheral: peripheral)
        }
    }

    private func fireReconnect(uuid: String, peripheral: CBPeripheral) {
        cancelPendingReconnect(uuid: uuid)
        if manuallyDisconnected.contains(uuid) { return }
        if peripheral.state == .connected { return }
        centralManager.connect(peripheral, options: nil)
    }

    /// At most one parked `central.connect` per peripheral. First drop is
    /// synchronous (iOS can suspend before `asyncAfter` fires). Later
    /// background timeout/fail storms back off.
    private func scheduleReconnect(peripheral: CBPeripheral, reason: String) {
        let uuid = peripheralUuidString(peripheral)
        if manuallyDisconnected.contains(uuid) { return }
        if reason == "pairing_lost" { return }

        cancelPendingReconnect(uuid: uuid)

        let attempt = reconnectAttempt[uuid] ?? 0
        let isBackground = UIApplication.shared.applicationState != .active
        let delayMs = OmiBleReconnectPolicy.reconnectDelayMs(
            attempt: attempt,
            isBackground: isBackground,
            isTimeoutOrFailToConnect: isTimeoutOrFailToConnectReason(reason)
        )
        reconnectAttempt[uuid] = attempt + 1

        NSLog("[OmiBle] scheduleReconnect uuid=\(uuid) reason=\(reason) attempt=\(attempt) delayMs=\(delayMs) background=\(isBackground)")

        if delayMs <= 0 {
            fireReconnect(uuid: uuid, peripheral: peripheral)
            return
        }

        pendingReconnectPeripheral[uuid] = peripheral
        pendingReconnectDeadline[uuid] = Date().addingTimeInterval(Double(delayMs) / 1000.0)
        let work = DispatchWorkItem { [weak self] in
            self?.flushDueReconnects()
        }
        pendingReconnectWork[uuid] = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(delayMs), execute: work)
    }

    /// Re-issue `connect()` on any previously-connected peripheral that isn't
    /// currently connected and wasn't manually disconnected. Scan-discovered
    /// peripherals that never completed a connection are excluded via the
    /// `everConnected` guard so we don't try to connect to unrelated devices
    /// picked up during a scan. Safe to call whenever the app returns to the
    /// foreground — `centralManager.connect` is idempotent and pending connects
    /// cost nothing while iOS waits at the chipset level.
    func reconnectStalePeripherals() {
        flushDueReconnects()
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

    // MARK: - RSSI diagnostics polling

    /// Periodic `readRSSI` is only for the diagnostics graph. It is not a
    /// connection keep-alive — a 3s timer in the background costs radio/CPU
    /// and does not prevent `connection_timeout`.
    func setRssiStreamingEnabled(_ enabled: Bool, uuid: String) {
        isRssiStreamingEnabled = enabled
        if enabled, let peripheral = peripherals[uuid], peripheral.state == .connected {
            startRssiPolling(for: peripheral)
        } else {
            stopRssiPolling()
        }
    }

    private func startRssiPolling(for peripheral: CBPeripheral) {
        stopRssiPolling()
        rssiTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) { [weak self, weak peripheral] _ in
            guard let peripheral = peripheral, peripheral.state == .connected else {
                self?.stopRssiPolling()
                return
            }
            peripheral.readRSSI()
        }
        peripheral.readRSSI()
    }

    private func stopRssiPolling() {
        rssiTimer?.invalidate()
        rssiTimer = nil
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
    private static let audioCharUuids: Set<CBUUID> = [
        CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214"),
        CBUUID(string: "01000000-1111-1111-1111-111111111111"),
        CBUUID(string: "632DE003-604C-446B-A80F-7963E950F3FB"),
    ]

    private static let diagnosticsKeyPrefix = "ble_diagnostics_disconnect_history_"
    private static let reconnectCountKeyPrefix = "ble_diagnostics_reconnect_count_"
    private static let failToConnectCountKeyPrefix = "ble_diagnostics_fail_to_connect_count_"
    private static let maxDisconnectHistory = 20
    private static let rssiHistoryLimit = 10
    private static let rssiTrendWindowMs: Int64 = 15_000
    private static let rssiTrendFadingDropDb: Int64 = 10

    /// Classify the RSSI trajectory in the window before `nowMs`. See `rssiTrend`
    /// on BleDisconnectEvent for the semantics of each label.
    private static func classifyRssiTrend(samples: [(ts: Int64, rssi: Int64)], nowMs: Int64) -> String {
        let windowStart = nowMs - rssiTrendWindowMs
        let recent = samples.filter { $0.ts >= windowStart }
        // No recent samples — diagnostics RSSI polling was off, so we can't say.
        if recent.isEmpty { return "gap" }
        if recent.count < 3 { return "unknown" }
        // Compare the average of the oldest third to the newest third. A drop of
        // ≥rssiTrendFadingDropDb dB indicates a fading signal (walk-away).
        let third = max(1, recent.count / 3)
        let oldestAvg = recent.prefix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
        let newestAvg = recent.suffix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
        let dropDb = oldestAvg - newestAvg // RSSI is negative; larger drop = more negative newer value
        if dropDb >= rssiTrendFadingDropDb { return "fading" }
        return "sudden"
    }

    private static func historyKey(_ uuid: String) -> String { "\(diagnosticsKeyPrefix)\(uuid)" }
    private static func reconnectKey(_ uuid: String) -> String { "\(reconnectCountKeyPrefix)\(uuid)" }
    private static func failToConnectKey(_ uuid: String) -> String { "\(failToConnectCountKeyPrefix)\(uuid)" }

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
        guard let cbError = error as? CBError else { return "clean_disconnect" }
        switch cbError.code {
        case .connectionTimeout: return "connection_timeout"
        case .peripheralDisconnected: return "remote_device_terminated"
        case .connectionFailed: return "connection_failed_instant_passed"
        case .peerRemovedPairingInformation: return "pairing_lost"
        default: return "gatt_error_\(cbError.code.rawValue)"
        }
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

        let trend = OmiBleManager.classifyRssiTrend(samples: rssiHistory[uuid] ?? [], nowMs: now)
        let event: [String: Any] = [
            "timestamp": now,
            "reason": isManual ? "manual" : (reason ?? "unknown"),
            "reasonCode": reasonCode,
            "isManual": isManual,
            "eventType": eventType,
            "lastRssi": lastRssi[uuid] ?? 0,
            "connectionDurationMs": durationMs,
            "appState": currentAppState(),
            "timeToReconnectMs": 0,
            "rssiTrend": trend,
        ]
        history.append(event)

        if history.count > OmiBleManager.maxDisconnectHistory {
            history = Array(history.suffix(OmiBleManager.maxDisconnectHistory))
        }

        defaults.set(history, forKey: key)

        // Remember this event's timestamp so the next successful didConnect can
        // backfill timeToReconnectMs. Only track unexpected (non-manual) events.
        if !isManual {
            pendingReconnectForEvent[uuid] = now
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
            failToConnectCount: Int64(failToConnectCount)
        )
    }

    // MARK: - Battery History

    private static func batteryHistoryKey(_ uuid: String) -> String { "\(batteryHistoryKeyPrefix)\(uuid)" }

    private func persistBatteryReading(uuid: String, level: Int) {
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        guard OmiBleReconnectPolicy.shouldPersistBatteryReading(
            previousLevel: lastPersistedBatteryLevel[uuid],
            lastPersistedAtMs: lastPersistedBatteryAtMs[uuid],
            newLevel: level,
            nowMs: now
        ) else {
            return
        }

        lastPersistedBatteryLevel[uuid] = level
        lastPersistedBatteryAtMs[uuid] = now

        let defaults = UserDefaults.standard
        let key = OmiBleManager.batteryHistoryKey(uuid)
        var history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let cutoff = now - OmiBleManager.batteryHistoryRetentionMs
        history.removeAll { ($0["ts"] as? Int64 ?? 0) < cutoff }

        history.append(["ts": now, "level": level])

        if history.count > OmiBleManager.maxBatteryHistoryEntries {
            history = Array(history.suffix(OmiBleManager.maxBatteryHistoryEntries))
        }

        defaults.set(history, forKey: key)
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
        stopRssiPolling()
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

        if central.state == .poweredOn {
            flushDueReconnects()
        }

        // Execute queued scan if Bluetooth just became ready
        if central.state == .poweredOn, let pending = pendingScan {
            NSLog("[OmiBle] Executing queued scan (timeout=\(pending.timeout))")
            startScan(timeout: pending.timeout, serviceUuids: pending.serviceUuids)
        }
    }

    func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
        flushDueReconnects()
        // Restore previously connected peripherals after app relaunch
        if let restoredPeripherals = dict[CBCentralManagerRestoredStatePeripheralsKey] as? [CBPeripheral] {
            var uuids: [String] = []
            for peripheral in restoredPeripherals {
                let uuid = peripheralUuidString(peripheral)
                peripheral.delegate = self
                peripherals[uuid] = peripheral
                uuids.append(uuid)
                // Restored peripherals are reconnect-eligible after a later drop.
                everConnected.insert(uuid)

                // Re-establish connection if not already connected
                if peripheral.state != .connected {
                    central.connect(peripheral, options: nil)
                } else {
                    peripheral.discoverServices(nil)
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

        // Track reconnections (not first connect)
        if everConnected.contains(uuid) {
            incrementReconnectionCount(uuid: uuid)
            // Backfill the prior unexpected event with how long it took to recover.
            backfillTimeToReconnect(uuid: uuid)
        }
        everConnected.insert(uuid)
        connectionStartTimes[uuid] = Int64(Date().timeIntervalSince1970 * 1000)
        cancelPendingReconnect(uuid: uuid)

        peripheral.delegate = self
        peripheral.discoverServices(nil)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let isManual = manuallyDisconnected.contains(uuid)
        let pairingLost = (error as? CBError)?.code == .peerRemovedPairingInformation
        NSLog("[OmiBle] didFailToConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)

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

        flushDueReconnects()

        // Retry previously-connected peripherals — otherwise a failed connect silently
        // drops the user. First attempt is a parked chipset-level connect; later
        // background timeout storms back off instead of 200ms forever.
        if !isManual, !pairingLost, everConnected.contains(uuid) {
            let reason = Self.bleReasonString(from: error)
            let reconnectReason = reason == "connection_timeout" ? reason : "fail_to_connect"
            scheduleReconnect(peripheral: peripheral, reason: reconnectReason)
        }
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let isManual = manuallyDisconnected.contains(uuid)
        let pairingLost = (error as? CBError)?.code == .peerRemovedPairingInformation
        NSLog("[OmiBle] didDisconnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        cleanupPeripheral(uuid)

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

        flushDueReconnects()

        // Auto-reconnect unless manually disconnected. Prefer a synchronous
        // parked connect — iOS can suspend before asyncAfter fires.
        if !isManual, !pairingLost {
            let reason = Self.bleReasonString(from: error)
            scheduleReconnect(peripheral: peripheral, reason: reason)
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
            
            flutterApi?.onDeviceReady(peripheralUuid: uuid, services: bleServices) { _ in }
            LimitlessFlashDrainEngine.shared.onDeviceReady(uuid)
            // One sample for disconnect annotation. Do not start a 3s timer
            // here — that was a fake keep-alive and a background battery cost.
            peripheral.readRSSI()
            if isRssiStreamingEnabled {
                startRssiPolling(for: peripheral)
            }
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
        if isRssiStreamingEnabled {
            flutterApi?.onRssiUpdate(peripheralUuid: uuid, rssi: value) { _ in }
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

        if characteristic.uuid == OmiBleManager.batteryLevelCharUuid, let firstByte = data.first {
            persistBatteryReading(uuid: uuid, level: Int(firstByte))
        }

        if OmiBleManager.audioCharUuids.contains(characteristic.uuid) {
            reconnectAttempt[uuid] = 0
        }

        // Limitless Transcribe Later: while batch mode targets this pendant's RX
        // characteristic, the flash-drain engine consumes the packet natively.
        if LimitlessFlashDrainEngine.shared.handle(
            peripheralUuid: uuid,
            serviceUuid: serviceUuid,
            characteristicUuid: charUuid,
            value: data
        ) {
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
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        let charUuid = fullUuidString(characteristic.uuid)
        if let error = error {
            NSLog("[OmiBle] Failed to update notification state for \(charUuid): \(error.localizedDescription)")
        } else {
            NSLog("[OmiBle] Notification state updated for \(charUuid): isNotifying=\(characteristic.isNotifying)")
        }
    }
}
