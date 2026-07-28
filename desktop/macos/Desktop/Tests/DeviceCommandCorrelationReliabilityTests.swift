import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class UncorrelatedDeviceCommandTests: XCTestCase {
  func testPlaudTimeoutPoisonsCommandKeyAndLateResponseCannotAliasRetry() async throws {
    let clock = ManualDeviceOperationClock()
    let transport = ReliabilityTestTransport(sessionGeneration: 7)
    transport.state = .connected
    let connection = PlaudDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport,
      operationClock: clock
    )

    let first = Task {
      try await connection.sendCommand(cmdId: 9, payload: [])
    }
    await waitForBluetoothReliabilityCondition {
      let sleeperCount = await clock.sleeperCount
      return transport.writeCallCount == 1 && sleeperCount == 1
    }
    await clock.advanceAll()
    let firstResult = try await first.value
    XCTAssertNil(firstResult)

    do {
      _ = try await connection.sendCommand(cmdId: 9, payload: [])
      XCTFail("An uncorrelated timed-out command must not be retried in-session")
    } catch let error as DeviceConnectionError {
      guard case .operationFailed = error else {
        return XCTFail("Unexpected connection error: \(error)")
      }
    }

    // This is the response to the timed-out command. There is deliberately
    // no replacement handle for it to complete.
    connection.handleNotification([0, 9, 0, 0x52])
    await Task.yield()
    XCTAssertEqual(transport.writeCallCount, 1)
  }

  func testPlaudSerializesDifferentCommandIDsOnSharedWriteCharacteristic() async throws {
    let transport = ReliabilityTestTransport(sessionGeneration: 8)
    transport.state = .connected
    let connection = PlaudDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport
    )

    let first = Task {
      try await connection.sendCommand(cmdId: 9, payload: [])
    }
    await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }

    let second = Task {
      try await connection.sendCommand(cmdId: 20, payload: [])
    }
    for _ in 0..<10 { await Task.yield() }
    XCTAssertEqual(transport.writeCallCount, 1)

    connection.handleNotification([0, 9, 0, 0x31])
    let firstResponse = try await first.value
    XCTAssertEqual(firstResponse, [0x31])
    await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }

    connection.handleNotification([0, 20, 0, 0x32])
    let secondResponse = try await second.value
    XCTAssertEqual(secondResponse, [0x32])
    XCTAssertEqual(transport.writeCallCount, 2)
  }

  func testPlaudTeardownClosesActiveAndQueuedCommandsBeforeReset() async {
    let transport = ReliabilityTestTransport(sessionGeneration: 17)
    transport.state = .connected
    let connection = PlaudDeviceConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport
    )

    let active = Task {
      try await connection.sendCommand(cmdId: 9, payload: [])
    }
    await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
    let queued = Task {
      try await connection.sendCommand(cmdId: 20, payload: [])
    }
    for _ in 0..<10 { await Task.yield() }

    await connection.teardownDevice()
    _ = try? await active.value
    _ = try? await queued.value
    XCTAssertEqual(transport.writeCallCount, 1)

    do {
      _ = try await connection.sendCommand(cmdId: 28, payload: [])
      XCTFail("A torn-down adapter must reject new commands")
    } catch let error as DeviceCommandQueueError {
      XCTAssertEqual(error, .closed)
    } catch {
      XCTFail("Unexpected error: \(error)")
    }
    XCTAssertEqual(transport.writeCallCount, 1)
  }
}
