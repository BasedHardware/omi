import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class DeviceSessionCoordinatorTests: XCTestCase {
  func testLateSuccessAfterDisconnectIsSuperseded() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    connection.suspendConnect = true
    let coordinator = makeCoordinator(connection: connection)

    let connectTask = Task { try await coordinator.connect(to: bluetoothReliabilityTestDevice) }
    await waitForBluetoothReliabilityCondition { connection.connectCallCount == 1 }

    await coordinator.disconnect(reconnectAfter: nil)
    connection.completeConnectSuccessfully()

    await assertSuperseded(connectTask)
    XCTAssertNil(coordinator.activeConnection)
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
    XCTAssertNil(coordinator.snapshot.connectedDevice)
  }

  func testLateFailureAfterUnpairIsSuperseded() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    connection.suspendConnect = true
    let coordinator = makeCoordinator(connection: connection)

    let connectTask = Task { try await coordinator.connect(to: bluetoothReliabilityTestDevice) }
    await waitForBluetoothReliabilityCondition { connection.connectCallCount == 1 }

    await coordinator.unpair()
    connection.failConnect(BluetoothReliabilityTestError.expected)

    await assertSuperseded(connectTask)
    XCTAssertNil(coordinator.activeConnection)
    XCTAssertNil(coordinator.snapshot.pairedDevice)
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
  }

  func testUnexpectedDisconnectTriesCachedPeripheralBeforeDiscovery() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    let scheduler = ManualDeviceSessionScheduler()
    let coordinator = DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { _, _ in connection },
      scheduler: scheduler,
      reconnectDelay: .seconds(15),
      autoReconnectEnabled: true
    )
    var discoveryCount = 0
    var reconnectRequests: [DeviceReconnectRequest] = []
    coordinator.onDiscoveryRequested = { discoveryCount += 1 }
    coordinator.onReconnectRequested = { reconnectRequests.append($0) }

    _ = try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    coordinator.deviceConnection(
      connection,
      didDisconnectUnexpectedly: bluetoothReliabilityTestDevice
    )

    XCTAssertEqual(coordinator.snapshot.phase, .waitingToReconnect(attempt: 1))
    XCTAssertEqual(discoveryCount, 0)
    XCTAssertEqual(scheduler.activeActionCount, 1)
    scheduler.runNext()
    XCTAssertEqual(reconnectRequests.map(\.device), [bluetoothReliabilityTestDevice])
    XCTAssertEqual(discoveryCount, 0)
  }

  func testUnpairInvalidatesReconnectRequestAfterSchedulerCallback() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    let scheduler = ManualDeviceSessionScheduler()
    let coordinator = DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { _, _ in connection },
      scheduler: scheduler,
      autoReconnectEnabled: true
    )
    var capturedRequest: DeviceReconnectRequest?
    coordinator.onReconnectRequested = { capturedRequest = $0 }

    _ = try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    coordinator.deviceConnection(
      connection,
      didDisconnectUnexpectedly: bluetoothReliabilityTestDevice
    )
    scheduler.runNext()
    let request = try XCTUnwrap(capturedRequest)

    await coordinator.unpair()
    let reconnect = Task { try await coordinator.reconnect(request) }
    await assertSuperseded(reconnect)
    XCTAssertNil(coordinator.snapshot.pairedDevice)
    XCTAssertEqual(connection.connectCallCount, 1)
  }

  func testStopReconnectingInvalidatesAlreadyDeliveredRequest() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    let scheduler = ManualDeviceSessionScheduler()
    let coordinator = DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { _, _ in connection },
      scheduler: scheduler,
      autoReconnectEnabled: true
    )
    var capturedRequest: DeviceReconnectRequest?
    coordinator.onReconnectRequested = { capturedRequest = $0 }

    _ = try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    coordinator.deviceConnection(
      connection,
      didDisconnectUnexpectedly: bluetoothReliabilityTestDevice
    )
    scheduler.runNext()
    let request = try XCTUnwrap(capturedRequest)

    coordinator.stopReconnecting()
    let reconnect = Task { try await coordinator.reconnect(request) }
    await assertSuperseded(reconnect)
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
    XCTAssertEqual(connection.connectCallCount, 1)
  }

  func testUnavailableReconnectStartsDiscoveryForDelayedRetry() async throws {
    let scheduler = ManualDeviceSessionScheduler()
    let coordinator = DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { _, _ in nil },
      scheduler: scheduler,
      reconnectDelay: .seconds(15),
      autoReconnectEnabled: true
    )
    var discoveryCount = 0
    var reconnectRequest: DeviceReconnectRequest?
    coordinator.onDiscoveryRequested = { discoveryCount += 1 }
    coordinator.onReconnectRequested = { reconnectRequest = $0 }

    coordinator.startReconnecting()
    scheduler.runNext()
    let request = try XCTUnwrap(reconnectRequest)

    do {
      _ = try await coordinator.reconnect(request)
      XCTFail("Expected an unavailable connection")
    } catch let error as DeviceSessionCoordinatorError {
      XCTAssertEqual(error, .connectionUnavailable)
    } catch {
      XCTFail("Unexpected error: \(error)")
    }

    XCTAssertEqual(discoveryCount, 1)
    XCTAssertEqual(coordinator.snapshot.phase, .waitingToReconnect(attempt: 2))
    XCTAssertEqual(scheduler.activeActionCount, 1)
  }

  func testExplicitDifferentDeviceFailureDoesNotRetryPersistedPairing() async {
    let selectedDevice = BtDevice(
      id: "99999999-8888-7777-6666-555555555555",
      name: "Selected Bee",
      type: .bee,
      rssi: -35
    )
    let scheduler = ManualDeviceSessionScheduler()
    var factoryDevices: [BtDevice] = []
    let coordinator = DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { device, _ in
        factoryDevices.append(device)
        return nil
      },
      scheduler: scheduler,
      reconnectDelay: .seconds(15),
      autoReconnectEnabled: true
    )
    var discoveryCount = 0
    coordinator.onDiscoveryRequested = { discoveryCount += 1 }

    do {
      _ = try await coordinator.connect(to: selectedDevice)
      XCTFail("Expected selected device to be unavailable")
    } catch let error as DeviceSessionCoordinatorError {
      XCTAssertEqual(error, .connectionUnavailable)
    } catch {
      XCTFail("Unexpected error: \(error)")
    }

    XCTAssertEqual(factoryDevices, [selectedDevice])
    XCTAssertEqual(coordinator.snapshot.pairedDevice, bluetoothReliabilityTestDevice)
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
    XCTAssertEqual(discoveryCount, 0)
    XCTAssertEqual(scheduler.activeActionCount, 0)
  }

  func testConnectIsRejectedWhileDisconnectTeardownIsSuspended() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    let coordinator = makeCoordinator(connection: connection)
    _ = try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    connection.suspendDisconnect = true

    let teardown = Task {
      await coordinator.disconnect(reconnectAfter: nil)
    }
    await waitForBluetoothReliabilityCondition { connection.disconnectCallCount == 1 }
    XCTAssertEqual(coordinator.snapshot.phase, .disconnecting)

    await assertConnectionAlreadyActive {
      try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    }

    connection.completeDisconnect()
    await teardown.value
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
    XCTAssertNil(coordinator.activeConnection)
  }

  func testConnectIsRejectedWhileUnpairTeardownIsSuspended() async throws {
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice,
      sessionGeneration: 1
    )
    let coordinator = makeCoordinator(connection: connection)
    _ = try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    connection.suspendUnpair = true

    let teardown = Task {
      await coordinator.unpair()
    }
    await waitForBluetoothReliabilityCondition { connection.unpairCallCount == 1 }
    XCTAssertEqual(coordinator.snapshot.phase, .disconnecting)

    await assertConnectionAlreadyActive {
      try await coordinator.connect(to: bluetoothReliabilityTestDevice)
    }

    connection.completeUnpair()
    await teardown.value
    XCTAssertEqual(coordinator.snapshot.phase, .idle)
    XCTAssertNil(coordinator.activeConnection)
    XCTAssertNil(coordinator.snapshot.pairedDevice)
  }

  private func makeCoordinator(
    connection: SessionConnectionDouble
  ) -> DeviceSessionCoordinator {
    DeviceSessionCoordinator(
      pairedDevice: bluetoothReliabilityTestDevice,
      connectionFactory: { _, generation in
        XCTAssertEqual(generation, connection.sessionGeneration)
        return connection
      },
      scheduler: NoopDeviceSessionScheduler(),
      autoReconnectEnabled: false
    )
  }

  private func assertSuperseded(
    _ task: Task<DeviceConnection, Error>,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    do {
      _ = try await task.value
      XCTFail("Expected superseded session", file: file, line: line)
    } catch let error as DeviceSessionCoordinatorError {
      XCTAssertEqual(error, .superseded, file: file, line: line)
    } catch {
      XCTFail("Unexpected error: \(error)", file: file, line: line)
    }
  }

  private func assertConnectionAlreadyActive(
    _ operation: @escaping @MainActor () async throws -> DeviceConnection,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    do {
      _ = try await operation()
      XCTFail("Expected active-session rejection", file: file, line: line)
    } catch let error as DeviceSessionCoordinatorError {
      XCTAssertEqual(error, .connectionAlreadyActive, file: file, line: line)
    } catch {
      XCTFail("Unexpected error: \(error)", file: file, line: line)
    }
  }
}

@MainActor
final class DeviceProviderGenerationTests: XCTestCase {
  func testLateBatteryResultFromOldGenerationCannotOverwriteReplacement() async {
    let suiteName = "DeviceProviderGenerationTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { defaults.removePersistentDomain(forName: suiteName) }

    var connections: [SessionConnectionDouble] = []
    let provider = DeviceProvider(
      bluetoothManager: ReliabilityBluetoothManager(),
      userDefaults: defaults,
      notificationCenter: NotificationCenter(),
      connectionFactory: { device, generation in
        let connection = SessionConnectionDouble(
          device: device,
          sessionGeneration: generation
        )
        if connections.isEmpty {
          connection.suspendBattery = true
        } else {
          connection.batteryLevel = 77
        }
        connections.append(connection)
        return connection
      },
      storageDataChecker: { nil },
      autoReconnectEnabled: false
    )

    let firstConnect = Task { await provider.connect(to: bluetoothReliabilityTestDevice) }
    await waitForBluetoothReliabilityCondition {
      provider.isConnected
        && connections.first?.batteryCallCount == 1
    }

    await provider.disconnect()
    await provider.connect(to: bluetoothReliabilityTestDevice)
    XCTAssertEqual(provider.batteryLevel, 77)

    connections[0].completeBattery(level: 4)
    await firstConnect.value
    XCTAssertEqual(provider.batteryLevel, 77)
    XCTAssertEqual(provider.activeConnection?.sessionGeneration, 3)
    XCTAssertEqual(connections[0].batteryStreamCallCount, 0)

    connections[1].emitBattery(level: 88)
    await waitForBluetoothReliabilityCondition { provider.batteryLevel == 88 }
    connections[1].finishBatteryStream()
  }
}
