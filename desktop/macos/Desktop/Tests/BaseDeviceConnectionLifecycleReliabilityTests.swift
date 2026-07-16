import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class BaseDeviceConnectionLifecycleTests: XCTestCase {
  func testTemplateLifecyclePreparesAndTearsDownExactlyOnce() async throws {
    let transport = ReliabilityTestTransport(sessionGeneration: 11)
    let connection = LifecycleHookConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport
    )

    try await connection.connect()
    XCTAssertEqual(connection.prepareCallCount, 1)

    do {
      try await connection.connect()
      XCTFail("A connection object represents exactly one session generation")
    } catch let error as DeviceConnectionError {
      guard case .alreadyConnected = error else {
        return XCTFail("Unexpected error: \(error)")
      }
    }

    await connection.disconnect()
    await connection.disconnect()
    XCTAssertEqual(connection.teardownCallCount, 1)
    XCTAssertEqual(transport.disposeCallCount, 1)
  }

  func testFailedPreparationStillTearsDownExactlyOnce() async {
    let transport = ReliabilityTestTransport(sessionGeneration: 12)
    let connection = LifecycleHookConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport
    )
    connection.prepareError = BluetoothReliabilityTestError.expected

    do {
      try await connection.connect()
      XCTFail("Expected preparation failure")
    } catch {}

    XCTAssertEqual(connection.prepareCallCount, 1)
    XCTAssertEqual(connection.teardownCallCount, 1)
    XCTAssertEqual(transport.disposeCallCount, 1)
  }

  func testUnexpectedPhysicalDisconnectTearsDownAndDelegatesExactlyOnce() async throws {
    let transport = ReliabilityTestTransport(sessionGeneration: 13)
    let connection = LifecycleHookConnection(
      device: bluetoothReliabilityTestDevice,
      transport: transport
    )
    let delegate = ConnectionDelegateDouble()
    connection.delegate = delegate
    try await connection.connect()

    transport.emitDisconnected()
    await waitForBluetoothReliabilityCondition { delegate.unexpectedDisconnectCount == 1 }
    transport.emitDisconnected()
    await Task.yield()

    XCTAssertEqual(connection.teardownCallCount, 1)
    XCTAssertEqual(transport.disposeCallCount, 1)
    XCTAssertEqual(delegate.unexpectedDisconnectCount, 1)
  }
}
