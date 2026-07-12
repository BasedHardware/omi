import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class BaseDeviceConnectionTeardownCoalescingTests: XCTestCase {
    func testExplicitDisconnectAwaitsUnexpectedTeardownAndTransportDispose() async throws {
        let transport = SuspendedDisposeTransport()
        let connection = SuspendedTeardownConnection(
            device: teardownTestDevice,
            transport: transport
        )
        let delegate = TeardownConnectionDelegate()
        let completion = TeardownCompletionProbe()
        connection.delegate = delegate

        try await connection.connect()
        transport.emitUnexpectedDisconnect()
        await waitForTeardownCondition { connection.teardownCallCount == 1 }

        let explicitDisconnect = Task { @MainActor in
            completion.didEnterExplicitDisconnect = true
            await connection.disconnect()
            completion.didFinishExplicitDisconnect = true
        }
        await waitForTeardownCondition { completion.didEnterExplicitDisconnect }

        XCTAssertFalse(completion.didFinishExplicitDisconnect)
        XCTAssertEqual(transport.disposeCallCount, 0)
        XCTAssertEqual(delegate.unexpectedDisconnectCount, 0)

        connection.resumeTeardown()
        await waitForTeardownCondition { transport.disposeCallCount == 1 }

        XCTAssertFalse(completion.didFinishExplicitDisconnect)
        XCTAssertEqual(delegate.unexpectedDisconnectCount, 0)

        transport.resumeDispose()
        await explicitDisconnect.value

        XCTAssertTrue(completion.didFinishExplicitDisconnect)
        XCTAssertEqual(connection.teardownCallCount, 1)
        XCTAssertEqual(transport.disposeCallCount, 1)
        XCTAssertEqual(delegate.unexpectedDisconnectCount, 1)
    }
}

private var teardownTestDevice: BtDevice {
    BtDevice(
        id: "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        name: "Teardown Test Omi",
        type: .omi,
        rssi: -50
    )
}

@MainActor
private func waitForTeardownCondition(
    _ condition: @escaping @MainActor () -> Bool,
    file: StaticString = #filePath,
    line: UInt = #line
) async {
    for _ in 0..<500 {
        if condition() { return }
        await Task.yield()
    }
    XCTFail("Timed out waiting for teardown condition", file: file, line: line)
}

@MainActor
private final class SuspendedTeardownConnection: BaseDeviceConnection {
    private(set) var teardownCallCount = 0
    private var teardownContinuation: CheckedContinuation<Void, Never>?

    override func teardownDevice() async {
        teardownCallCount += 1
        await withCheckedContinuation { continuation in
            teardownContinuation = continuation
        }
    }

    func resumeTeardown() {
        let continuation = teardownContinuation
        teardownContinuation = nil
        continuation?.resume()
    }
}

@MainActor
private final class SuspendedDisposeTransport: DeviceTransport {
    let deviceId = teardownTestDevice.id
    let sessionGeneration: UInt64 = 101
    private(set) var state: DeviceTransportState = .disconnected
    private let stateSubject = PassthroughSubject<DeviceTransportState, Never>()
    var connectionStatePublisher: AnyPublisher<DeviceTransportState, Never> {
        stateSubject.eraseToAnyPublisher()
    }

    private(set) var disposeCallCount = 0
    private var disposeContinuation: CheckedContinuation<Void, Never>?

    func connect() async throws {
        state = .connected
        stateSubject.send(.connected)
    }

    func disconnect() async {
        state = .disconnected
        stateSubject.send(.disconnected)
    }

    func isConnected() async -> Bool {
        state == .connected
    }

    func ping() async -> Bool {
        true
    }

    func getCharacteristicStream(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func readCharacteristic(
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID
    ) async throws -> Data {
        Data()
    }

    func writeCharacteristic(
        data: Data,
        serviceUUID: CBUUID,
        characteristicUUID: CBUUID,
        withResponse: Bool
    ) async throws {}

    func dispose() async {
        disposeCallCount += 1
        await withCheckedContinuation { continuation in
            disposeContinuation = continuation
        }
        state = .disconnected
        stateSubject.send(.disconnected)
    }

    func emitUnexpectedDisconnect() {
        state = .disconnected
        stateSubject.send(.disconnected)
    }

    func resumeDispose() {
        let continuation = disposeContinuation
        disposeContinuation = nil
        continuation?.resume()
    }
}

@MainActor
private final class TeardownConnectionDelegate: DeviceConnectionDelegate {
    private(set) var unexpectedDisconnectCount = 0

    func deviceConnection(
        _ connection: DeviceConnection,
        didDisconnectUnexpectedly device: BtDevice
    ) {
        unexpectedDisconnectCount += 1
    }

    func deviceConnection(
        _ connection: DeviceConnection,
        didDetectFall data: AccelerometerData
    ) {}
}

@MainActor
private final class TeardownCompletionProbe {
    var didEnterExplicitDisconnect = false
    var didFinishExplicitDisconnect = false
}
