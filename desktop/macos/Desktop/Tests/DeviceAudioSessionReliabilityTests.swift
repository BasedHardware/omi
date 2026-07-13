import Combine
import CoreBluetooth
import XCTest

@testable import Omi_Computer

@MainActor
final class DeviceAudioStreamLifecycleTests: XCTestCase {
    func testFriendAudioStreamFinishesWhenSessionTearsDown() async throws {
        let clock = ManualDeviceOperationClock()
        let transport = ReliabilityTestTransport(sessionGeneration: 14)
        let connection = FriendPendantConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport,
            operationClock: clock
        )
        let connectTask = Task { try await connection.connect() }
        await waitForBluetoothReliabilityCondition { await clock.sleeperCount == 1 }
        await clock.advanceAll()
        try await connectTask.value

        let stream = connection.getAudioStream()
        let consumer = Task {
            for try await _ in stream {}
        }
        await connection.disconnect()
        try await consumer.value
    }

    func testLimitlessButtonStreamFinishesWhenSessionTearsDown() async throws {
        let transport = ReliabilityTestTransport(sessionGeneration: 19)
        let connection = LimitlessDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport
        )
        let stream = connection.getButtonStream()
        let consumer = Task {
            for try await _ in stream {}
        }

        await connection.teardownDevice()
        try await consumer.value
    }
}

@MainActor
final class DeviceAudioSetupCancellationTests: XCTestCase {
    func testBeeCancellationDuringUnmuteWritesCompensatingMute() async {
        let clock = ManualDeviceOperationClock()
        let transport = ReliabilityTestTransport(sessionGeneration: 15)
        transport.state = .connected
        let connection = BeeDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport,
            operationClock: clock
        )

        let stream = connection.getAudioStream()
        let consumer = Task {
            for try await _ in stream {}
        }
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
        consumer.cancel()
        _ = try? await consumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }
        await waitForBluetoothReliabilityCondition { transport.disconnectCallCount == 1 }

        XCTAssertEqual(transport.writtenData[0], Data([0x06, 0xC0, 0x01]))
        XCTAssertEqual(transport.writtenData[1], Data([0x06, 0xC0, 0x00]))
        XCTAssertEqual(transport.disconnectCallCount, 1)

        let replacement = connection.getAudioStream()
        do {
            _ = try await firstValue(from: replacement)
            XCTFail("A poisoned Bee command channel must require reconnect")
        } catch {}
        XCTAssertEqual(transport.writeCallCount, 2)
        await clock.advanceAll()
    }

    func testPlaudCancellationDuringSetupStopsPartialSession() async {
        let clock = ManualDeviceOperationClock()
        let transport = ReliabilityTestTransport(sessionGeneration: 16)
        transport.state = .connected
        let connection = PlaudDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport,
            operationClock: clock
        )

        let stream = connection.getAudioStream()
        let consumer = Task {
            for try await _ in stream {}
        }
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
        consumer.cancel()
        _ = try? await consumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }

        XCTAssertEqual(transport.writtenData[1], Data([1, 30, 0, 1]))
        connection.handleNotification([0, 23, 0])
        for _ in 0..<10 { await Task.yield() }
        await waitForBluetoothReliabilityCondition { transport.disconnectCallCount == 1 }
        XCTAssertEqual(transport.writeCallCount, 2)
        XCTAssertEqual(transport.disconnectCallCount, 1)
        await clock.advanceAll()
    }

    func testBeeNormalStopDrainsMuteBeforeWaitingSubscriberRestarts() async {
        let transport = ReliabilityTestTransport(sessionGeneration: 18)
        transport.state = .connected
        let connection = BeeDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport
        )

        let firstStream = connection.getAudioStream()
        let firstConsumer = Task {
            for try await _ in firstStream {}
        }
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
        connection.handleControlResponse([0x06, 0xC0, 0x01])
        for _ in 0..<10 { await Task.yield() }

        firstConsumer.cancel()
        _ = try? await firstConsumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }

        let replacementStream = connection.getAudioStream()
        let replacementConsumer = Task {
            for try await _ in replacementStream {}
        }
        for _ in 0..<10 { await Task.yield() }
        XCTAssertEqual(transport.writeCallCount, 2)

        connection.handleControlResponse([0x06, 0xC0, 0x00])
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 3 }
        connection.handleControlResponse([0x06, 0xC0, 0x01])

        replacementConsumer.cancel()
        _ = try? await replacementConsumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 4 }
        connection.handleControlResponse([0x06, 0xC0, 0x00])
        await connection.teardownDevice()
        XCTAssertEqual(transport.disconnectCallCount, 0)
    }

    func testPlaudStopRecordTimeoutDisconnectsAndFencesRestart() async {
        let clock = ManualDeviceOperationClock()
        let transport = ReliabilityTestTransport(sessionGeneration: 20)
        transport.state = .connected
        let connection = PlaudDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport,
            operationClock: clock
        )
        let stream = connection.getAudioStream()
        let consumer = Task {
            for try await _ in stream {}
        }

        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
        connection.handleNotification([0, 23, 0, 1])
        await waitForBluetoothReliabilityCondition { await clock.sleeperCount >= 2 }
        await clock.advanceAll()

        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }
        connection.handleNotification([
            0, 20, 0,
            1, 0, 0, 0,
            2, 0, 0, 0,
            0, 0,
        ])
        await waitForBluetoothReliabilityCondition { await clock.sleeperCount >= 2 }
        await clock.advanceAll()

        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 3 }
        connection.handleNotification([0, 28, 0, 1])
        for _ in 0..<10 { await Task.yield() }
        await clock.advanceAll()

        consumer.cancel()
        _ = try? await consumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 5 }
        await waitForBluetoothReliabilityCondition { await clock.sleeperCount >= 1 }
        await clock.advanceAll()
        await waitForBluetoothReliabilityCondition { transport.disconnectCallCount == 1 }

        let replacement = connection.getAudioStream()
        do {
            _ = try await firstValue(from: replacement)
            XCTFail("Unacknowledged STOP_RECORD must fence PLAUD audio")
        } catch {}
        XCTAssertEqual(transport.writeCallCount, 5)
    }

    func testBeeRestartClearsPartialAudioFrameFromPreviousSession() async {
        let transport = ReliabilityTestTransport(sessionGeneration: 21)
        transport.state = .connected
        let connection = BeeDeviceConnection(
            device: bluetoothReliabilityTestDevice,
            transport: transport
        )
        let initialStream = connection.getAudioStream()
        let initialConsumer = Task {
            for try await _ in initialStream {}
        }
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 1 }
        connection.handleControlResponse([0x06, 0xC0, 0x01])

        XCTAssertNil(connection.processAudioPacket([0, 0, 0xFF, 0xF1, 0x50]))
        initialConsumer.cancel()
        _ = try? await initialConsumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 2 }
        connection.handleControlResponse([0x06, 0xC0, 0x00])

        let replacementStream = connection.getAudioStream()
        let replacementConsumer = Task {
            for try await _ in replacementStream {}
        }
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 3 }
        let cleanFrame: [UInt8] = [0xFF, 0xF1, 0x50, 0x80, 0, 0xE0, 0xFC]
        XCTAssertEqual(
            connection.processAudioPacket([0, 0] + cleanFrame),
            cleanFrame
        )
        connection.handleControlResponse([0x06, 0xC0, 0x01])

        replacementConsumer.cancel()
        _ = try? await replacementConsumer.value
        await waitForBluetoothReliabilityCondition { transport.writeCallCount == 4 }
        connection.handleControlResponse([0x06, 0xC0, 0x00])
        await connection.teardownDevice()
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
final class DeviceAudioStreamControllerTests: XCTestCase {
    func testFailedStopFencesWaitingSubscriberInsteadOfRestarting() async {
        let harness = AudioControllerHarness()
        let controller = DeviceAudioStreamController(
            start: { try await harness.start() },
            stop: { try await harness.stop() }
        )
        let initialStream = controller.makeStream()
        let initialConsumer = Task {
            for try await _ in initialStream {}
        }
        await waitForBluetoothReliabilityCondition { harness.startCallCount == 1 }

        initialConsumer.cancel()
        _ = try? await initialConsumer.value
        await waitForBluetoothReliabilityCondition { harness.stopCallCount == 1 }

        let waitingStream = controller.makeStream()
        let waitingConsumer = Task {
            for try await _ in waitingStream {}
        }
        harness.failStop(BluetoothReliabilityTestError.expected)

        do {
            try await waitingConsumer.value
            XCTFail("A failed stop must fence the controller")
        } catch {}
        XCTAssertEqual(harness.startCallCount, 1)
    }

    func testFramesBeforeSetupCompletesAreDropped() async throws {
        let harness = AudioControllerHarness()
        harness.suspendStart = true
        let controller = DeviceAudioStreamController(
            start: { try await harness.start() },
            stop: { try await harness.stop() }
        )
        let stream = controller.makeStream()
        var received: [Data] = []
        let consumer = Task {
            for try await value in stream {
                received.append(value)
            }
        }
        await waitForBluetoothReliabilityCondition { harness.startCallCount == 1 }

        controller.yield(Data([1]))
        harness.resumeStart()
        await waitForBluetoothReliabilityCondition { harness.startCompletionCount == 1 }
        controller.yield(Data([2]))

        await waitForBluetoothReliabilityCondition { received == [Data([2])] }
        consumer.cancel()
        _ = try? await consumer.value
        await waitForBluetoothReliabilityCondition { harness.stopCallCount == 1 }
        harness.succeedStop()
    }

    func testWaitingReplacementDropsOldFramesUntilStopAndRestartComplete() async throws {
        let harness = AudioControllerHarness()
        let controller = DeviceAudioStreamController(
            start: { try await harness.start() },
            stop: { try await harness.stop() }
        )
        let initialStream = controller.makeStream()
        let initialConsumer = Task {
            for try await _ in initialStream {}
        }
        await waitForBluetoothReliabilityCondition { harness.startCompletionCount == 1 }
        initialConsumer.cancel()
        _ = try? await initialConsumer.value
        await waitForBluetoothReliabilityCondition { harness.stopCallCount == 1 }

        let replacementStream = controller.makeStream()
        var replacementValues: [Data] = []
        let replacementConsumer = Task {
            for try await value in replacementStream {
                replacementValues.append(value)
            }
        }
        controller.yield(Data([3]))
        harness.succeedStop()
        await waitForBluetoothReliabilityCondition { harness.startCompletionCount == 2 }
        controller.yield(Data([4]))

        await waitForBluetoothReliabilityCondition { replacementValues == [Data([4])] }
        replacementConsumer.cancel()
        _ = try? await replacementConsumer.value
        await waitForBluetoothReliabilityCondition { harness.stopCallCount == 2 }
        harness.succeedStop()
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
