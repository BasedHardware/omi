import CoreBluetooth
import CoreFoundation
import AVFoundation
import Flutter
import UIKit

/// Native CoreBluetooth manager that handles BLE lifecycle, state restoration,
/// reconnection, service discovery, and audio batching.
///
/// Replaces flutter_blue_plus on iOS for better battery efficiency and background reliability.
final class OmiBleManager: NSObject {
    static let shared = OmiBleManager()
    private let healthStore = OmiDeviceHealthStore()
    func setDeviceHealthPolicy(enabled: Bool, epoch: Int64, retire: Bool) {
        let changed = healthStore.epoch != epoch
        healthStore.setPolicy(enabled: enabled, epoch: epoch, retire: retire)
        if retire || changed || !enabled {
            pendingAudioRecovery.removeAll()
            packetDays.removeAll()
            lastPacketIndex.removeAll()
            audioReceived.removeAll()
            audioExpected.removeAll()
            for uuid in connectionStartTimes.keys { connectionStartTimes[uuid] = CheckedIntegerConversion.epochMs() }
            reconnectDiagnostics.removeAll()
            chargingState.removeAll()
            // Battery throttling must not reuse the previous account's baseline.
            batteryBaselineRehydrated.removeAll()
            lastPersistedBatteryLevel.removeAll()
            lastPersistedBatteryTimestampMs.removeAll()
            lastPersistedBatteryCharging.removeAll()
        }
        if enabled {
            for (uuid, peripheral) in peripherals where peripheral.state == .connected {
                healthStore.start(uuid, at: CheckedIntegerConversion.epochMs())
            }
        }
    }

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

    private struct NotificationRequest {
        let characteristic: CBCharacteristic
        let enabled: Bool
        let token: UUID
        var completions: [(Result<Void, Error>) -> Void]
    }
    private var notificationRequests: [String: NotificationRequest] = [:]
    private var timedOutNotifications: Set<String> = []
    private var captureSessions: [String: OmiBleCaptureSession] = [:]
    private var captureSnapshots: [String: [String: Any]] = [:]
    private var freshConnections: Set<String> = []
    private var captureReconnects: [String: OmiCaptureReconnect] = [:]
    private let captureStorageProgress = OmiCaptureStorageProgress()

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
    private var packetDays: [String: [[String: Any]]] = [:]
    private var pendingAudioRecovery: [String: Int64] = [:]
    private var chargingState: [String: Bool] = [:]
    private var lastDiagnosticsReadUptime: [String: TimeInterval] = [:]
    private static let diagnosticsServiceUuid = CBUUID(string: "19B10040-E8F2-537E-4F6C-D104768A1214")
    private static let diagnosticsCharUuid = CBUUID(string: "19B10041-E8F2-537E-4F6C-D104768A1214")
    private static let audioCharUuid = CBUUID(string: "19B10001-E8F2-537E-4F6C-D104768A1214")

    /// Retains the event that started recovery while connection attempts retry.
    private var reconnectDiagnostics: [String: OmiBleReconnectDiagnostics] = [:]

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
        try? SafeDefaults.store(.bool(true), forKey: "ble_diagnostics_run_open", in: defaults)
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
        // A reset owns this peripheral until a native disconnect and fresh discovery.
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
            if peripheral.state == .connected { healthStore.start(uuid, at: CheckedIntegerConversion.epochMs()) }
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
                ),
                captureResetInProgress: captureReconnects[uuid] != nil
            ) {
            case .awaitCaptureReset:
                if let recovery = captureReconnects[uuid], recovery.stage == .finished {
                    recovery.requestResume(settled: peripheral.state == .disconnected,
                        schedule: { delay, task in
                            self.centralManager.cancelPeripheralConnection(peripheral)
                            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: task)
                        }
                    ) { [weak self, weak recovery] settled in
                        guard let self, let recovery, self.captureReconnects[uuid] === recovery else { return }
                        if settled {
                            self.captureReconnects.removeValue(forKey: uuid)
                            self.connectPeripheral(uuid: uuid)
                        } else {
                            self.finishReadyRequest(uuid: uuid)
                            self.logBle(uuid: uuid, event: "capture_resume_failed", detail: "reset_settlement_timeout")
                            self.flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: "capture_recovery") { _ in }
                            self.captureSessions[uuid]?.emit()
                        }
                    }
                }
                return
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
            // Characteristic callbacks from the first batch can still arrive
            // after the retry starts. CoreBluetooth provides no attempt ID, so
            // only the retry's deadline can declare terminal failure.
            guard reason == "timeout" else { return }
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
        if let recovery = captureReconnects[uuid] {
            recovery.ready(fresh: source == "discovery" && freshConnections.contains(uuid)) { done in
                self.setNotification(uuid, "19B10000-E8F2-537E-4F6C-D104768A1214", Self.audioCharUuid.uuidString, enabled: true) { [weak self] result in
                    guard let self, self.captureReconnects[uuid] === recovery,
                          recovery.stage == .subscribing else { return }
                    done((try? result.get()) != nil)
                    self.captureReconnects.removeValue(forKey: uuid)
                }
            }
        }
        LimitlessFlashDrainEngine.shared.onDeviceReady(uuid)
        readFirmwareDiagnosticsIfDue(peripheral, uuid: uuid)
        if source == "restored_cache" { logBle(uuid: uuid, event: "ready_from_restored_cache", detail: "") }
    }

    private func notifyFlutterDeviceReady(uuid: String, services: [BleService], source: String) {
        let fresh = source == "discovery" && freshConnections.contains(uuid)
        if captureSession(uuid).ready(fresh: fresh, recovery: captureReconnects[uuid]) {
            captureReconnects.removeValue(forKey: uuid)
        }
        guard let flutterApi else {
            logBle(uuid: uuid, event: "ready_delivery_unavailable", detail: source)
            return
        }
        flutterApi.onDeviceReady(peripheralUuid: uuid, services: services) { [weak self] result in
            if case .failure(let error) = result {
                self?.logBle(uuid: uuid, event: "ready_delivery_failed", detail: "\(source):\(error.code)")
            }
        }
        if captureReconnects[uuid]?.stage == .finished { captureSessions[uuid]?.emit() }
        if source == "replay" { logBle(uuid: uuid, event: "ready_replayed", detail: "") }
    }

    func disconnectPeripheral(uuid: String) {
        persistDisconnectEvent(uuid: uuid, reason: "manual", reasonCode: 0, isManual: true, eventType: "disconnect")
        manuallyDisconnected.insert(uuid)
        setCaptureAuthorized(uuid: uuid, authorized: false)
        captureReconnects.removeValue(forKey: uuid)?.finish(false)
        pairingLostBlocked.remove(uuid)
        finishReadyRequest(uuid: uuid)
        guard let peripheral = peripherals[uuid] else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    func disconnectAllPeripherals() {
        for (uuid, peripheral) in peripherals {
            persistDisconnectEvent(uuid: uuid, reason: "manual", reasonCode: 0, isManual: true, eventType: "disconnect")
            manuallyDisconnected.insert(uuid)
            reconnectDiagnostics.removeValue(forKey: uuid)
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

    func subscribeCharacteristic(peripheralUuid: String, serviceUuid: String, characteristicUuid: String,
                                 completion: @escaping (Result<Void, Error>) -> Void) {
        setNotification(peripheralUuid, serviceUuid, characteristicUuid, enabled: true, completion: completion)
    }

    private func setNotification(_ uuid: String, _ service: String, _ characteristicUuid: String,
                                 enabled: Bool, completion: @escaping (Result<Void, Error>) -> Void) {
        guard let peripheral = peripherals[uuid], peripheral.state == .connected,
              let characteristic = findCharacteristic(peripheralUuid: uuid, serviceUuid: service, characteristicUuid: characteristicUuid),
              characteristic.properties.contains(.notify) || characteristic.properties.contains(.indicate) else {
            if CBUUID(string: characteristicUuid) == Self.audioCharUuid { captureSession(uuid).subscribed(false) }
            logBle(uuid: uuid, event: "subscription_failed", detail: "missing_or_disconnected:\(characteristicUuid)")
            completion(.failure(PigeonError(code: "NOT_FOUND", message: "Connected notification characteristic not found", details: nil)))
            return
        }
        let key = "\(uuid):\(service):\(characteristicUuid)".lowercased()
        guard !timedOutNotifications.contains(key) else {
            completion(.failure(PigeonError(code: "SUBSCRIPTION_TIMEOUT", message: "Fresh connection required after subscription timeout", details: nil)))
            return
        }
        if var pending = notificationRequests[key] {
            guard pending.enabled == enabled, pending.characteristic === characteristic else {
                completion(.failure(PigeonError(code: "BUSY", message: "Notification change already pending", details: nil)))
                return
            }
            pending.completions.append(completion)
            notificationRequests[key] = pending
            return
        }
        let token = UUID()
        notificationRequests[key] = NotificationRequest(characteristic: characteristic, enabled: enabled, token: token, completions: [completion])
        logBle(uuid: uuid, event: "subscription_requested", detail: "\(characteristicUuid):\(enabled)")
        peripheral.setNotifyValue(enabled, for: characteristic)
        DispatchQueue.main.asyncAfter(deadline: .now() + OmiCaptureHealth.Policy.operationTimeout) { [weak self] in
            guard let self, self.notificationRequests[key]?.token == token else { return }
            self.timedOutNotifications.insert(key)
            self.finishNotification(key, uuid: uuid, error: PigeonError(code: "SUBSCRIPTION_TIMEOUT", message: "Notification state was not confirmed", details: nil))
        }
    }

    private func finishNotification(_ key: String, uuid: String, error: Error?) {
        guard let request = notificationRequests.removeValue(forKey: key) else { return }
        let confirmed = error == nil && request.characteristic.isNotifying == request.enabled
        let resultError = error ?? (confirmed ? nil : PigeonError(code: "SUBSCRIPTION_FAILED", message: "Unexpected notification state", details: nil))
        logBle(uuid: uuid, event: confirmed ? "subscription_confirmed" : "subscription_failed",
               detail: "\(request.characteristic.uuid):\(request.enabled):\(resultError?.localizedDescription ?? "")")
        if request.characteristic.uuid == Self.audioCharUuid {
            captureSession(uuid).subscribed(confirmed && request.enabled)
        }
        for completion in request.completions {
            if let resultError { completion(.failure(resultError)) } else { completion(.success(())) }
        }
    }

    func setCaptureAuthorized(uuid: String, authorized: Bool) {
        captureSession(uuid).authorize(authorized)
        if !authorized { captureReconnects[uuid]?.finish(false) }
    }

    private let ingressPolicyDecoder = CaptureAdmissionPolicyDecoder()

    private func captureSession(_ uuid: String) -> OmiBleCaptureSession {
        if let session = captureSessions[uuid] { return session }
        let health = OmiCaptureHealth(record: OmiCaptureHealthStore.load(uuid)) {
            OmiCaptureHealthStore.save($0, uuid: uuid)
        }
        let session = OmiBleCaptureSession(
            health: health,
            permitted: { [weak self] in
                guard let self else { return false }
                return !CaptureAdmissionPolicy.load(from: .standard, decoder: self.ingressPolicyDecoder).muted
            },
            linkAvailable: { [weak self] in
                self?.captureStorageProgress.isActive(uuid, now: ProcessInfo.processInfo.systemUptime) != true
            },
            repair: { [weak self] done in
                guard let self else { done(false); return }
                let service = "19B10000-E8F2-537E-4F6C-D104768A1214"
                let audio = Self.audioCharUuid.uuidString
                self.setNotification(uuid, service, audio, enabled: false) { result in
                    guard case .success = result, self.captureSessions[uuid]?.isAuthorized == true else { done(false); return }
                    self.setNotification(uuid, service, audio, enabled: true) { done((try? $0.get()) != nil) }
                }
            },
            reconnect: { [weak self] done in self?.recoverCaptureConnection(uuid: uuid, completion: done) },
            publish: { [weak self] snapshot in
                guard let self else { return }
                let previous = self.captureSnapshots[uuid]
                self.captureSnapshots[uuid] = snapshot
                if previous?["reason"] as? String != snapshot["reason"] as? String ||
                    previous?["generation"] as? String != snapshot["generation"] as? String ||
                    previous?["subscription_confirmed"] as? Bool != snapshot["subscription_confirmed"] as? Bool ||
                    previous?["recovery_outcome"] as? String != snapshot["recovery_outcome"] as? String {
                    self.logBle(uuid: uuid, event: "capture_health", detail: "\(snapshot["phase"] ?? ""):\(snapshot["reason"] ?? "")")
                    var history = UserDefaults.standard.array(forKey: "ble_capture_health_\(uuid)") as? [[String: Any]] ?? []
                    history.append(snapshot)
                    self.persistPropertyListRecords(Array(history.suffix(80)), forKey: "ble_capture_health_\(uuid)", in: .standard)
                }
                if let data = try? SafeJSON.data(withJSONObject: snapshot), let json = String(data: data, encoding: .utf8) {
                    self.flutterApi?.onCaptureHealth(peripheralUuid: uuid, snapshot: json) { _ in }
                }
            }
        )
        captureSessions[uuid] = session
        return session
    }

    private func recoverCaptureConnection(uuid: String, completion: @escaping (Bool) -> Void) {
        guard captureReconnects[uuid] == nil, let peripheral = peripherals[uuid],
              peripheral.state == .connected, !manuallyDisconnected.contains(uuid),
              !captureStorageProgress.isActive(uuid, now: ProcessInfo.processInfo.systemUptime),
              !CaptureAdmissionPolicy.load(from: .standard).muted else { completion(false); return }
        let recovery = captureSession(uuid).reconnectTransaction(
            connected: { [weak peripheral] in peripheral?.state == .connected },
            connect: { [weak self, weak peripheral] in
                guard let self, let peripheral else { return }
                // Never adopt cached readiness here: disconnect has been observed.
                self.centralManager.connect(peripheral, options: nil)
            },
            reportLink: { [weak self] connected in
                guard let self, !connected else { return }
                self.flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid,
                    error: self.manuallyDisconnected.contains(uuid) ? nil : "capture_recovery") { _ in }
            },
            completion: completion
        )
        captureReconnects[uuid] = recovery
        logBle(uuid: uuid, event: "capture_reconnect_requested", detail: "")
        centralManager.cancelPeripheralConnection(peripheral)
        DispatchQueue.main.asyncAfter(deadline: .now() + OmiCaptureHealth.Policy.reconnectTimeout) { [weak self, weak recovery] in
            guard let self, let recovery, self.captureReconnects[uuid] === recovery,
                  recovery.stage != .finished else { return }
            self.logBle(uuid: uuid, event: "capture_reconnect_failed", detail: "timeout")
            // Retain the tombstone until the radio callback, preventing an
            // automatic reconnect outside the durable budget.
            recovery.finish(false)
        }
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
    // 15-minute reads over the worst-case catch-up window: 4/hour * 24 * 8.
    // maybeEmit can roll up yesterday - 6, whose start is nearly eight days old
    // when the app runs late in the current day, so the ring must cover the
    // seven prior days plus the current partial day.
    private static let maxFirmwareDiagnosticsEntries = 768

    private static let diagnosticsKeyPrefix = "ble_diagnostics_disconnect_history_"
    private static let reconnectCountKeyPrefix = "ble_diagnostics_reconnect_count_"
    private static let failToConnectCountKeyPrefix = "ble_diagnostics_fail_to_connect_count_"
    private static let maxDisconnectHistory = 500
    private static let disconnectRetentionMs: Int64 = 7 * 24 * 3600 * 1000
    private static let rssiHistoryLimit = 120

    private static func historyKey(_ uuid: String) -> String { "\(diagnosticsKeyPrefix)\(uuid)" }
    private static func reconnectKey(_ uuid: String) -> String { "\(reconnectCountKeyPrefix)\(uuid)" }
    private static func failToConnectKey(_ uuid: String) -> String { "\(failToConnectCountKeyPrefix)\(uuid)" }

    @discardableResult
    private func persistPropertyListRecords(_ records: [[String: Any]], forKey key: String, in defaults: UserDefaults) -> Bool {
        guard healthStore.enabled else { return false }
        func value(_ object: Any) -> PlistValue? {
            if let string = object as? String { return .string(string) }
            if let date = object as? Date { return .date(date) }
            if let data = object as? Data { return .data(data) }
            if let number = object as? NSNumber {
                if CFGetTypeID(number) == CFBooleanGetTypeID() { return .bool(number.boolValue) }
                let type = String(cString: number.objCType)
                if type == "f" || type == "d" { return .double(number.doubleValue) }
                if ["q", "Q"].contains(type) { return .int64(number.int64Value) }
                return .int(number.intValue)
            }
            if let array = object as? [Any] {
                let values = array.compactMap(value)
                return values.count == array.count ? .array(values) : nil
            }
            if let dictionary = object as? [String: Any] {
                var values: [String: PlistValue] = [:]
                for (key, element) in dictionary {
                    guard let converted = value(element) else { return nil }
                    values[key] = converted
                }
                return .dictionary(values)
            }
            return nil
        }
        let typed = records.compactMap { record -> [String: PlistValue]? in
            var result: [String: PlistValue] = [:]
            for (key, element) in record {
                guard let converted = value(element) else { return nil }
                result[key] = converted
            }
            return result
        }
        guard typed.count == records.count else { return false }
        do {
            try SafeDefaults.setPlistRecords(typed, forKey: key, in: defaults)
            return true
        } catch {
            return false
        }
    }

    @objc private func markCleanExit() {
        try? SafeDefaults.store(.bool(false), forKey: "ble_diagnostics_run_open")
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
                try? SafeDefaults.store(.string(value), forKey: key, in: defaults)
                appendLifecycleEvent("\(name)_permission_\(value)")
            }
        }
    }

    private func appendLifecycleEvent(_ name: String) {
        guard healthStore.enabled else { return }
        let defaults = UserDefaults.standard
        var events = defaults.array(forKey: "ble_diagnostics_lifecycle") as? [[String: Any]] ?? []
        let now = CheckedIntegerConversion.epochMs()
        events.append(["ts": now, "event": name])
        events.removeAll { ($0["ts"] as? Int64 ?? 0) < now - Self.disconnectRetentionMs }
        persistPropertyListRecords(Array(events.suffix(500)), forKey: "ble_diagnostics_lifecycle", in: defaults)
    }

    private func logBle(uuid: String, event: String, detail: String) {
        guard healthStore.enabled else { return }
        let defaults = UserDefaults.standard
        let key = "ble_diagnostics_log_\(uuid)"
        var entries = defaults.array(forKey: key) as? [[String: Any]] ?? []
        let now = CheckedIntegerConversion.epochMs()
        entries.append(["ts": now, "event": event, "detail": detail])
        entries.removeAll { ($0["ts"] as? Int64 ?? 0) < now - 24 * 3600 * 1000 }
        persistPropertyListRecords(Array(entries.suffix(500)), forKey: key, in: defaults)
    }

    private func recordAudioPacket(uuid: String, value: Data) {
        guard healthStore.enabled else { return }
        guard value.count >= 3 else { return }
        let index = Int(value[0]) | (Int(value[1]) << 8)
        let previous = lastPacketIndex[uuid]
        let delta = previous.map { (index - $0 + 65_536) % 65_536 } ?? 1
        if delta == 0 { return } // Duplicate packet.
        audioReceived[uuid, default: 0] += 1
        audioExpected[uuid, default: 0] += Int64(delta > 4096 ? 1 : delta) // Stream restart becomes a new baseline.
        lastPacketIndex[uuid] = index
        let defaults = UserDefaults.standard
        let now = CheckedIntegerConversion.epochMs()
        guard let day = CheckedIntegerConversion.int64(Calendar.current.startOfDay(for: Date()).timeIntervalSince1970 * 1000) else { return }
        var days = packetDays[uuid] ?? (defaults.array(forKey: "ble_packet_days_\(uuid)") as? [[String: Any]] ?? [])
        if days.last?["ts"] as? Int64 != day {
            var point: [String: Any] = ["ts": day, "received": Int64(0), "expected": Int64(0)]
            point["identity_epoch"] = healthStore.epoch
        point["app_build"] = OmiDeviceHealthStore.build
            point["firmware"] = defaults.string(forKey: "ble_observed_firmware_\(uuid)")
            days.append(point)
        }
        let i = days.count - 1
        days[i]["received"] = (days[i]["received"] as? Int64 ?? 0) + 1
        days[i]["expected"] = (days[i]["expected"] as? Int64 ?? 0) + Int64(delta > 4096 ? 1 : delta)
        packetDays[uuid] = Array(days.suffix(8))
        if let marker = healthStore.openSince(uuid) {
            let key = Self.historyKey(uuid)
            let defaults = UserDefaults.standard
            var history = defaults.array(forKey: key) as? [[String: Any]] ?? []
            if let i = history.lastIndex(where: { ($0["timestamp"] as? Int64) == marker }) {
                history[i]["lostAudioSeconds"] = Double(max(0, now - marker)) / 1000
                history[i]["lostAudioResolvedAt"] = now
            } else {
                history = Array((history + [["timestamp": marker, "lostAudioResolvedAt": now, "identity_epoch": healthStore.epoch]]).suffix(Self.maxDisconnectHistory))
            }
            guard persistPropertyListRecords(history, forKey: key, in: defaults) else { return }
            defaults.removeObject(forKey: "ble_audio_outage_\(uuid)")
            persistPropertyListRecords(packetDays[uuid] ?? [], forKey: "ble_packet_days_\(uuid)", in: defaults)
        }
    }

    private func readFirmwareDiagnosticsIfDue(_ peripheral: CBPeripheral, uuid: String) {
        let now = ProcessInfo.processInfo.systemUptime
        if let last = lastDiagnosticsReadUptime[uuid], now - last < 15 * 60 { return }
        guard let diagnostic = peripheral.services?.first(where: { $0.uuid == Self.diagnosticsServiceUuid })?
            .characteristics?.first(where: { $0.uuid == Self.diagnosticsCharUuid }) else { return }
        // Throttle attempts too: unsupported/failed reads must not create a retry storm.
        lastDiagnosticsReadUptime[uuid] = now
        peripheral.readValue(for: diagnostic)
    }

    private func recordFirmwareDiagnostics(uuid: String, data: Data) {
        guard healthStore.enabled else { return }
        guard let value = OmiBleFirmwareDiagnostics.parse(data, timestampMs: CheckedIntegerConversion.epochMs()) else { return }
        let defaults = UserDefaults.standard
        chargingState[uuid] = value["charging"] as? Bool
        if let charging = chargingState[uuid] {
            rehydrateBatteryBaselineIfNeeded(uuid: uuid)
            let batteryKey = Self.batteryHistoryKey(uuid)
            let history = defaults.array(forKey: batteryKey) as? [[String: Any]] ?? []
            if let updated = OmiBleEnergyPolicy.backfillLatestBatteryCharging(
                history, charging: charging, nowMs: CheckedIntegerConversion.epochMs()
            ),
               persistPropertyListRecords(updated, forKey: batteryKey, in: defaults) {
                lastPersistedBatteryCharging[uuid] = charging
            }
        }
        let key = "ble_diagnostics_firmware_\(uuid)"
        var reads = defaults.array(forKey: key) as? [[String: Any]] ?? []
        var stamped = value
        stamped["identity_epoch"] = healthStore.epoch
        stamped["app_build"] = OmiDeviceHealthStore.build
        stamped["firmware"] = defaults.string(forKey: "ble_observed_firmware_\(uuid)")
        reads.append(stamped)
        // 15-minute reads over the worst-case catch-up window: 4/hour * 24 * 8.
        // maybeEmit can roll up yesterday - 6, whose start is nearly eight days old
        // when the app runs late in the current day, so the ring must cover the
        // seven prior days plus the current partial day.
        persistPropertyListRecords(Array(reads.suffix(Self.maxFirmwareDiagnosticsEntries)), forKey: key, in: defaults)
        logBle(uuid: uuid, event: "firmware_diagnostics_read", detail: "v\(data[0])")
    }

    func getExtendedDeviceDiagnostics(uuid: String) -> String {
        guard healthStore.enabled else { return "{}" }
        let defaults = UserDefaults.standard
        var data: [String: Any] = [
            "observed_at": CheckedIntegerConversion.epochMs(),
            "audio_packet_days": packetDays[uuid] ?? (defaults.array(forKey: "ble_packet_days_\(uuid)") ?? []),
            "disconnect_history_v2": defaults.array(forKey: Self.historyKey(uuid)) ?? [],
            "battery_history_v2": defaults.array(forKey: Self.batteryHistoryKey(uuid)) ?? [],
            "rssi_samples": (rssiHistory[uuid] ?? []).map { ["ts": $0.ts, "rssi": $0.rssi] },
            "audio_packets_received": audioReceived[uuid] ?? 0,
            "audio_packets_expected": audioExpected[uuid] ?? 0,
            "connected_at": connectionStartTimes[uuid] ?? 0,
            "firmware_diagnostics": defaults.array(forKey: "ble_diagnostics_firmware_\(uuid)") ?? [],
            "lifecycle_events": defaults.array(forKey: "ble_diagnostics_lifecycle") ?? [],
            "ble_log": defaults.array(forKey: "ble_diagnostics_log_\(uuid)") ?? [],
            "capture_health": captureSnapshots[uuid] ?? [:],
            "capture_health_history": defaults.array(forKey: "ble_capture_health_\(uuid)") ?? [],
            "counters_since": defaults.object(forKey: "ble_diagnostics_counters_since_\(uuid)") ?? NSNull(),
        ]
        data["identity_epoch"] = healthStore.epoch
        data["audio_outage_started_at"] = healthStore.openSince(uuid)
        guard let encoded = try? SafeJSON.data(withJSONObject: data),
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
        guard healthStore.enabled else { return }
        if eventType == "disconnect" { healthStore.end(uuid, at: CheckedIntegerConversion.epochMs()) }
        let defaults = UserDefaults.standard
        let key = OmiBleManager.historyKey(uuid)
        var history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let now = CheckedIntegerConversion.epochMs()
        let startedAt = connectionStartTimes[uuid] ?? 0
        let durationMs: Int64 = (eventType == "disconnect" && startedAt > 0) ? (now - startedAt) : 0

        let trend = OmiBleRssiDiagnostics.trend(samples: rssiHistory[uuid] ?? [], nowMs: now)
        var event: [String: Any] = [
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
        event["identity_epoch"] = healthStore.epoch
        event["app_build"] = OmiDeviceHealthStore.build
        event["firmware"] = defaults.string(forKey: "ble_observed_firmware_\(uuid)")
        history.append(event)
        var recovery = reconnectDiagnostics[uuid, default: OmiBleReconnectDiagnostics()]
        recovery.recordEvent(timestampMs: now, eventType: eventType, isManual: isManual)
        reconnectDiagnostics[uuid] = recovery
        history = recovery.retainedHistory(
            history, nowMs: now, retentionMs: Self.disconnectRetentionMs, limit: Self.maxDisconnectHistory,
            timestampOf: { $0["timestamp"] as? Int64 ?? 0 }
        )

        persistPropertyListRecords(history, forKey: key, in: defaults)
        persistPropertyListRecords(packetDays[uuid] ?? [], forKey: "ble_packet_days_\(uuid)", in: defaults)
        logBle(uuid: uuid, event: eventType, detail: event["reason"] as? String ?? "unknown")

        if eventType == "disconnect" {
            if healthStore.enabled {
                let start = defaults.object(forKey: "ble_audio_outage_\(uuid)") as? Int64 ?? now
                pendingAudioRecovery[uuid] = start
                try? SafeDefaults.store(.int64(start), forKey: "ble_audio_outage_\(uuid)", in: defaults)
            }
        }
    }

    /// On successful didConnect, attribute the recovery interval to the event
    /// that started it, even when later connection attempts failed.
    private func backfillTimeToReconnect(uuid: String) {
        let defaults = UserDefaults.standard
        var pending = reconnectDiagnostics.removeValue(forKey: uuid) ?? OmiBleReconnectDiagnostics()
        if let start = defaults.object(forKey: "ble_audio_outage_\(uuid)") as? Int64 {
            pending.recordEvent(timestampMs: start, eventType: "disconnect", isManual: false)
        }
        let key = OmiBleManager.historyKey(uuid)
        let history = defaults.array(forKey: key) as? [[String: Any]] ?? []
        if let updated = pending.backfilledHistory(
            history, nowMs: CheckedIntegerConversion.epochMs(), hadConnection: everConnected.contains(uuid) || defaults.object(forKey: "ble_audio_outage_\(uuid)") != nil,
            timestampOf: { $0["timestamp"] as? Int64 ?? 0 },
            withDuration: { event, duration in
                var updated = event
                updated["timeToReconnectMs"] = duration
                return updated
            }
        ) { persistPropertyListRecords(updated, forKey: key, in: defaults) }
    }

    private func incrementReconnectionCount(uuid: String) {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.reconnectKey(uuid)
        let count = defaults.integer(forKey: key)
        try? SafeDefaults.store(.int(count + 1), forKey: key, in: defaults)
    }

    private func incrementFailToConnectCount(uuid: String) {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.failToConnectKey(uuid)
        let count = defaults.integer(forKey: key)
        try? SafeDefaults.store(.int(count + 1), forKey: key, in: defaults)
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
        guard healthStore.enabled else { return }
        guard let now = CheckedIntegerConversion.int64(Date().timeIntervalSince1970 * 1000) else { return }
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

        var point = OmiBleEnergyPolicy.batteryHistoryEntry(timestampMs: now, level: level, charging: charging)
        point["identity_epoch"] = healthStore.epoch
        point["app_build"] = OmiDeviceHealthStore.build
        point["firmware"] = defaults.string(forKey: "ble_observed_firmware_\(uuid)")
        history.append(point)

        if history.count > OmiBleManager.maxBatteryHistoryEntries {
            history = Array(history.suffix(OmiBleManager.maxBatteryHistoryEntries))
        }

        let records: [[String: PlistValue]] = history.compactMap { entry in
            guard let timestamp = entry["ts"] as? Int64,
                  let batteryLevel = entry["level"] as? Int else { return nil }
            var record: [String: PlistValue] = ["ts": .int64(timestamp), "level": .int(batteryLevel)]
            if let epoch = entry["identity_epoch"] as? Int64 { record["identity_epoch"] = .int64(epoch) }
            if let build = entry["app_build"] as? String { record["app_build"] = .string(build) }
            if let firmware = entry["firmware"] as? String { record["firmware"] = .string(firmware) }
            if let charging = entry["charging"] as? Bool { record["charging"] = .bool(charging) }
            return record
        }
        do {
            try SafeDefaults.setPlistRecords(records, forKey: key, in: defaults)
        } catch {
            return
        }
        lastPersistedBatteryLevel[uuid] = level
        lastPersistedBatteryTimestampMs[uuid] = now
        lastPersistedBatteryCharging[uuid] = charging
    }

    func getBatteryHistory(uuid: String) -> [BleBatteryPoint] {
        let defaults = UserDefaults.standard
        let key = OmiBleManager.batteryHistoryKey(uuid)
        let history = defaults.array(forKey: key) as? [[String: Any]] ?? []

        let now = CheckedIntegerConversion.epochMs()
        let cutoff = now - OmiBleManager.batteryHistoryRetentionMs

        return history.compactMap { obj in
            guard let ts = obj["ts"] as? Int64, let level = obj["level"] as? Int, ts >= cutoff else { return nil }
            return BleBatteryPoint(timestamp: ts, level: Int64(level))
        }
    }

    // MARK: - Audio Batch Helpers

    private func cleanupPeripheral(_ peripheralUuid: String) {
        timedOutNotifications = timedOutNotifications.filter { !$0.hasPrefix(peripheralUuid.lowercased() + ":") }
        freshConnections.remove(peripheralUuid)
        for key in notificationRequests.keys.filter({ $0.hasPrefix(peripheralUuid.lowercased() + ":") }) {
            finishNotification(key, uuid: peripheralUuid, error: PigeonError(code: "DISCONNECTED", message: "Link ended before notification confirmation", details: nil))
        }
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
                    healthStore.start(uuid, at: CheckedIntegerConversion.epochMs())
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
        guard peripherals[uuid] === peripheral else { return }
        NSLog("[OmiBle] didConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid)")

        // Track reconnections (not first connect)
        if everConnected.contains(uuid) {
            incrementReconnectionCount(uuid: uuid)
        }
        // Consume first-time failure markers too, without recording those
        // initial connections as reconnections.
        backfillTimeToReconnect(uuid: uuid)
        everConnected.insert(uuid)
        freshConnections.insert(uuid)
        readyNotified.remove(uuid)
        discoveryStartedAt.removeValue(forKey: uuid)
        pairingRecoveryInFlight.remove(uuid)
        let connectionStartedAt = CheckedIntegerConversion.epochMs()
        healthStore.start(uuid, at: connectionStartedAt)
        connectionStartTimes[uuid] = connectionStartedAt
        lastRssi.removeValue(forKey: uuid)
        rssiHistory.removeValue(forKey: uuid)
        // The charging flag comes only from firmware diagnostics reads, and the
        // state may have changed while disconnected. Clear it so new battery
        // points stay unknown (counted conservatively as drain by the rollup)
        // until the next read re-stamps the actual state; a retained stale
        // charging=true would exclude real drain intervals and the backfill
        // cannot correct an explicit flag.
        chargingState.removeValue(forKey: uuid)
        lastPacketIndex.removeValue(forKey: uuid)
        audioReceived[uuid] = 0
        audioExpected[uuid] = 0
        if UserDefaults.standard.object(forKey: "ble_diagnostics_counters_since_\(uuid)") == nil {
            try? SafeDefaults.store(.int64(connectionStartedAt), forKey: "ble_diagnostics_counters_since_\(uuid)")
        }
        startRssiDiagnosticsPolling(for: peripheral)
        logBle(uuid: uuid, event: "connected", detail: "")

        peripheral.delegate = self
        discoverServices(for: peripheral, uuid: uuid)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        let uuid = peripheralUuidString(peripheral)
        guard OmiCaptureReconnect.acceptsDownCallback(
            currentOwner: peripherals[uuid] === peripheral, connected: peripheral.state == .connected
        ) else { return }
        if let recovery = captureReconnects[uuid] {
            cleanupPeripheral(uuid)
            recovery.finish(false)
            recovery.settleResume(true)
            if captureReconnects[uuid] === recovery { captureReconnects.removeValue(forKey: uuid) }
            return
        }
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
        guard OmiCaptureReconnect.acceptsDownCallback(
            currentOwner: peripherals[uuid] === peripheral, connected: peripheral.state == .connected
        ) else { return }
        let isManual = manuallyDisconnected.contains(uuid)
        let pairingLost = OmiBlePairingPolicy.isPairingLost(error)
            || pairingRecoveryInFlight.remove(uuid) != nil
        NSLog("[OmiBle] didDisconnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")")
        if !isManual {
            persistDisconnectEvent(uuid: uuid, reason: Self.bleReasonString(from: error), reasonCode: (error as? CBError)?.code.rawValue ?? -1, isManual: false, eventType: "disconnect")
        }
        cleanupPeripheral(uuid)

        if pairingLost {
            markPairingLost(uuid: uuid)
        }

        // Finalize the in-progress batch recording so it's saved + ingestable right away
        // (a plain BLE disconnect never delivers another packet to trigger the gap finalize).
        OmiBatchAudioWriter.shared.stop("disconnected")
        LimitlessFlashDrainEngine.shared.onDeviceDisconnected(uuid)

        if let recovery = captureReconnects[uuid] {
            connectionStartTimes.removeValue(forKey: uuid)
            recovery.didDisconnect(pairingLost: pairingLost || isManual)
            if recovery.stage == .finished {
                recovery.settleResume(true)
                if captureReconnects[uuid] === recovery { captureReconnects.removeValue(forKey: uuid) }
            }
            return
        }
        captureSessions[uuid]?.disconnected(recovering: false)

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
        guard peripherals[uuid] === peripheral else { return }
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
        guard peripherals[uuid] === peripheral else { return }
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
        let now = CheckedIntegerConversion.epochMs()
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

        if characteristic.uuid != Self.diagnosticsCharUuid && OmiBleConnectionPolicy.requiresPairingRecovery(error) {
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
                if charUuid == "00002a26-0000-1000-8000-00805f9b34fb", let firmware = String(data: data, encoding: .utf8) {
                    try? SafeDefaults.store(.string(firmware), forKey: "ble_observed_firmware_\(uuid)")
                }
                completion(.success(FlutterStandardTypedData(bytes: data)))
            }
            return
        }

        if characteristic.uuid == Self.diagnosticsCharUuid {
            if error == nil, let value = characteristic.value { recordFirmwareDiagnostics(uuid: uuid, data: value) }
            return
        }

        // Handle notification
        guard error == nil, peripheral.state == .connected,
              captureReconnects[uuid]?.disconnected != false,
              let data = characteristic.value, !data.isEmpty else { return }

        guard peripherals[uuid] === peripheral else { return }
        let wasTransferring = captureStorageProgress.isActive(uuid, now: ProcessInfo.processInfo.systemUptime)
        captureStorageProgress.received(uuid, characteristic: charUuid, now: ProcessInfo.processInfo.systemUptime)
        if !wasTransferring && captureStorageProgress.isActive(uuid, now: ProcessInfo.processInfo.systemUptime) {
            logBle(uuid: uuid, event: "capture_recovery_deferred", detail: "storage_notification_progress")
        }

        if characteristic.uuid == Self.audioCharUuid {
            guard let service = characteristic.service,
                  findCharacteristic(peripheralUuid: uuid, serviceUuid: service.uuid.uuidString,
                                     characteristicUuid: characteristic.uuid.uuidString) === characteristic else { return }
            recordAudioPacket(uuid: uuid, value: data)
            if data.count > 3 { captureSessions[uuid]?.audio() }
        }

        if characteristic.uuid == OmiBleManager.batteryLevelCharUuid, let firstByte = data.first {
            persistBatteryReading(uuid: uuid, level: Int(firstByte))
            readFirmwareDiagnosticsIfDue(peripheral, uuid: uuid)
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
        if let service = characteristic.service {
            let key = "\(uuid):\(fullUuidString(service.uuid)):\(charUuid)".lowercased()
            if notificationRequests[key]?.characteristic === characteristic {
                finishNotification(key, uuid: uuid, error: error)
            }
        }
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
