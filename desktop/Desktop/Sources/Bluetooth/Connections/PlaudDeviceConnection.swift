import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for PLAUD NotePin devices
/// Ported from: omi/app/lib/services/devices/plaud_connection.dart
final class PlaudDeviceConnection: BaseDeviceConnection {

    // MARK: - Constants

    private enum Command {
        static let getBattery = 9
        static let startRecord = 20
        static let stopRecord = 23
        static let syncFileStart = 28
        static let stopSync = 30
    }

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "PlaudDeviceConnection")

    private var commandQueues: [Int: PassthroughSubject<[UInt8], Never>] = [:]
    private var audioStreamSubject = PassthroughSubject<Data, Error>()
    private var notificationSubscription: Task<Void, Never>?
    private var sessionId: Int?
    private var cancellables = Set<AnyCancellable>()

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()

        // Wait for connection to stabilize
        try? await Task.sleep(nanoseconds: 2_000_000_000)

        // Subscribe to notifications
        startNotificationListener()
    }

    override func disconnect() async {
        // Stop recording if active
        if let sessionId = sessionId {
            do {
                try await stopSync()
                try await stopRecord(sessionId: sessionId)
            } catch {
                logger.debug("Error stopping recording during disconnect: \(error.localizedDescription)")
            }
        }

        notificationSubscription?.cancel()
        notificationSubscription = nil
        commandQueues.removeAll()
        sessionId = nil

        await super.disconnect()
    }

    // MARK: - Notification Handling

    private func startNotificationListener() {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.PLAUD.service,
            characteristicUUID: DeviceUUIDs.PLAUD.notifyCharacteristic
        )

        notificationSubscription = Task {
            do {
                for try await data in stream {
                    handleNotification(Array(data))
                }
            } catch {
                logger.debug("Notification stream ended: \(error.localizedDescription)")
            }
        }
    }

    private func handleNotification(_ data: [UInt8]) {
        guard !data.isEmpty else { return }

        if data[0] == 2 {
            // Audio data packet
            if let chunk = parseAudioChunk(Array(data.dropFirst())) {
                audioStreamSubject.send(Data(chunk))
            }
        } else if data.count >= 3 {
            // Command response
            let cmdId = Int(data[1]) | (Int(data[2]) << 8)
            let payload = data.count > 3 ? Array(data.dropFirst(3)) : []

            if commandQueues[cmdId] == nil {
                commandQueues[cmdId] = PassthroughSubject<[UInt8], Never>()
            }
            commandQueues[cmdId]?.send(payload)
        }
    }

    private func parseAudioChunk(_ payload: [UInt8]) -> [UInt8]? {
        guard payload.count >= 9 else { return nil }

        let position = toInt32(Array(payload[4..<8]))
        if position == 0xFFFFFFFF { return nil } // End marker

        let length = Int(payload[8])
        guard payload.count >= 9 + length else { return nil }

        return Array(payload[9..<(9 + length)])
    }

    // MARK: - Command Sending

    private func sendCommand(cmdId: Int, payload: [UInt8]) async throws -> [UInt8]? {
        if commandQueues[cmdId] == nil {
            commandQueues[cmdId] = PassthroughSubject<[UInt8], Never>()
        }

        let command: [UInt8] = [1, UInt8(cmdId & 0xFF), UInt8((cmdId >> 8) & 0xFF)] + payload

        try await transport.writeCharacteristic(
            data: Data(command),
            serviceUUID: DeviceUUIDs.PLAUD.service,
            characteristicUUID: DeviceUUIDs.PLAUD.writeCharacteristic,
            withResponse: true
        )

        // Wait for response with timeout
        return await withCheckedContinuation { continuation in
            var cancellable: AnyCancellable?
            let timeoutTask = Task {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10 seconds
                cancellable?.cancel()
                continuation.resume(returning: nil)
            }

            cancellable = commandQueues[cmdId]?
                .first()
                .sink { response in
                    timeoutTask.cancel()
                    continuation.resume(returning: response)
                }
        }
    }

    // MARK: - Recording Control

    private func startRecord() async throws -> (sessionId: Int, startTime: Int)? {
        let payload = toBytes32(1) + toBytes32(0) + toBytes32(0)
        guard let response = try await sendCommand(cmdId: Command.startRecord, payload: payload),
              response.count >= 10 else {
            return nil
        }

        return (
            sessionId: toInt32(Array(response[0..<4])),
            startTime: toInt32(Array(response[4..<8]))
        )
    }

    private func stopRecord(sessionId: Int) async throws {
        let payload = toBytes32(sessionId) + toBytes32(0)
        _ = try await sendCommand(cmdId: Command.stopRecord, payload: payload)
    }

    private func startSync(sessionId: Int, start: Int) async throws -> Bool {
        let payload = toBytes64(sessionId) + toBytes64(start) + toBytes64(0x7FFFFFFF)
        let response = try await sendCommand(cmdId: Command.syncFileStart, payload: payload)
        return response != nil
    }

    private func stopSync() async throws {
        let command: [UInt8] = [1, UInt8(Command.stopSync & 0xFF), UInt8((Command.stopSync >> 8) & 0xFF), 1]
        try await transport.writeCharacteristic(
            data: Data(command),
            serviceUUID: DeviceUUIDs.PLAUD.service,
            characteristicUUID: DeviceUUIDs.PLAUD.writeCharacteristic,
            withResponse: true
        )
    }

    private func setupRecordingSession() async -> Bool {
        let maxRetries = 3

        for attempt in 0..<maxRetries {
            do {
                if attempt > 0 {
                    logger.debug("Retry attempt \(attempt)/\(maxRetries)")
                    try await Task.sleep(nanoseconds: UInt64(attempt) * 1_000_000_000)
                }

                try await stopRecord(sessionId: 0)
                try await Task.sleep(nanoseconds: 500_000_000)

                guard let recordInfo = try await startRecord() else { continue }

                sessionId = recordInfo.sessionId

                try await Task.sleep(nanoseconds: 1_000_000_000)

                if try await startSync(sessionId: recordInfo.sessionId, start: recordInfo.startTime) {
                    logger.debug("Recording session setup successful")
                    return true
                }
            } catch {
                logger.debug("Setup error (attempt \(attempt + 1)): \(error.localizedDescription)")
            }
        }

        return false
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            guard let response = try await sendCommand(cmdId: Command.getBattery, payload: []),
                  response.count >= 2 else {
                return -1
            }

            // Response format: [is_charging, battery_level]
            let batteryLevel = Int(response[1])
            let isCharging = response[0] != 0
            logger.debug("Battery: \(batteryLevel)% \(isCharging ? "(Charging)" : "")")
            return batteryLevel
        } catch {
            logger.debug("Error retrieving battery level: \(error.localizedDescription)")
            return -1
        }
    }

    /// Get battery state including charging status
    func getBatteryState() async -> (level: Int, isCharging: Bool)? {
        guard await isConnected() else { return nil }

        do {
            guard let response = try await sendCommand(cmdId: Command.getBattery, payload: []),
                  response.count >= 2 else {
                return nil
            }

            return (level: Int(response[1]), isCharging: response[0] != 0)
        } catch {
            logger.debug("Error getting battery state: \(error.localizedDescription)")
            return nil
        }
    }

    override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        // PLAUD uses command-based battery retrieval, poll every 60 seconds
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                // Get initial battery level
                let initialLevel = await self.getBatteryLevel()
                if initialLevel >= 0 {
                    continuation.yield(initialLevel)
                }

                // Poll every 60 seconds
                var lastLevel = initialLevel
                while await self.isConnected() {
                    try? await Task.sleep(nanoseconds: 60_000_000_000)

                    let level = await self.getBatteryLevel()
                    if level >= 0 && level != lastLevel {
                        lastLevel = level
                        continuation.yield(level)
                    }
                }

                continuation.finish()
            }
        }
    }

    // MARK: - Audio

    override func getAudioCodec() async -> BleAudioCodec {
        .opusFS320
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                // Setup recording session
                guard await self.setupRecordingSession() else {
                    self.logger.debug("Failed to setup recording session")
                    continuation.finish()
                    return
                }

                // Buffer for 80-byte chunking
                var buffer = [UInt8]()
                let chunkSize = 80

                let cancellable = self.audioStreamSubject
                    .sink(
                        receiveCompletion: { _ in
                            // Flush remaining buffer
                            if !buffer.isEmpty {
                                continuation.yield(Data(buffer))
                            }
                            continuation.finish()
                        },
                        receiveValue: { data in
                            buffer.append(contentsOf: data)
                            while buffer.count >= chunkSize {
                                let chunk = Array(buffer.prefix(chunkSize))
                                continuation.yield(Data(chunk))
                                buffer.removeFirst(chunkSize)
                            }
                        }
                    )

                continuation.onTermination = { @Sendable _ in
                    cancellable.cancel()
                }
            }
        }
    }

    // MARK: - Unsupported Features

    override func getButtonState() async -> [UInt8] { [] }
    override func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        AsyncThrowingStream { $0.finish() }
    }

    override func hasPhotoStreaming() async -> Bool { false }
    override func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        AsyncThrowingStream { $0.finish() }
    }

    override func getFeatures() async -> OmiFeatures { [] }

    // MARK: - Byte Conversion Helpers

    private func toBytes32(_ value: Int) -> [UInt8] {
        [
            UInt8(value & 0xFF),
            UInt8((value >> 8) & 0xFF),
            UInt8((value >> 16) & 0xFF),
            UInt8((value >> 24) & 0xFF)
        ]
    }

    private func toBytes64(_ value: Int) -> [UInt8] {
        [
            UInt8(value & 0xFF),
            UInt8((value >> 8) & 0xFF),
            UInt8((value >> 16) & 0xFF),
            UInt8((value >> 24) & 0xFF),
            UInt8((value >> 32) & 0xFF),
            UInt8((value >> 40) & 0xFF),
            UInt8((value >> 48) & 0xFF),
            UInt8((value >> 56) & 0xFF)
        ]
    }

    private func toInt32(_ bytes: [UInt8]) -> Int {
        guard bytes.count >= 4 else { return 0 }
        return Int(bytes[0]) |
               (Int(bytes[1]) << 8) |
               (Int(bytes[2]) << 16) |
               (Int(bytes[3]) << 24)
    }
}
