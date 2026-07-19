import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class BleTransportLifecycleTests: XCTestCase {
  func testDisposeDrainsPendingConnectAndRequestsPhysicalDisconnectExactlyOnce() async {
    let physicalDriver = FakeBLEPhysicalDriver()
    let centralEvents = PassthroughSubject<BluetoothCentralEvent, Never>()
    let transport = BleTransport(
      physicalDriver: physicalDriver,
      centralEvents: centralEvents.eraseToAnyPublisher(),
      sessionGeneration: 42
    )

    let connectTask = Task {
      try await transport.connect()
    }
    await waitForBluetoothReliabilityCondition { physicalDriver.connectCallCount == 1 }

    await transport.dispose()
    do {
      try await connectTask.value
      XCTFail("Pending connect should be cancelled by disposal")
    } catch {
      // The precise public transport wrapping is not important here; the
      // invariant is that the waiter terminates and the driver drains.
    }

    XCTAssertEqual(physicalDriver.disconnectCallCount, 1)
    XCTAssertNil(physicalDriver.delegate)
    XCTAssertEqual(transport.state, .disconnected)

    await transport.dispose()
    await transport.disconnect()
    XCTAssertEqual(physicalDriver.disconnectCallCount, 1)
  }

  func testReplacementTransportIgnoresLateConnectedEventFromOldLease() async {
    let clock = ManualDeviceOperationClock()
    let centralEvents = PassthroughSubject<BluetoothCentralEvent, Never>()
    let physicalA = FakeBLEPhysicalDriver(firstLeaseToken: 100)
    let transportA = BleTransport(
      physicalDriver: physicalA,
      centralEvents: centralEvents.eraseToAnyPublisher(),
      sessionGeneration: 1,
      operationClock: clock
    )
    let connectA = Task { try await transportA.connect() }
    await waitForBluetoothReliabilityCondition {
      let sleeperCount = await clock.sleeperCount
      return physicalA.issuedLeases.count == 1 && sleeperCount == 1
    }
    let leaseA = physicalA.issuedLeases[0]
    await clock.advanceAll()
    do { try await connectA.value } catch {}
    await transportA.dispose()

    let physicalB = FakeBLEPhysicalDriver(firstLeaseToken: 200)
    let transportB = BleTransport(
      physicalDriver: physicalB,
      centralEvents: centralEvents.eraseToAnyPublisher(),
      sessionGeneration: 2
    )
    let connectB = Task { try await transportB.connect() }
    await waitForBluetoothReliabilityCondition { physicalB.issuedLeases.count == 1 }
    let leaseB = physicalB.issuedLeases[0]

    centralEvents.send(.connected(lease: leaseA))
    await Task.yield()
    await Task.yield()
    XCTAssertEqual(physicalB.discoverServicesCallCount, 0)

    centralEvents.send(.connected(lease: leaseB))
    await waitForBluetoothReliabilityCondition { physicalB.discoverServicesCallCount == 1 }

    await transportB.dispose()
    do { try await connectB.value } catch {}
  }

  func testTimedOutReadDoesNotSuppressNotificationsOrAllowReadRetry() async throws {
    let clock = ManualDeviceOperationClock()
    let fixture = try await makeConnectedTransport(operationClock: clock)
    let transport = fixture.transport
    let physicalDriver = fixture.physicalDriver
    let service = fixture.service
    let characteristic = fixture.characteristic

    let notifications = transport.getCharacteristicStream(
      serviceUUID: service.uuid,
      characteristicUUID: characteristic.uuid
    )
    let notification = Task { () -> Data? in
      for try await value in notifications {
        return value
      }
      return nil
    }

    let read = Task {
      try await transport.readCharacteristic(
        serviceUUID: service.uuid,
        characteristicUUID: characteristic.uuid
      )
    }
    await waitForBluetoothReliabilityCondition { physicalDriver.readValueCallCount == 1 }
    await clock.advanceAll()
    do {
      _ = try await read.value
      XCTFail("Expected read timeout")
    } catch {
      // The transport wraps broker timeout details in its public error.
    }

    characteristic.value = Data([64])
    await transport.didUpdateValue(for: characteristic, error: nil)
    let streamedValue = try await notification.value
    XCTAssertEqual(streamedValue, Data([64]))

    do {
      _ = try await transport.readCharacteristic(
        serviceUUID: service.uuid,
        characteristicUUID: characteristic.uuid
      )
      XCTFail("A timed-out uncorrelated read must not be retried in-session")
    } catch let error as DeviceTransportError {
      guard case .readFailed = error else {
        return XCTFail("Unexpected transport error: \(error)")
      }
    }
    XCTAssertEqual(physicalDriver.readValueCallCount, 1)
    await transport.dispose()
  }

  func testCharacteristicNotificationsBroadcastToEverySubscriber() async throws {
    let fixture = try await makeConnectedTransport()
    let firstStream = fixture.transport.getCharacteristicStream(
      serviceUUID: fixture.service.uuid,
      characteristicUUID: fixture.characteristic.uuid
    )
    let secondStream = fixture.transport.getCharacteristicStream(
      serviceUUID: fixture.service.uuid,
      characteristicUUID: fixture.characteristic.uuid
    )
    let firstReceived = Task { try await firstValue(from: firstStream) }
    let secondReceived = Task { try await firstValue(from: secondStream) }

    fixture.characteristic.value = Data([1, 2, 3])
    await fixture.transport.didUpdateValue(
      for: fixture.characteristic,
      error: nil
    )

    let firstResult = try await firstReceived.value
    let secondResult = try await secondReceived.value
    XCTAssertEqual(firstResult, Data([1, 2, 3]))
    XCTAssertEqual(secondResult, Data([1, 2, 3]))
    await fixture.transport.dispose()
  }

  func testCancelledCharacteristicSubscriberCanResubscribeInSession() async throws {
    let fixture = try await makeConnectedTransport()
    let initialStream = fixture.transport.getCharacteristicStream(
      serviceUUID: fixture.service.uuid,
      characteristicUUID: fixture.characteristic.uuid
    )
    let initialConsumer = Task {
      for try await _ in initialStream {}
    }
    await Task.yield()
    initialConsumer.cancel()
    _ = try? await initialConsumer.value

    let replacementStream = fixture.transport.getCharacteristicStream(
      serviceUUID: fixture.service.uuid,
      characteristicUUID: fixture.characteristic.uuid
    )
    let replacementValue = Task {
      try await firstValue(from: replacementStream)
    }
    fixture.characteristic.value = Data([9])
    await fixture.transport.didUpdateValue(
      for: fixture.characteristic,
      error: nil
    )

    let replacementResult = try await replacementValue.value
    XCTAssertEqual(replacementResult, Data([9]))
    await fixture.transport.dispose()
  }

  func testBeeCancellationDuringPendingPhysicalWriteRecoversByDisconnecting() async throws {
    let fixture = try await makeConnectedTransport(
      serviceUUID: DeviceUUIDs.Bee.service,
      characteristicUUID: CBUUID(
        string: "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e"
      )
    )
    let connection = BeeDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: fixture.transport
    )
    let stream = connection.getAudioStream()
    let consumer = Task {
      for try await _ in stream {}
    }
    await waitForBluetoothReliabilityCondition { fixture.physicalDriver.writeValueCallCount == 1 }

    consumer.cancel()
    _ = try? await consumer.value
    await waitForBluetoothReliabilityCondition { fixture.physicalDriver.disconnectCallCount == 1 }

    // The cancelled write poisoned the characteristic callback identity,
    // so a compensating write was not issued over the ambiguous channel.
    XCTAssertEqual(fixture.physicalDriver.writeValueCallCount, 1)
    XCTAssertEqual(fixture.transport.state, .disconnected)
    await fixture.transport.dispose()
    XCTAssertEqual(fixture.physicalDriver.disconnectCallCount, 1)
  }

  func testBeeResponseBeforeWriteAckDrainsPhysicalWriteBeforeQueueAdvances() async throws {
    let fixture = try await makeConnectedTransport(
      serviceUUID: DeviceUUIDs.Bee.service,
      characteristicUUID: CBUUID(
        string: "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e"
      )
    )
    let connection = BeeDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: fixture.transport
    )
    let stream = connection.getAudioStream()
    let consumer = Task {
      for try await _ in stream {}
    }
    await waitForBluetoothReliabilityCondition { fixture.physicalDriver.writeValueCallCount == 1 }

    connection.handleControlResponse([0x06, 0xC0, 0x01])
    for _ in 0..<10 { await Task.yield() }
    XCTAssertEqual(fixture.physicalDriver.writeValueCallCount, 1)

    await fixture.transport.didWriteValue(
      for: fixture.characteristic,
      error: nil
    )
    consumer.cancel()
    _ = try? await consumer.value
    await waitForBluetoothReliabilityCondition { fixture.physicalDriver.writeValueCallCount == 2 }

    connection.handleControlResponse([0x06, 0xC0, 0x00])
    for _ in 0..<10 { await Task.yield() }
    XCTAssertEqual(fixture.physicalDriver.writeValueCallCount, 2)
    await fixture.transport.didWriteValue(
      for: fixture.characteristic,
      error: nil
    )

    await connection.teardownDevice()
    XCTAssertEqual(fixture.physicalDriver.disconnectCallCount, 0)
    await fixture.transport.dispose()
  }

  private func makeConnectedTransport(
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock(),
    serviceUUID: CBUUID = CBUUID(string: "180F"),
    characteristicUUID: CBUUID = CBUUID(string: "2A19")
  ) async throws -> (
    transport: BleTransport,
    physicalDriver: FakeBLEPhysicalDriver,
    service: CBMutableService,
    characteristic: CBMutableCharacteristic
  ) {
    let centralEvents = PassthroughSubject<BluetoothCentralEvent, Never>()
    let physicalDriver = FakeBLEPhysicalDriver()
    let service = CBMutableService(type: serviceUUID, primary: true)
    let characteristic = CBMutableCharacteristic(
      type: characteristicUUID,
      properties: [.read, .notify],
      value: nil,
      permissions: [.readable]
    )
    service.characteristics = [characteristic]
    let transport = BleTransport(
      physicalDriver: physicalDriver,
      centralEvents: centralEvents.eraseToAnyPublisher(),
      sessionGeneration: 9,
      operationClock: operationClock
    )

    let connect = Task { try await transport.connect() }
    await waitForBluetoothReliabilityCondition { physicalDriver.issuedLeases.count == 1 }
    centralEvents.send(.connected(lease: physicalDriver.issuedLeases[0]))
    await waitForBluetoothReliabilityCondition { physicalDriver.discoverServicesCallCount == 1 }
    await transport.didDiscoverServices([service], error: nil)
    await waitForBluetoothReliabilityCondition { physicalDriver.discoverCharacteristicsCallCount == 1 }
    await transport.didDiscoverCharacteristics(for: service, error: nil)
    try await connect.value
    return (transport, physicalDriver, service, characteristic)
  }

  private func firstValue(
    from stream: AsyncThrowingStream<Data, Error>
  ) async throws -> Data? {
    for try await value in stream {
      return value
    }
    return nil
  }
}

@MainActor
final class BluetoothConnectionLeaseRegistryTests: XCTestCase {
  func testCancelledLeaseFencesPeripheralUntilTerminalCallback() throws {
    let registry = BluetoothConnectionLeaseRegistry()
    let peripheralID = UUID()
    let leaseA = try registry.begin(
      peripheralID: peripheralID,
      sessionGeneration: 1
    )

    XCTAssertTrue(registry.requestCancellation(leaseA))
    XCTAssertThrowsError(
      try registry.begin(peripheralID: peripheralID, sessionGeneration: 2)
    ) { error in
      XCTAssertEqual(
        error as? BluetoothConnectionLeaseError,
        .leaseAlreadyActive(leaseA)
      )
    }

    let lateConnect = registry.markConnected(peripheralID: peripheralID)
    XCTAssertEqual(lateConnect?.lease, leaseA)
    XCTAssertEqual(lateConnect?.shouldCancel, true)
    XCTAssertEqual(registry.activeLease(for: peripheralID), leaseA)

    XCTAssertEqual(registry.finish(peripheralID: peripheralID), leaseA)
    let leaseB = try registry.begin(
      peripheralID: peripheralID,
      sessionGeneration: 2
    )
    XCTAssertNotEqual(leaseB.token, leaseA.token)
  }

  func testCentralResetReleasesEveryFencedLease() throws {
    let registry = BluetoothConnectionLeaseRegistry()
    let firstID = UUID()
    let secondID = UUID()
    let first = try registry.begin(peripheralID: firstID, sessionGeneration: 1)
    let second = try registry.begin(peripheralID: secondID, sessionGeneration: 2)
    XCTAssertTrue(registry.requestCancellation(first))

    XCTAssertEqual(Set(registry.reset()), Set([first, second]))
    XCTAssertNil(registry.activeLease(for: firstID))
    XCTAssertNoThrow(
      try registry.begin(peripheralID: firstID, sessionGeneration: 3)
    )
  }
}
