import Foundation

enum DeviceSessionPhase: Equatable, Sendable {
  case idle
  case connecting
  case ready
  case disconnecting
  case waitingToReconnect(attempt: Int)

  var isConnecting: Bool {
    if case .connecting = self { return true }
    return false
  }

  var isReady: Bool {
    if case .ready = self { return true }
    return false
  }

  var allowsConnectionAttempt: Bool {
    switch self {
    case .idle, .waitingToReconnect:
      return true
    case .connecting, .ready, .disconnecting:
      return false
    }
  }
}

struct DeviceSessionSnapshot: Equatable {
  fileprivate(set) var generation: UInt64
  fileprivate(set) var phase: DeviceSessionPhase
  fileprivate(set) var pairedDevice: BtDevice?
  fileprivate(set) var connectedDevice: BtDevice?
  fileprivate(set) var failureMessage: String?

  static func initial(pairedDevice: BtDevice?) -> DeviceSessionSnapshot {
    DeviceSessionSnapshot(
      generation: 0,
      phase: .idle,
      pairedDevice: pairedDevice,
      connectedDevice: nil,
      failureMessage: nil
    )
  }
}

struct DeviceReconnectRequest {
  let device: BtDevice
  fileprivate let generation: UInt64
  fileprivate let attempt: Int
}

enum DeviceSessionCoordinatorError: LocalizedError, Equatable {
  case connectionAlreadyActive
  case connectionUnavailable
  case superseded

  var errorDescription: String? {
    switch self {
    case .connectionAlreadyActive:
      return "A device connection is already active"
    case .connectionUnavailable:
      return "The device is not currently available over Bluetooth"
    case .superseded:
      return "The device connection was superseded"
    }
  }
}

@MainActor
protocol DeviceSessionScheduledAction: AnyObject {
  func cancel()
}

@MainActor
protocol DeviceSessionScheduling: AnyObject {
  func schedule(
    after delay: Duration,
    action: @escaping @MainActor () -> Void
  ) -> any DeviceSessionScheduledAction
}

@MainActor
final class DeviceSessionTaskScheduler: DeviceSessionScheduling {
  private final class ScheduledAction: DeviceSessionScheduledAction {
    let task: Task<Void, Never>

    init(task: Task<Void, Never>) {
      self.task = task
    }

    func cancel() {
      task.cancel()
    }
  }

  private let clock: any DeviceOperationClock

  init(clock: any DeviceOperationClock = ContinuousDeviceOperationClock()) {
    self.clock = clock
  }

  func schedule(
    after delay: Duration,
    action: @escaping @MainActor () -> Void
  ) -> any DeviceSessionScheduledAction {
    let task = Task { @MainActor [clock] in
      do {
        if delay > .zero {
          try await clock.sleep(for: delay)
        }
      } catch {
        return
      }
      guard !Task.isCancelled else { return }
      action()
    }
    return ScheduledAction(task: task)
  }
}

/// Canonical owner for the logical lifecycle of one paired Bluetooth device.
///
/// Every connect attempt receives a monotonically increasing generation. The
/// coordinator accepts callbacks only from the current connection object and
/// generation, which makes late CoreBluetooth callbacks harmless.
@MainActor
final class DeviceSessionCoordinator: DeviceConnectionDelegate {
  typealias ConnectionFactory = @MainActor (BtDevice, UInt64) -> DeviceConnection?

  private let connectionFactory: ConnectionFactory
  private let scheduler: any DeviceSessionScheduling
  private let reconnectDelay: Duration
  private let autoReconnectEnabled: Bool

  private(set) var snapshot: DeviceSessionSnapshot
  private(set) var activeConnection: DeviceConnection?

  private var reconnectAttempt = 0
  private var scheduledReconnect: (any DeviceSessionScheduledAction)?

  var onSnapshotChanged: ((DeviceSessionSnapshot) -> Void)?
  var onReconnectRequested: ((DeviceReconnectRequest) -> Void)?
  var onDiscoveryRequested: (() -> Void)?
  var onSessionEnded: (() -> Void)?
  var onFallDetected: ((AccelerometerData) -> Void)?

  init(
    pairedDevice: BtDevice?,
    connectionFactory: @escaping ConnectionFactory,
    scheduler: any DeviceSessionScheduling,
    reconnectDelay: Duration = .seconds(15),
    autoReconnectEnabled: Bool = true
  ) {
    self.snapshot = .initial(pairedDevice: pairedDevice)
    self.connectionFactory = connectionFactory
    self.scheduler = scheduler
    self.reconnectDelay = reconnectDelay
    self.autoReconnectEnabled = autoReconnectEnabled
  }

  func connect(to device: BtDevice) async throws -> DeviceConnection {
    try await connect(to: device, reconnectRequest: nil)
  }

  func reconnect(_ request: DeviceReconnectRequest) async throws -> DeviceConnection {
    try await connect(to: request.device, reconnectRequest: request)
  }

  private func connect(
    to device: BtDevice,
    reconnectRequest: DeviceReconnectRequest?
  ) async throws -> DeviceConnection {
    let isReconnectAttempt = reconnectRequest != nil
    if let reconnectRequest {
      guard snapshot.generation == reconnectRequest.generation,
        snapshot.phase == .waitingToReconnect(attempt: reconnectRequest.attempt),
        snapshot.pairedDevice?.id == reconnectRequest.device.id
      else {
        throw DeviceSessionCoordinatorError.superseded
      }
    } else {
      guard snapshot.phase.allowsConnectionAttempt else {
        throw DeviceSessionCoordinatorError.connectionAlreadyActive
      }
    }

    cancelScheduledReconnect()
    let generation = nextGeneration()
    snapshot.phase = .connecting
    snapshot.connectedDevice = nil
    snapshot.failureMessage = nil
    publishSnapshot()

    guard let connection = connectionFactory(device, generation) else {
      let error = DeviceSessionCoordinatorError.connectionUnavailable
      recordConnectionFailure(error.localizedDescription)
      if isReconnectAttempt {
        scheduleReconnectIfNeeded(after: reconnectDelay)
      }
      throw error
    }

    activeConnection = connection
    connection.delegate = self

    do {
      try await connection.connect()
    } catch {
      let wasCurrent = isCurrent(connection)
      if wasCurrent {
        activeConnection = nil
        recordConnectionFailure(error.localizedDescription)
        if isReconnectAttempt {
          scheduleReconnectIfNeeded(after: reconnectDelay)
        }
      }
      await connection.disconnect()
      guard wasCurrent else {
        throw DeviceSessionCoordinatorError.superseded
      }
      throw error
    }

    guard isCurrent(connection), snapshot.phase.isConnecting else {
      await connection.disconnect()
      throw DeviceSessionCoordinatorError.superseded
    }

    reconnectAttempt = 0
    snapshot.phase = .ready
    snapshot.pairedDevice = connection.device
    snapshot.connectedDevice = connection.device
    snapshot.failureMessage = nil
    publishSnapshot()
    return connection
  }

  func disconnect(reconnectAfter delay: Duration? = .zero) async {
    cancelScheduledReconnect()
    guard let connection = activeConnection else {
      if let delay {
        scheduleReconnectIfNeeded(after: delay)
      }
      return
    }

    let teardownGeneration = nextGeneration()
    snapshot.phase = .disconnecting
    snapshot.connectedDevice = nil
    snapshot.failureMessage = nil
    publishSnapshot()

    activeConnection = nil
    await connection.disconnect()

    guard snapshot.generation == teardownGeneration,
      snapshot.phase == .disconnecting,
      activeConnection == nil
    else {
      return
    }
    snapshot.phase = .idle
    publishSnapshot()
    onSessionEnded?()

    if let delay {
      scheduleReconnectIfNeeded(after: delay)
    }
  }

  func unpair() async {
    cancelScheduledReconnect()
    let teardownGeneration = nextGeneration()
    let connection = activeConnection
    activeConnection = nil

    snapshot.phase = connection == nil ? .idle : .disconnecting
    snapshot.connectedDevice = nil
    snapshot.pairedDevice = nil
    snapshot.failureMessage = nil
    publishSnapshot()

    if let connection {
      await connection.unpair()

      guard snapshot.generation == teardownGeneration,
        snapshot.phase == .disconnecting,
        activeConnection == nil,
        snapshot.pairedDevice == nil
      else {
        return
      }
      onSessionEnded?()
    }

    snapshot.phase = .idle
    publishSnapshot()
  }

  func startReconnecting() {
    scheduleReconnectIfNeeded(after: .zero)
  }

  func stopReconnecting() {
    cancelScheduledReconnect()
    if case .waitingToReconnect = snapshot.phase {
      snapshot.phase = .idle
      publishSnapshot()
    }
  }

  func isReady(generation: UInt64) -> Bool {
    snapshot.generation == generation && snapshot.phase.isReady
  }

  func deviceConnection(
    _ connection: DeviceConnection,
    didDisconnectUnexpectedly device: BtDevice
  ) {
    guard isCurrent(connection) else { return }

    activeConnection = nil
    _ = nextGeneration()
    snapshot.phase = .idle
    snapshot.connectedDevice = nil
    snapshot.failureMessage = "Device disconnected unexpectedly"
    publishSnapshot()
    onSessionEnded?()
    scheduleReconnectIfNeeded(after: .zero)
  }

  func deviceConnection(
    _ connection: DeviceConnection,
    didDetectFall data: AccelerometerData
  ) {
    guard isCurrent(connection) else { return }
    onFallDetected?(data)
  }

  private func isCurrent(_ connection: DeviceConnection) -> Bool {
    activeConnection === connection
      && connection.sessionGeneration == snapshot.generation
  }

  @discardableResult
  private func nextGeneration() -> UInt64 {
    snapshot.generation &+= 1
    return snapshot.generation
  }

  private func recordConnectionFailure(_ message: String) {
    snapshot.phase = .idle
    snapshot.connectedDevice = nil
    snapshot.failureMessage = message
    publishSnapshot()
  }

  private func scheduleReconnectIfNeeded(after delay: Duration) {
    guard autoReconnectEnabled, let pairedDevice = snapshot.pairedDevice else { return }
    guard snapshot.phase.allowsConnectionAttempt else { return }

    cancelScheduledReconnect()
    reconnectAttempt += 1
    let expectedGeneration = snapshot.generation
    let expectedAttempt = reconnectAttempt
    snapshot.phase = .waitingToReconnect(attempt: expectedAttempt)
    publishSnapshot()

    // A zero-delay attempt is the direct reconnect path. Preserve the
    // manager's cached peripheral until that attempt has run; scanning
    // clears the cache. If direct reconnect cannot build a connection,
    // `connect` schedules the delayed path below, which starts discovery.
    if delay > .zero {
      onDiscoveryRequested?()
    }

    scheduledReconnect = scheduler.schedule(after: delay) { [weak self] in
      guard let self else { return }
      guard self.snapshot.generation == expectedGeneration,
        self.snapshot.phase == .waitingToReconnect(attempt: expectedAttempt),
        self.snapshot.pairedDevice?.id == pairedDevice.id
      else {
        return
      }
      self.scheduledReconnect = nil
      self.onReconnectRequested?(
        DeviceReconnectRequest(
          device: pairedDevice,
          generation: expectedGeneration,
          attempt: expectedAttempt
        )
      )
    }
  }

  private func cancelScheduledReconnect() {
    scheduledReconnect?.cancel()
    scheduledReconnect = nil
  }

  private func publishSnapshot() {
    onSnapshotChanged?(snapshot)
  }
}
