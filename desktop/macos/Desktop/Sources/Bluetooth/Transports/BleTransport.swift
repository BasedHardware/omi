@preconcurrency import Combine
@preconcurrency import CoreBluetooth
import Foundation
import os.log

private enum BLESingletonOperation: String, Hashable, Sendable {
  case value
}

private struct BLEDiscoveredServices: @unchecked Sendable {
  let values: [CBService]
}

/// BLE transport implementation using CoreBluetooth.
///
/// CoreBluetooth remains the physical driver. Logical session identity belongs
/// to `DeviceSessionCoordinator`; this transport accepts only events for its
/// peripheral and carries that coordinator-assigned generation for fencing.
@MainActor
final class BleTransport: NSObject, DeviceTransport {
  let deviceId: String
  let sessionGeneration: UInt64

  var state: DeviceTransportState { transportState }
  var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> {
    connectionStateSubject.eraseToAnyPublisher()
  }

  private let physicalDriver: any BLEPhysicalDriving
  private let logger = Logger(subsystem: "me.omi.desktop", category: "BleTransport")

  private var transportState: DeviceTransportState = .disconnected
  private let connectionStateSubject = PassthroughSubject<DeviceTransportState, Never>()
  private var discoveredServices: [CBService] = []
  private var pendingCharacteristicServices: Set<ObjectIdentifier> = []
  private var characteristicStreams: [String: CharacteristicStreamBroadcaster] = [:]
  private var isDisposed = false
  private var isConnectionInvalidated = false
  private var didRequestPhysicalDisconnect = false
  private var connectionLease: BluetoothConnectionLease?

  nonisolated(unsafe) private var centralEventSubscription: AnyCancellable?
  private var centralEventContinuation: AsyncStream<BluetoothCentralEvent>.Continuation?
  private var centralEventTask: Task<Void, Never>?

  private let connectOperations: DeviceOperationBroker<BLESingletonOperation, Void>
  private let serviceOperations: DeviceOperationBroker<BLESingletonOperation, BLEDiscoveredServices>
  private let characteristicDiscoveryOperations: DeviceOperationBroker<BLESingletonOperation, Void>
  private let readOperations: DeviceOperationBroker<String, Data>
  private let writeOperations: DeviceOperationBroker<String, Void>

  private var connectHandle: DeviceOperationHandle<BLESingletonOperation>?
  private var serviceHandle: DeviceOperationHandle<BLESingletonOperation>?
  private var characteristicDiscoveryHandle: DeviceOperationHandle<BLESingletonOperation>?
  private let readGate = UncorrelatedOperationGate<String>()
  private let writeGate = UncorrelatedOperationGate<String>()

  convenience init(
    peripheral: CBPeripheral,
    connectionController: any BluetoothCentralConnectionControlling,
    centralEvents: AnyPublisher<BluetoothCentralEvent, Never>,
    sessionGeneration: UInt64,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) {
    self.init(
      physicalDriver: CoreBluetoothPhysicalDriver(
        peripheral: peripheral,
        connectionController: connectionController
      ),
      centralEvents: centralEvents,
      sessionGeneration: sessionGeneration,
      operationClock: operationClock
    )
  }

  init(
    physicalDriver: any BLEPhysicalDriving,
    centralEvents: AnyPublisher<BluetoothCentralEvent, Never>,
    sessionGeneration: UInt64,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) {
    self.physicalDriver = physicalDriver
    self.deviceId = physicalDriver.identifier.uuidString
    self.sessionGeneration = sessionGeneration
    self.connectOperations = DeviceOperationBroker(clock: operationClock)
    self.serviceOperations = DeviceOperationBroker(clock: operationClock)
    self.characteristicDiscoveryOperations = DeviceOperationBroker(clock: operationClock)
    self.readOperations = DeviceOperationBroker(clock: operationClock)
    self.writeOperations = DeviceOperationBroker(clock: operationClock)
    super.init()

    physicalDriver.delegate = self
    let (eventStream, eventContinuation) = AsyncStream.makeStream(
      of: BluetoothCentralEvent.self
    )
    centralEventContinuation = eventContinuation
    centralEventSubscription = centralEvents.sink { event in
      eventContinuation.yield(event)
    }
    centralEventTask = Task { @MainActor [weak self] in
      for await event in eventStream {
        guard let self else { return }
        await self.handleCentralEvent(event)
      }
    }
  }

  deinit {
    centralEventSubscription?.cancel()
    centralEventContinuation?.finish()
    centralEventTask?.cancel()
  }

  func connect() async throws {
    guard !isDisposed else { throw DeviceTransportError.disposed }
    guard !isConnectionInvalidated else {
      throw DeviceTransportError.connectionFailed("Transport session must be recreated")
    }
    guard transportState != .connected else { return }

    updateState(.connecting)
    do {
      _ = try await connectOperations.perform(
        key: .value,
        timeout: .seconds(10),
        onTerminal: { [weak self] handle, _ in
          guard self?.connectHandle == handle else { return }
          self?.connectHandle = nil
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        self.connectHandle = handle
        self.connectionLease = try self.physicalDriver.connect(
          sessionGeneration: self.sessionGeneration
        )
      }
      try ensureConnectionIsValid()

      let services = try await serviceOperations.perform(
        key: .value,
        timeout: .seconds(10),
        onTerminal: { [weak self] handle, _ in
          guard self?.serviceHandle == handle else { return }
          self?.serviceHandle = nil
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        self.serviceHandle = handle
        self.physicalDriver.discoverServices(nil)
      }
      try ensureConnectionIsValid()
      discoveredServices = services.values

      if !discoveredServices.isEmpty {
        _ = try await characteristicDiscoveryOperations.perform(
          key: .value,
          timeout: .seconds(10),
          onTerminal: { [weak self] handle, _ in
            guard self?.characteristicDiscoveryHandle == handle else { return }
            self?.characteristicDiscoveryHandle = nil
          }
        ) { [weak self] handle in
          guard let self else { throw DeviceTransportError.disposed }
          self.characteristicDiscoveryHandle = handle
          self.pendingCharacteristicServices = Set(
            self.discoveredServices.map(ObjectIdentifier.init)
          )
          for service in self.discoveredServices {
            self.physicalDriver.discoverCharacteristics(nil, for: service)
          }
        }
      }
      try ensureConnectionIsValid()

      updateState(.connected)
      logger.info("Connected to device \(self.deviceId), generation \(self.sessionGeneration)")
    } catch {
      isConnectionInvalidated = true
      await cancelPendingOperations(reason: .cancelled)
      requestPhysicalDisconnectIfNeeded()
      updateState(.disconnected)
      throw DeviceTransportError.connectionFailed(error.localizedDescription)
    }
  }

  func disconnect() async {
    guard !isDisposed else { return }
    await drainSession()
  }

  func dispose() async {
    guard !isDisposed else { return }
    // Claim disposal before the first suspension so concurrent callers
    // cannot start a second drain. `drainSession` deliberately has no
    // disposed guard; disposal must still cancel every pending operation.
    isDisposed = true
    await drainSession()
    centralEventSubscription?.cancel()
    centralEventSubscription = nil
    centralEventContinuation?.finish()
    centralEventContinuation = nil
    centralEventTask?.cancel()
    centralEventTask = nil
    physicalDriver.delegate = nil
    readGate.reset()
    writeGate.reset()
    logger.debug("Transport disposed for device \(self.deviceId), generation \(self.sessionGeneration)")
  }

  private func drainSession() async {
    isConnectionInvalidated = true

    if transportState != .disconnected {
      updateState(.disconnecting)
    }

    await cancelPendingOperations(reason: .cancelled)
    finishCharacteristicStreams()
    requestPhysicalDisconnectIfNeeded()
    updateState(.disconnected)
    logger.info("Disconnected from device \(self.deviceId), generation \(self.sessionGeneration)")
  }

  func isConnected() async -> Bool {
    physicalDriver.state == .connected && transportState == .connected
  }

  func ping() async -> Bool {
    guard physicalDriver.state == .connected else { return false }
    physicalDriver.readRSSI()
    return true
  }

  func getCharacteristicStream(
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID
  ) -> AsyncThrowingStream<Data, Error> {
    guard !isDisposed else {
      return failedCharacteristicStream(error: DeviceTransportError.disposed)
    }
    guard transportState == .connected else {
      return failedCharacteristicStream(error: DeviceTransportError.notConnected)
    }

    let key = streamKey(serviceUUID: serviceUUID, characteristicUUID: characteristicUUID)
    if let existing = characteristicStreams[key] {
      return existing.makeStream()
    }

    guard
      let characteristic = findCharacteristic(
        serviceUUID: serviceUUID,
        characteristicUUID: characteristicUUID
      )
    else {
      return failedCharacteristicStream(
        error: DeviceTransportError.characteristicNotFound(characteristicUUID)
      )
    }

    let broadcaster = CharacteristicStreamBroadcaster()
    characteristicStreams[key] = broadcaster
    physicalDriver.setNotifyValue(true, for: characteristic)
    logger.debug("Enabled notifications for \(characteristicUUID.uuidString)")
    return broadcaster.makeStream()
  }

  func readCharacteristic(
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID
  ) async throws -> Data {
    guard !isDisposed else { throw DeviceTransportError.disposed }
    guard transportState == .connected else { throw DeviceTransportError.notConnected }
    guard
      let characteristic = findCharacteristic(
        serviceUUID: serviceUUID,
        characteristicUUID: characteristicUUID
      )
    else {
      throw DeviceTransportError.characteristicNotFound(characteristicUUID)
    }

    let key = operationKey(
      serviceUUIDString: serviceUUID.uuidString,
      characteristicUUIDString: characteristicUUID.uuidString
    )
    guard readGate.canStart(key) else {
      throw DeviceTransportError.readFailed(
        "A previous read has an uncorrelated callback; reconnect the device"
      )
    }
    do {
      return try await readOperations.perform(
        key: key,
        timeout: .seconds(5),
        onTerminal: { [weak self] handle, termination in
          self?.readGate.terminal(handle: handle, termination: termination)
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        guard self.readGate.register(handle) else {
          throw DeviceTransportError.readFailed(
            "Read callback identity is no longer trustworthy"
          )
        }
        self.physicalDriver.readValue(for: characteristic)
      }
    } catch let error as DeviceOperationBrokerError {
      throw DeviceTransportError.readFailed(error.localizedDescription)
    }
  }

  func writeCharacteristic(
    data: Data,
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID,
    withResponse: Bool
  ) async throws {
    guard !isDisposed else { throw DeviceTransportError.disposed }
    guard transportState == .connected else { throw DeviceTransportError.notConnected }
    guard
      let characteristic = findCharacteristic(
        serviceUUID: serviceUUID,
        characteristicUUID: characteristicUUID
      )
    else {
      throw DeviceTransportError.characteristicNotFound(characteristicUUID)
    }

    let writeType: CBCharacteristicWriteType = withResponse ? .withResponse : .withoutResponse
    guard withResponse else {
      physicalDriver.writeValue(data, for: characteristic, type: writeType)
      return
    }

    let key = operationKey(
      serviceUUIDString: serviceUUID.uuidString,
      characteristicUUIDString: characteristicUUID.uuidString
    )
    guard writeGate.canStart(key) else {
      throw DeviceTransportError.writeFailed(
        "A previous write has an uncorrelated callback; reconnect the device"
      )
    }
    do {
      _ = try await writeOperations.perform(
        key: key,
        timeout: .seconds(5),
        onTerminal: { [weak self] handle, termination in
          self?.writeGate.terminal(handle: handle, termination: termination)
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        guard self.writeGate.register(handle) else {
          throw DeviceTransportError.writeFailed(
            "Write callback identity is no longer trustworthy"
          )
        }
        self.physicalDriver.writeValue(data, for: characteristic, type: writeType)
      }
    } catch let error as DeviceOperationBrokerError {
      throw DeviceTransportError.writeFailed(error.localizedDescription)
    }
  }

  var services: [CBService] { discoveredServices }

  private func handleCentralEvent(_ event: BluetoothCentralEvent) async {
    switch event {
    case .connected(let lease):
      guard lease == connectionLease else { return }
      guard !isConnectionInvalidated else {
        requestPhysicalDisconnectIfNeeded()
        return
      }
      guard let handle = connectHandle else { return }
      connectHandle = nil
      await connectOperations.succeed(handle: handle, value: ())

    case .failedToConnect(let lease, let reason):
      guard lease == connectionLease else { return }
      connectionLease = nil
      isConnectionInvalidated = true
      if let handle = connectHandle {
        connectHandle = nil
        await connectOperations.fail(handle: handle, reason: reason)
      }
      await cancelPendingOperations(reason: .disconnected)
      updateState(.disconnected)

    case .disconnected(let lease, let reason):
      guard lease == connectionLease else { return }
      connectionLease = nil
      isConnectionInvalidated = true
      if let handle = connectHandle {
        connectHandle = nil
        await connectOperations.fail(
          handle: handle,
          reason: reason ?? "Disconnected during connection"
        )
      }
      await cancelPendingOperations(reason: .disconnected)
      finishCharacteristicStreams(
        throwing: reason.map(DeviceOperationBrokerError.failed)
          ?? DeviceOperationBrokerError.disconnected
      )
      updateState(.disconnected)
    }
  }

  func didDiscoverServices(_ services: [CBService], error: Error?) async {
    guard let handle = serviceHandle else { return }
    serviceHandle = nil
    if let error {
      await serviceOperations.fail(handle: handle, reason: error.localizedDescription)
    } else {
      await serviceOperations.succeed(
        handle: handle,
        value: BLEDiscoveredServices(values: services)
      )
    }
  }

  func didDiscoverCharacteristics(for service: CBService, error: Error?) async {
    if let error {
      guard let handle = characteristicDiscoveryHandle else { return }
      characteristicDiscoveryHandle = nil
      pendingCharacteristicServices.removeAll()
      await characteristicDiscoveryOperations.fail(
        handle: handle,
        reason: error.localizedDescription
      )
      return
    }

    pendingCharacteristicServices.remove(ObjectIdentifier(service))
    logger.debug("Discovered \(service.characteristics?.count ?? 0) characteristics for \(service.uuid)")
    guard pendingCharacteristicServices.isEmpty,
      let handle = characteristicDiscoveryHandle
    else { return }
    characteristicDiscoveryHandle = nil
    await characteristicDiscoveryOperations.succeed(handle: handle, value: ())
  }

  func didUpdateValue(for characteristic: CBCharacteristic, error: Error?) async {
    let characteristicKey = operationKey(
      serviceUUIDString: characteristic.service?.uuid.uuidString ?? "",
      characteristicUUIDString: characteristic.uuid.uuidString
    )

    if let handle = readGate.takeHandleForCallback(key: characteristicKey) {
      if let error {
        await readOperations.fail(
          handle: handle,
          reason: error.localizedDescription
        )
      } else {
        await readOperations.succeed(
          handle: handle,
          value: characteristic.value ?? Data()
        )
      }
      return
    }

    // CoreBluetooth uses the same delegate callback for explicit reads and
    // subscribed notifications. A timed-out read poisons only the read
    // operation identity; it must never suppress later notifications. A
    // live read was resolved above, so only unclaimed values broadcast.
    let notificationKey = streamKey(
      serviceUUIDString: characteristic.service?.uuid.uuidString ?? "",
      characteristicUUIDString: characteristic.uuid.uuidString
    )
    if error == nil, let value = characteristic.value {
      characteristicStreams[notificationKey]?.yield(value)
    }
  }

  func didWriteValue(for characteristic: CBCharacteristic, error: Error?) async {
    let key = operationKey(
      serviceUUIDString: characteristic.service?.uuid.uuidString ?? "",
      characteristicUUIDString: characteristic.uuid.uuidString
    )
    guard let handle = writeGate.takeHandleForCallback(key: key) else { return }

    if let error {
      await writeOperations.fail(handle: handle, reason: error.localizedDescription)
    } else {
      await writeOperations.succeed(handle: handle, value: ())
    }
  }

  private func cancelPendingOperations(reason: DeviceOperationBrokerError) async {
    await connectOperations.cancelAll(reason: reason)
    await serviceOperations.cancelAll(reason: reason)
    await characteristicDiscoveryOperations.cancelAll(reason: reason)
    await readOperations.cancelAll(reason: reason)
    await writeOperations.cancelAll(reason: reason)
    connectHandle = nil
    serviceHandle = nil
    characteristicDiscoveryHandle = nil
    pendingCharacteristicServices.removeAll()
  }

  private func requestPhysicalDisconnectIfNeeded() {
    guard !didRequestPhysicalDisconnect else { return }
    didRequestPhysicalDisconnect = true
    physicalDriver.disconnect()
  }

  private func ensureConnectionIsValid() throws {
    guard !isDisposed, !isConnectionInvalidated else {
      throw DeviceTransportError.connectionFailed("Connection was superseded")
    }
  }

  private func finishCharacteristicStreams(throwing error: Error? = nil) {
    for handler in characteristicStreams.values {
      handler.finish(throwing: error)
    }
    characteristicStreams.removeAll()
  }

  private func updateState(_ newState: DeviceTransportState) {
    guard transportState != newState else { return }
    transportState = newState
    connectionStateSubject.send(newState)
  }

  private func findCharacteristic(
    serviceUUID: CBUUID,
    characteristicUUID: CBUUID
  ) -> CBCharacteristic? {
    guard
      let service = discoveredServices.first(where: {
        $0.uuid.uuidString.caseInsensitiveCompare(serviceUUID.uuidString) == .orderedSame
      })
    else {
      return nil
    }

    return service.characteristics?.first(where: {
      $0.uuid.uuidString.caseInsensitiveCompare(characteristicUUID.uuidString) == .orderedSame
    })
  }

  private func streamKey(serviceUUID: CBUUID, characteristicUUID: CBUUID) -> String {
    streamKey(
      serviceUUIDString: serviceUUID.uuidString,
      characteristicUUIDString: characteristicUUID.uuidString
    )
  }

  private func streamKey(serviceUUIDString: String, characteristicUUIDString: String) -> String {
    "\(serviceUUIDString.lowercased()):\(characteristicUUIDString.lowercased())"
  }

  private func operationKey(
    serviceUUIDString: String,
    characteristicUUIDString: String
  ) -> String {
    streamKey(
      serviceUUIDString: serviceUUIDString,
      characteristicUUIDString: characteristicUUIDString
    )
  }

  private func failedCharacteristicStream(
    error: Error
  ) -> AsyncThrowingStream<Data, Error> {
    AsyncThrowingStream { continuation in
      continuation.finish(throwing: error)
    }
  }
}

extension BleTransport: CBPeripheralDelegate {
  nonisolated func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
    let services = peripheral.services ?? []
    Task { @MainActor [weak self] in
      await self?.didDiscoverServices(services, error: error)
    }
  }

  nonisolated func peripheral(
    _ peripheral: CBPeripheral,
    didDiscoverCharacteristicsFor service: CBService,
    error: Error?
  ) {
    Task { @MainActor [weak self] in
      await self?.didDiscoverCharacteristics(for: service, error: error)
    }
  }

  nonisolated func peripheral(
    _ peripheral: CBPeripheral,
    didUpdateValueFor characteristic: CBCharacteristic,
    error: Error?
  ) {
    Task { @MainActor [weak self] in
      await self?.didUpdateValue(for: characteristic, error: error)
    }
  }

  nonisolated func peripheral(
    _ peripheral: CBPeripheral,
    didWriteValueFor characteristic: CBCharacteristic,
    error: Error?
  ) {
    Task { @MainActor [weak self] in
      await self?.didWriteValue(for: characteristic, error: error)
    }
  }

  nonisolated func peripheral(
    _ peripheral: CBPeripheral,
    didUpdateNotificationStateFor characteristic: CBCharacteristic,
    error: Error?
  ) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      if let error {
        self.logger.warning(
          "Failed to update notification state for \(characteristic.uuid): \(error.localizedDescription)")
      } else {
        self.logger.debug("Notification state updated for \(characteristic.uuid): \(characteristic.isNotifying)")
      }
    }
  }
}

@MainActor
private final class CharacteristicStreamBroadcaster {
  typealias Continuation = AsyncThrowingStream<Data, Error>.Continuation

  private var continuations: [UUID: Continuation] = [:]

  func makeStream() -> AsyncThrowingStream<Data, Error> {
    let subscriberID = UUID()
    return AsyncThrowingStream { continuation in
      continuations[subscriberID] = continuation
      continuation.onTermination = { @Sendable [weak self] _ in
        Task { @MainActor [weak self] in
          self?.removeSubscriber(subscriberID)
        }
      }
    }
  }

  func yield(_ data: Data) {
    var terminatedSubscribers: [UUID] = []
    for (subscriberID, continuation) in continuations {
      if case .terminated = continuation.yield(data) {
        terminatedSubscribers.append(subscriberID)
      }
    }
    for subscriberID in terminatedSubscribers {
      continuations.removeValue(forKey: subscriberID)
    }
  }

  func finish(throwing error: Error? = nil) {
    let currentContinuations = Array(continuations.values)
    continuations.removeAll()
    for continuation in currentContinuations {
      if let error {
        continuation.finish(throwing: error)
      } else {
        continuation.finish()
      }
    }
  }

  private func removeSubscriber(_ subscriberID: UUID) {
    continuations.removeValue(forKey: subscriberID)
  }
}
