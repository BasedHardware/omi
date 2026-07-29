import CoreBluetooth
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

  /// One serialized CoreBluetooth operation queue per peripheral.
  private var operationSchedulers: [String: BleGattOperationScheduler] = [:]

  private struct NotificationTransitionKey: Hashable {
    let peripheralUuid: String
    let target: BleGattTarget
  }

  /// Latest requested CCCD state per characteristic in the active connection session.
  private var notificationTransitions: [NotificationTransitionKey: BleGattNotificationTransitionState] = [:]

  private struct CharacteristicContext {
    let peripheralUuid: String
    let sessionId: UInt64
    let target: BleGattTarget
  }

  /// Binds delegate callbacks to the exact characteristic object and connection session.
  private var characteristicContexts: [ObjectIdentifier: CharacteristicContext] = [:]
  private var nextCharacteristicInstanceId: UInt64 = 0

  private struct PendingWriteWithoutResponse {
    let token: BleGattOperationToken
    let characteristic: CBCharacteristic
    let data: Data
  }

  private var pendingWritesWithoutResponse: [String: PendingWriteWithoutResponse] = [:]

  /// Whether the user explicitly disconnected (suppress auto-reconnect).
  private var manuallyDisconnected: Set<String> = []

  /// Bounded reconnect state prevents fixed-delay retry storms during RF outages.
  private var reconnectLifecycles: [String: BleReconnectLifecycle] = [:]
  private var reconnectWorkItems: [String: DispatchWorkItem] = [:]

  /// RSSI diagnostics timer. Connection supervision is owned by the controller;
  /// polling RSSI is not a keep-alive and stays off outside the diagnostics view.
  private var rssiTimer: Timer?
  private var rssiPeripheralUuid: String?

  /// When true, RSSI reads are forwarded to Flutter for the diagnostics graph.
  private var isRssiStreamingEnabled = false

  /// Connection start time per peripheral UUID.
  private var connectionStartTimes: [String: Int64] = [:]

  /// Tracks peripherals that have connected or were restored by CoreBluetooth.
  private let reconnectEligibility = BleReconnectEligibility()

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

  #if DEBUG
    private struct NotificationWindow {
      var count = 0
      var bytes = 0
      var maxValueLength = 0
    }

    private var notificationWindowStartedAt = Date()
    private var notificationWindows: [String: NotificationWindow] = [:]
    private var pigeonNotificationsInFlight = 0
    private var peakPigeonNotificationsInFlight = 0
  #endif

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
    NSLog(
      "[OmiBle] startScan called, state=\(getBluetoothState()), timeout=\(timeout), serviceUuids=\(serviceUuids)"
    )

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
    centralManager.scanForPeripherals(
      withServices: cbuuids,
      options: [
        CBCentralManagerScanOptionAllowDuplicatesKey: false
      ])

    scanTimer?.invalidate()
    if timeout > 0 {
      scanTimer = Timer.scheduledTimer(withTimeInterval: TimeInterval(timeout), repeats: false) {
        [weak self] _ in
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
    cancelScheduledReconnect(uuid: uuid, resetAttempt: true)

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
    cancelScheduledReconnect(uuid: uuid, resetAttempt: true)
    persistDisconnectEvent(
      uuid: uuid, reason: "manual", reasonCode: 0, isManual: true, eventType: "disconnect")
    guard let peripheral = peripherals[uuid] else { return }
    centralManager.cancelPeripheralConnection(peripheral)
  }

  func disconnectAllPeripherals() {
    for (uuid, peripheral) in peripherals {
      manuallyDisconnected.insert(uuid)
      cancelScheduledReconnect(uuid: uuid, resetAttempt: true)
      centralManager.cancelPeripheralConnection(peripheral)
    }
  }

  func isPeripheralConnected(uuid: String) -> Bool {
    return peripherals[uuid]?.state == .connected
  }

  /// Re-issue `connect()` on any previously-connected peripheral that isn't
  /// currently connected and wasn't manually disconnected. Scan-discovered
  /// peripherals that never completed a connection are excluded via the
  /// reconnect-eligibility guard so we don't try to connect to unrelated devices
  /// picked up during a scan. Safe to call whenever the app returns to the
  /// foreground — `centralManager.connect` is idempotent and pending connects
  /// cost nothing while iOS waits at the chipset level.
  func reconnectStalePeripherals() {
    guard centralManager.state == .poweredOn else { return }
    for (uuid, peripheral) in peripherals {
      guard reconnectEligibility.contains(uuid) else { continue }
      if manuallyDisconnected.contains(uuid) { continue }
      if peripheral.state == .connected || peripheral.state == .connecting { continue }
      NSLog(
        "[OmiBle] Re-issuing connect on foreground for \(uuid), state=\(peripheral.state.rawValue)")
      cancelScheduledReconnect(uuid: uuid, resetAttempt: false)
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
    guard
      let characteristic = findCharacteristic(
        peripheralUuid: peripheralUuid, serviceUuid: serviceUuid,
        characteristicUuid: characteristicUuid)
    else {
      completion(
        .failure(PigeonError(code: "NOT_FOUND", message: "Characteristic not found", details: nil)))
      return
    }

    guard let peripheral = peripherals[peripheralUuid], peripheral.state == .connected,
      let context = characteristicContexts[ObjectIdentifier(characteristic)]
    else {
      completion(
        .failure(
          PigeonError(code: "DISCONNECTED", message: "Peripheral disconnected", details: nil)))
      return
    }

    // CoreBluetooth uses the same delegate callback for reads and notifications
    // and provides no request identifier. Reading an actively-notifying
    // characteristic would make the response fundamentally ambiguous.
    guard BleGattReadAdmission.evaluate(isNotifying: characteristic.isNotifying) == .start else {
      completion(.failure(readWhileNotifyingError()))
      return
    }

    let scheduler = operationScheduler(for: peripheralUuid)
    scheduler.enqueue(
      kind: .readValue,
      target: context.target,
      start: { [weak self, weak peripheral] token in
        guard let self, let peripheral, peripheral.state == .connected else {
          self?.operationSchedulers[peripheralUuid]?.complete(
            token: token,
            result: .failure(BleGattOperationSchedulerError.disconnected)
          )
          return
        }
        guard BleGattReadAdmission.evaluate(isNotifying: characteristic.isNotifying) == .start
        else {
          scheduler.complete(token: token, result: .failure(self.readWhileNotifyingError()))
          return
        }
        peripheral.readValue(for: characteristic)
      },
      completion: { result in
        switch result {
        case .success(let data):
          completion(.success(FlutterStandardTypedData(bytes: data ?? Data())))
        case .failure(let error):
          completion(.failure(error))
        }
      }
    )
  }

  func writeCharacteristic(
    peripheralUuid: String,
    serviceUuid: String,
    characteristicUuid: String,
    data: FlutterStandardTypedData,
    completion: @escaping (Result<Void, Error>) -> Void
  ) {
    guard
      let characteristic = findCharacteristic(
        peripheralUuid: peripheralUuid, serviceUuid: serviceUuid,
        characteristicUuid: characteristicUuid)
    else {
      completion(
        .failure(PigeonError(code: "NOT_FOUND", message: "Characteristic not found", details: nil)))
      return
    }

    guard let peripheral = peripherals[peripheralUuid], peripheral.state == .connected,
      let context = characteristicContexts[ObjectIdentifier(characteristic)]
    else {
      completion(
        .failure(
          PigeonError(code: "DISCONNECTED", message: "Peripheral disconnected", details: nil)))
      return
    }

    let writeType: CBCharacteristicWriteType =
      characteristic.properties.contains(.write) ? .withResponse : .withoutResponse
    let scheduler = operationScheduler(for: peripheralUuid)
    let kind: BleGattOperationKind =
      writeType == .withResponse ? .writeWithResponse : .writeWithoutResponse

    scheduler.enqueue(
      kind: kind,
      target: context.target,
      start: { [weak self, weak peripheral] token in
        guard let self, let peripheral, peripheral.state == .connected else {
          self?.operationSchedulers[peripheralUuid]?.complete(
            token: token,
            result: .failure(BleGattOperationSchedulerError.disconnected)
          )
          return
        }

        if writeType == .withResponse {
          peripheral.writeValue(data.data, for: characteristic, type: .withResponse)
          return
        }

        if peripheral.canSendWriteWithoutResponse {
          peripheral.writeValue(data.data, for: characteristic, type: .withoutResponse)
          scheduler.complete(token: token, result: .success(nil))
        } else {
          self.pendingWritesWithoutResponse[peripheralUuid] = PendingWriteWithoutResponse(
            token: token,
            characteristic: characteristic,
            data: data.data
          )
        }
      },
      completion: { result in
        switch result {
        case .success:
          completion(.success(()))
        case .failure(let error):
          completion(.failure(error))
        }
      }
    )
  }

  func subscribeCharacteristic(
    peripheralUuid: String, serviceUuid: String, characteristicUuid: String
  ) {
    setNotificationState(
      true,
      peripheralUuid: peripheralUuid,
      serviceUuid: serviceUuid,
      characteristicUuid: characteristicUuid
    )
  }

  func unsubscribeCharacteristic(
    peripheralUuid: String, serviceUuid: String, characteristicUuid: String
  ) {
    setNotificationState(
      false,
      peripheralUuid: peripheralUuid,
      serviceUuid: serviceUuid,
      characteristicUuid: characteristicUuid
    )
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

  func startRssiStreaming(uuid: String) {
    isRssiStreamingEnabled = true
    rssiPeripheralUuid = uuid
    guard let peripheral = peripherals[uuid], peripheral.state == .connected else { return }
    startRssiDiagnostics(for: peripheral)
  }

  func stopRssiStreaming(uuid: String) {
    guard rssiPeripheralUuid == nil || rssiPeripheralUuid == uuid else { return }
    isRssiStreamingEnabled = false
    rssiPeripheralUuid = nil
    stopRssiDiagnostics()
  }

  private func startRssiDiagnostics(for peripheral: CBPeripheral) {
    guard isRssiStreamingEnabled, rssiPeripheralUuid == peripheralUuidString(peripheral) else {
      return
    }
    stopRssiDiagnostics(clearSelection: false)
    enqueueRssiRead(for: peripheral)
    rssiTimer = Timer.scheduledTimer(withTimeInterval: 3.0, repeats: true) {
      [weak self, weak peripheral] _ in
      guard let self, let peripheral, peripheral.state == .connected else {
        self?.stopRssiDiagnostics(clearSelection: false)
        return
      }
      self.enqueueRssiRead(for: peripheral)
    }
  }

  private func enqueueRssiRead(for peripheral: CBPeripheral) {
    let uuid = peripheralUuidString(peripheral)
    guard let sessionId = operationSchedulers[uuid]?.sessionId else { return }
    let scheduler = operationScheduler(for: uuid)
    guard !scheduler.contains(kind: .readRssi, target: .rssi) else { return }

    scheduler.enqueue(
      kind: .readRssi,
      target: .rssi,
      fatalOnTimeout: false,
      start: { [weak self, weak peripheral] token in
        guard let self, let peripheral, peripheral.state == .connected,
          self.operationSchedulers[uuid]?.sessionId == sessionId
        else {
          self?.operationSchedulers[uuid]?.complete(
            token: token,
            result: .failure(BleGattOperationSchedulerError.disconnected)
          )
          return
        }
        peripheral.readRSSI()
      },
      completion: { result in
        if case .failure(let error) = result {
          NSLog("[OmiBle] RSSI read failed for \(uuid): \(error.localizedDescription)")
        }
      }
    )
  }

  private func stopRssiDiagnostics(clearSelection: Bool = true) {
    rssiTimer?.invalidate()
    rssiTimer = nil
    if clearSelection {
      rssiPeripheralUuid = nil
    }
  }

  // MARK: - Private Helpers

  private func readWhileNotifyingError() -> PigeonError {
    PigeonError(
      code: "READ_WHILE_NOTIFYING",
      message: "Cannot safely read an actively notifying characteristic",
      details: nil
    )
  }

  private func operationScheduler(for peripheralUuid: String) -> BleGattOperationScheduler {
    if let scheduler = operationSchedulers[peripheralUuid] {
      return scheduler
    }

    let scheduler = BleGattOperationScheduler(
      onFatalTimeout: { [weak self] token in
        guard let self else { return }
        NSLog(
          "[OmiBle] GATT operation timed out for \(peripheralUuid), "
            + "session=\(token.sessionId), operation=\(token.id)"
        )
        self.pendingWritesWithoutResponse.removeValue(forKey: peripheralUuid)
        if let peripheral = self.peripherals[peripheralUuid], peripheral.state != .disconnected {
          self.centralManager.cancelPeripheralConnection(peripheral)
        }
      }
    )
    operationSchedulers[peripheralUuid] = scheduler
    return scheduler
  }

  private func cancelScheduledReconnect(uuid: String, resetAttempt: Bool) {
    reconnectWorkItems.removeValue(forKey: uuid)?.cancel()
    if resetAttempt {
      reconnectLifecycles.removeValue(forKey: uuid)
    }
  }

  private func reconnectLifecycle(for uuid: String) -> BleReconnectLifecycle {
    if let lifecycle = reconnectLifecycles[uuid] {
      return lifecycle
    }
    let lifecycle = BleReconnectLifecycle()
    reconnectLifecycles[uuid] = lifecycle
    return lifecycle
  }

  private func scheduleReconnect(for peripheral: CBPeripheral) {
    let uuid = peripheralUuidString(peripheral)
    guard !manuallyDisconnected.contains(uuid), centralManager.state == .poweredOn else { return }

    reconnectWorkItems.removeValue(forKey: uuid)?.cancel()
    let lifecycle = reconnectLifecycle(for: uuid)
    let attempt = lifecycle.failureCount + 1
    let delay = lifecycle.nextReconnectDelay()

    let workItem = DispatchWorkItem { [weak self, weak peripheral] in
      guard let self, let peripheral else { return }
      self.reconnectWorkItems.removeValue(forKey: uuid)
      guard !self.manuallyDisconnected.contains(uuid),
        self.centralManager.state == .poweredOn,
        peripheral.state == .disconnected
      else {
        return
      }
      NSLog("[OmiBle] Reconnect attempt \(attempt) for \(uuid)")
      peripheral.delegate = self
      self.centralManager.connect(peripheral, options: nil)
    }
    reconnectWorkItems[uuid] = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
  }

  /// Reissue the system-owned connection request before iOS suspends us after
  /// a background disconnect. CoreBluetooth keeps a pending request alive; a
  /// delayed work item may never run once the app is suspended.
  private func requestPersistentReconnect(for peripheral: CBPeripheral) {
    let uuid = peripheralUuidString(peripheral)
    guard
      !manuallyDisconnected.contains(uuid),
      centralManager.state == .poweredOn,
      peripheral.state == .disconnected
    else {
      return
    }

    reconnectWorkItems.removeValue(forKey: uuid)?.cancel()
    NSLog("[OmiBle] Reissuing persistent reconnect for \(uuid)")
    peripheral.delegate = self
    centralManager.connect(peripheral, options: nil)
  }

  private func activateSession(for peripheral: CBPeripheral) {
    let uuid = peripheralUuidString(peripheral)
    let scheduler = operationScheduler(for: uuid)
    scheduler.beginSession()
    characteristicContexts = characteristicContexts.filter { $0.value.peripheralUuid != uuid }
    notificationTransitions = notificationTransitions.filter { $0.key.peripheralUuid != uuid }
    pendingWritesWithoutResponse.removeValue(forKey: uuid)
  }

  private func registerCharacteristics(for peripheral: CBPeripheral, service: CBService) {
    let uuid = peripheralUuidString(peripheral)
    let scheduler = operationScheduler(for: uuid)
    for characteristic in service.characteristics ?? [] {
      nextCharacteristicInstanceId &+= 1
      let target = BleGattTarget(
        serviceUuid: fullUuidString(service.uuid),
        characteristicUuid: fullUuidString(characteristic.uuid),
        instanceId: nextCharacteristicInstanceId
      )
      characteristicContexts[ObjectIdentifier(characteristic)] = CharacteristicContext(
        peripheralUuid: uuid,
        sessionId: scheduler.sessionId,
        target: target
      )
    }
  }

  private func setNotificationState(
    _ enabled: Bool,
    peripheralUuid: String,
    serviceUuid: String,
    characteristicUuid: String
  ) {
    guard
      let characteristic = findCharacteristic(
        peripheralUuid: peripheralUuid,
        serviceUuid: serviceUuid,
        characteristicUuid: characteristicUuid
      ),
      let peripheral = peripherals[peripheralUuid],
      peripheral.state == .connected,
      let context = characteristicContexts[ObjectIdentifier(characteristic)]
    else {
      return
    }

    let key = NotificationTransitionKey(peripheralUuid: peripheralUuid, target: context.target)
    let transitionState =
      notificationTransitions[key]
      ?? BleGattNotificationTransitionState(confirmed: characteristic.isNotifying)
    notificationTransitions[key] = transitionState
    guard let transition = transitionState.request(enabled) else { return }

    startNotificationTransition(
      transition,
      key: key,
      peripheral: peripheral,
      characteristic: characteristic,
      context: context
    )
  }

  private func startNotificationTransition(
    _ enabled: Bool,
    key: NotificationTransitionKey,
    peripheral: CBPeripheral,
    characteristic: CBCharacteristic,
    context: CharacteristicContext
  ) {
    let peripheralUuid = key.peripheralUuid
    let characteristicUuid = context.target.characteristicUuid
    let scheduler = operationScheduler(for: peripheralUuid)
    let requestedKind = BleGattOperationKind.setNotifications(enabled)

    scheduler.enqueue(
      kind: requestedKind,
      target: context.target,
      start: { [weak self, weak peripheral] token in
        guard let peripheral, peripheral.state == .connected else {
          self?.operationSchedulers[peripheralUuid]?.complete(
            token: token,
            result: .failure(BleGattOperationSchedulerError.disconnected)
          )
          return
        }
        peripheral.setNotifyValue(enabled, for: characteristic)
      },
      completion: { [weak self, weak peripheral] result in
        guard let self else { return }
        let success: Bool
        switch result {
        case .success:
          success = true
        case .failure(let error):
          success = false
          NSLog(
            "[OmiBle] Failed to set notification state for \(characteristicUuid): "
              + error.localizedDescription
          )
        }

        guard
          let next = self.notificationTransitions[key]?.complete(
            attempted: enabled,
            success: success
          ),
          let peripheral,
          peripheral.state == .connected,
          self.characteristicContexts[ObjectIdentifier(characteristic)]?.sessionId
            == context.sessionId
        else {
          return
        }

        self.startNotificationTransition(
          next,
          key: key,
          peripheral: peripheral,
          characteristic: characteristic,
          context: context
        )
      }
    )
  }

  private func findCharacteristic(
    peripheralUuid: String, serviceUuid: String, characteristicUuid: String
  )
    -> CBCharacteristic?
  {
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
      let short = uuid.uuidString  // e.g. "180A"
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
  private static let maxDisconnectHistory = 20
  private static let rssiHistoryLimit = 10
  private static let rssiTrendWindowMs: Int64 = 15_000
  private static let rssiTrendFadingDropDb: Int64 = 10

  /// Classify the RSSI trajectory in the window before `nowMs`. See `rssiTrend`
  /// on BleDisconnectEvent for the semantics of each label.
  private static func classifyRssiTrend(samples: [(ts: Int64, rssi: Int64)], nowMs: Int64) -> String {
    let windowStart = nowMs - rssiTrendWindowMs
    let recent = samples.filter { $0.ts >= windowStart }
    // No recent samples — keep-alive wasn't running, so we can't say.
    if recent.isEmpty { return "gap" }
    if recent.count < 3 { return "unknown" }
    // Compare the average of the oldest third to the newest third. A drop of
    // ≥rssiTrendFadingDropDb dB indicates a fading signal (walk-away).
    let third = max(1, recent.count / 3)
    let oldestAvg = recent.prefix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
    let newestAvg = recent.suffix(third).map { $0.rssi }.reduce(0, +) / Int64(third)
    let dropDb = oldestAvg - newestAvg  // RSSI is negative; larger drop = more negative newer value
    if dropDb >= rssiTrendFadingDropDb { return "fading" }
    return "sudden"
  }

  private static func historyKey(_ uuid: String) -> String { "\(diagnosticsKeyPrefix)\(uuid)" }
  private static func reconnectKey(_ uuid: String) -> String { "\(reconnectCountKeyPrefix)\(uuid)" }
  private static func failToConnectKey(_ uuid: String) -> String {
    "\(failToConnectCountKeyPrefix)\(uuid)"
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
    guard let cbError = error as? CBError else { return "clean_disconnect" }
    switch cbError.code {
    case .connectionTimeout: return "connection_timeout"
    case .peripheralDisconnected: return "remote_device_terminated"
    case .connectionFailed: return "connection_failed_instant_passed"
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

  private static func batteryHistoryKey(_ uuid: String) -> String {
    "\(batteryHistoryKeyPrefix)\(uuid)"
  }

  private func persistBatteryReading(uuid: String, level: Int) {
    let defaults = UserDefaults.standard
    let key = OmiBleManager.batteryHistoryKey(uuid)
    var history = defaults.array(forKey: key) as? [[String: Any]] ?? []

    let now = Int64(Date().timeIntervalSince1970 * 1000)
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
      guard let ts = obj["ts"] as? Int64, let level = obj["level"] as? Int, ts >= cutoff else {
        return nil
      }
      return BleBatteryPoint(timestamp: ts, level: Int64(level))
    }
  }

  // MARK: - Audio Batch Helpers

  private func cleanupPeripheral(_ peripheralUuid: String) {
    if rssiPeripheralUuid == peripheralUuid {
      stopRssiDiagnostics(clearSelection: false)
    }
    discoveredServices.removeValue(forKey: peripheralUuid)
    pendingWritesWithoutResponse.removeValue(forKey: peripheralUuid)
    notificationTransitions = notificationTransitions.filter {
      $0.key.peripheralUuid != peripheralUuid
    }
    characteristicContexts = characteristicContexts.filter {
      $0.value.peripheralUuid != peripheralUuid
    }
    operationSchedulers[peripheralUuid]?.endSession()
  }

  #if DEBUG
    private func recordNotificationMetric(characteristicUuid: String, valueLength: Int) {
      var window = notificationWindows[characteristicUuid] ?? NotificationWindow()
      window.count += 1
      window.bytes += valueLength
      window.maxValueLength = max(window.maxValueLength, valueLength)
      notificationWindows[characteristicUuid] = window

      let elapsed = Date().timeIntervalSince(notificationWindowStartedAt)
      guard elapsed >= 5 else { return }

      for (characteristic, values) in notificationWindows.sorted(by: { $0.key < $1.key }) {
        NSLog(
          "[OmiBleMetrics] window=%.3fs characteristic=%@ notifications=%d bytes=%d max_value=%d "
            + "notifications_per_sec=%.1f bytes_per_sec=%.1f pigeon_in_flight=%d pigeon_peak=%d",
          elapsed,
          characteristic,
          values.count,
          values.bytes,
          values.maxValueLength,
          Double(values.count) / elapsed,
          Double(values.bytes) / elapsed,
          pigeonNotificationsInFlight,
          peakPigeonNotificationsInFlight
        )
      }
      notificationWindows.removeAll(keepingCapacity: true)
      notificationWindowStartedAt = Date()
      peakPigeonNotificationsInFlight = pigeonNotificationsInFlight
    }

    private func recordPigeonNotificationSent() {
      pigeonNotificationsInFlight += 1
      peakPigeonNotificationsInFlight = max(
        peakPigeonNotificationsInFlight, pigeonNotificationsInFlight)
    }

    private func recordPigeonNotificationCompleted() {
      pigeonNotificationsInFlight = max(0, pigeonNotificationsInFlight - 1)
    }
  #endif
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
    if central.state == .poweredOn {
      reconnectStalePeripherals()
    }
  }

  func centralManager(_ central: CBCentralManager, willRestoreState dict: [String: Any]) {
    // Restore previously connected peripherals after app relaunch
    if let restoredPeripherals = dict[CBCentralManagerRestoredStatePeripheralsKey]
      as? [CBPeripheral]
    {
      var uuids: [String] = []
      for peripheral in restoredPeripherals {
        let uuid = peripheralUuidString(peripheral)
        reconnectEligibility.recordRestored(uuid)
        peripheral.delegate = self
        peripherals[uuid] = peripheral
        uuids.append(uuid)

        // Re-establish connection if not already connected
        if peripheral.state != .connected {
          central.connect(peripheral, options: nil)
        } else {
          reconnectLifecycle(for: uuid).transportConnected()
          activateSession(for: peripheral)
          peripheral.discoverServices(nil)
        }
      }
      flutterApi?.onStateRestored(peripheralUuids: uuids) { _ in }
    }
  }

  func centralManager(
    _ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
    advertisementData: [String: Any],
    rssi RSSI: NSNumber
  ) {
    let uuid = peripheralUuidString(peripheral)
    peripheral.delegate = self
    peripherals[uuid] = peripheral

    let serviceUuids =
      (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID])?.map { $0.uuidString }
      ?? []

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
    if reconnectEligibility.contains(uuid) {
      incrementReconnectionCount(uuid: uuid)
      // Backfill the prior unexpected event with how long it took to recover.
      backfillTimeToReconnect(uuid: uuid)
    }
    reconnectEligibility.recordConnected(uuid)
    connectionStartTimes[uuid] = Int64(Date().timeIntervalSince1970 * 1000)
    cancelScheduledReconnect(uuid: uuid, resetAttempt: false)
    reconnectLifecycle(for: uuid).transportConnected()

    peripheral.delegate = self
    activateSession(for: peripheral)
    peripheral.discoverServices(nil)
  }

  func centralManager(
    _ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)
    let isManual = manuallyDisconnected.contains(uuid)
    NSLog(
      "[OmiBle] didFailToConnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")"
    )
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

    flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: error?.localizedDescription) {
      _ in
    }

    if !isManual, reconnectEligibility.contains(uuid) {
      switch BleReconnectDispatchPolicy.action(
        after: .failedConnect,
        centralIsPoweredOn: central.state == .poweredOn
      ) {
      case .retryWithBackoff:
        scheduleReconnect(for: peripheral)
      case .connectNow:
        requestPersistentReconnect(for: peripheral)
      case .waitForPowerOn:
        break
      }
    }
  }

  func centralManager(
    _ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)
    let isManual = manuallyDisconnected.contains(uuid)
    NSLog(
      "[OmiBle] didDisconnect: \(peripheral.name ?? "<nil>"), uuid=\(uuid), error=\(error?.localizedDescription ?? "nil")"
    )
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

    flutterApi?.onPeripheralDisconnected(peripheralUuid: uuid, error: error?.localizedDescription) {
      _ in
    }

    // Register a persistent CoreBluetooth connection request synchronously.
    // Waiting even 500 ms here is long enough for iOS to suspend a background
    // app after Bluetooth is turned off, stranding the reconnect until launch.
    if !isManual {
      switch BleReconnectDispatchPolicy.action(
        after: .unexpectedDisconnect,
        centralIsPoweredOn: central.state == .poweredOn
      ) {
      case .connectNow:
        requestPersistentReconnect(for: peripheral)
      case .retryWithBackoff:
        scheduleReconnect(for: peripheral)
      case .waitForPowerOn:
        break
      }
    }
  }
}

// MARK: - CBPeripheralDelegate

extension OmiBleManager: CBPeripheralDelegate {

  func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
    let uuid = peripheralUuidString(peripheral)

    if let error {
      NSLog("[OmiBle] Service discovery failed for \(uuid): \(error.localizedDescription)")
      centralManager.cancelPeripheralConnection(peripheral)
      return
    }

    guard let services = peripheral.services else { return }
    discoveredServices[uuid] = services

    // Discover characteristics for all services
    for service in services {
      peripheral.discoverCharacteristics(nil, for: service)
    }
  }

  func peripheral(
    _ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)

    if let error {
      NSLog(
        "[OmiBle] Characteristic discovery failed for \(uuid)/\(service.uuid): "
          + error.localizedDescription
      )
      centralManager.cancelPeripheralConnection(peripheral)
      return
    }

    registerCharacteristics(for: peripheral, service: service)

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
      reconnectLifecycle(for: uuid).deviceReady()
      LimitlessFlashDrainEngine.shared.onDeviceReady(uuid)
      startRssiDiagnostics(for: peripheral)
    }
  }

  func peripheral(_ peripheral: CBPeripheral, didReadRSSI RSSI: NSNumber, error: Error?) {
    let uuid = peripheralUuidString(peripheral)
    guard let scheduler = operationSchedulers[uuid] else { return }
    let result: Result<Data?, Error> = error.map { .failure($0) } ?? .success(nil)
    guard
      scheduler.completeExpected(
        sessionId: scheduler.sessionId,
        kind: .readRssi,
        target: .rssi,
        result: result
      )
    else {
      return
    }
    guard error == nil else { return }

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

  func peripheral(
    _ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)
    guard let service = characteristic.service else { return }
    guard let context = characteristicContexts[ObjectIdentifier(characteristic)],
      context.peripheralUuid == uuid
    else {
      NSLog("[OmiBle] Ignoring value callback from a stale characteristic session for \(uuid)")
      return
    }

    let serviceUuid = fullUuidString(service.uuid)
    let charUuid = fullUuidString(characteristic.uuid)

    // A value update can complete a read only when that exact operation,
    // connection session, and characteristic object are active. If the
    // characteristic is notifying, preserve the packet as a notification:
    // CoreBluetooth gives us no safe way to call it a read response.
    if !characteristic.isNotifying {
      let result: Result<Data?, Error> =
        error.map { .failure($0) } ?? .success(characteristic.value ?? Data())
      if operationSchedulers[uuid]?.completeExpected(
        sessionId: context.sessionId,
        kind: .readValue,
        target: context.target,
        result: result
      ) == true {
        return
      }
    }

    if let error {
      NSLog(
        "[OmiBle] Characteristic value update failed for \(charUuid): \(error.localizedDescription)"
      )
      return
    }

    // Handle notification
    guard let data = characteristic.value, !data.isEmpty else { return }

    #if DEBUG
      recordNotificationMetric(characteristicUuid: charUuid, valueLength: data.count)
    #endif

    if characteristic.uuid == OmiBleManager.batteryLevelCharUuid, let firstByte = data.first {
      persistBatteryReading(uuid: uuid, level: Int(firstByte))
    }

    // Route by fixed protocol identity before consulting native capture policy.
    // Ring sync can deliver hundreds of notifications per second; asking both
    // batch handlers to read UserDefaults before rejecting every storage packet
    // needlessly occupies CoreBluetooth's main-queue callback.
    switch BleNotificationRouter.route(serviceUuid: serviceUuid, characteristicUuid: charUuid) {
    case .limitlessFlash:
      if LimitlessFlashDrainEngine.shared.handle(
        peripheralUuid: uuid,
        serviceUuid: serviceUuid,
        characteristicUuid: charUuid,
        value: data
      ) {
        return
      }
    case .batchAudio:
      if OmiBatchAudioWriter.shared.handle(
        peripheralUuid: uuid,
        serviceUuid: serviceUuid,
        characteristicUuid: charUuid,
        value: data
      ) {
        return
      }
    case .dart:
      break
    }

    let typedData = FlutterStandardTypedData(bytes: data)
    #if DEBUG
      recordPigeonNotificationSent()
    #endif
    flutterApi?.onCharacteristicValueUpdated(
      peripheralUuid: uuid,
      serviceUuid: serviceUuid,
      characteristicUuid: charUuid,
      value: typedData
    ) { [weak self] _ in
      #if DEBUG
        self?.recordPigeonNotificationCompleted()
      #endif
    }
  }

  func peripheral(
    _ peripheral: CBPeripheral, didWriteValueFor characteristic: CBCharacteristic, error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)
    guard let context = characteristicContexts[ObjectIdentifier(characteristic)],
      context.peripheralUuid == uuid
    else {
      return
    }

    let result: Result<Data?, Error> = error.map { .failure($0) } ?? .success(nil)
    _ = operationSchedulers[uuid]?.completeExpected(
      sessionId: context.sessionId,
      kind: .writeWithResponse,
      target: context.target,
      result: result
    )
  }

  func peripheral(
    _ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic,
    error: Error?
  ) {
    let uuid = peripheralUuidString(peripheral)
    let charUuid = fullUuidString(characteristic.uuid)
    guard let context = characteristicContexts[ObjectIdentifier(characteristic)],
      context.peripheralUuid == uuid
    else {
      return
    }
    let requestedState = operationSchedulers[uuid]?.activeToken?.kind
    let completed: Bool
    switch requestedState {
    case .setNotifications(let enabled):
      if let error {
        completed =
          operationSchedulers[uuid]?.failExpectedAndInvalidate(
            sessionId: context.sessionId,
            kind: .setNotifications(enabled),
            target: context.target,
            error: error
          ) == true
      } else if BleGattNotificationStateAdmission.evaluate(
        requestedEnabled: enabled,
        actualIsNotifying: characteristic.isNotifying
      ) == .ignoreMismatchedState {
        completed = false
      } else {
        completed =
          operationSchedulers[uuid]?.completeExpected(
            sessionId: context.sessionId,
            kind: .setNotifications(enabled),
            target: context.target,
            result: .success(nil)
          ) == true
      }
    default:
      completed = false
    }

    guard completed else {
      NSLog("[OmiBle] Ignoring stale notification-state callback for \(charUuid)")
      return
    }

    if let error = error {
      NSLog(
        "[OmiBle] Failed to update notification state for \(charUuid): \(error.localizedDescription)"
      )
      pendingWritesWithoutResponse.removeValue(forKey: uuid)
      centralManager.cancelPeripheralConnection(peripheral)
    } else {
      NSLog(
        "[OmiBle] Notification state updated for \(charUuid): isNotifying=\(characteristic.isNotifying)"
      )
    }
  }

  func peripheralIsReady(toSendWriteWithoutResponse peripheral: CBPeripheral) {
    let uuid = peripheralUuidString(peripheral)
    guard let pending = pendingWritesWithoutResponse.removeValue(forKey: uuid),
      let context = characteristicContexts[ObjectIdentifier(pending.characteristic)],
      context.peripheralUuid == uuid,
      context.sessionId == pending.token.sessionId,
      operationSchedulers[uuid]?.activeToken == pending.token
    else {
      return
    }

    peripheral.writeValue(pending.data, for: pending.characteristic, type: .withoutResponse)
    operationSchedulers[uuid]?.complete(token: pending.token, result: .success(nil))
  }
}
