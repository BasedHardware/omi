import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Bee devices
/// Uses AAC audio codec with ADTS framing
/// Ported from: omi/app/lib/services/devices/bee_connection.dart
final class BeeDeviceConnection: BaseDeviceConnection {

    // MARK: - Constants

    private static let controlCharacteristicUUID = "05e1f93c-d8d0-5ed8-dd88-379e4c1a3e3e"
    private static let audioCharacteristicUUID = "b189a505-a86c-11ee-a5fb-8f2089a49e7e"

    private enum Command {
        static let mute: UInt16 = 0xC006
        static let unmute: UInt16 = 0xC006
        static let battery: UInt16 = 0xC00F
    }

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "BeeDeviceConnection")

    private var audioBuffer = [UInt8]()
    private var audioStreamSubject = PassthroughSubject<Data, Error>()
    private var controlSubscription: Task<Void, Never>?
    private var audioSubscription: Task<Void, Never>?
    private var responseCompleters: [UInt16: CheckedContinuation<[UInt8]?, Never>] = [:]
    private var isRecording = false

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        startControlListener()
        startAudioListener()
    }

    override func disconnect() async {
        if isRecording {
            _ = try? await sendCommand(cmdId: Command.mute, payload: [0x00])
        }

        controlSubscription?.cancel()
        audioSubscription?.cancel()
        controlSubscription = nil
        audioSubscription = nil

        await super.disconnect()
    }

    // MARK: - Listeners

    private func startControlListener() {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Bee.service,
            characteristicUUID: CBUUID(string: Self.controlCharacteristicUUID)
        )

        controlSubscription = Task { [weak self] in
            do {
                for try await data in stream {
                    self?.handleControlResponse(Array(data))
                }
            } catch {
                self?.logger.debug("Control stream ended")
            }
        }
    }

    private func startAudioListener() {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Bee.service,
            characteristicUUID: CBUUID(string: Self.audioCharacteristicUUID)
        )

        audioSubscription = Task { [weak self] in
            do {
                for try await data in stream {
                    if let frame = self?.processAudioPacket(Array(data)) {
                        self?.audioStreamSubject.send(Data(frame))
                    }
                }
            } catch {
                self?.logger.debug("Audio stream ended")
            }
        }
    }

    // MARK: - Response Handling

    private func handleControlResponse(_ data: [UInt8]) {
        guard data.count >= 2 else { return }

        let responseCode = UInt16(data[0]) | (UInt16(data[1]) << 8)
        let payload = data.count > 2 ? Array(data.dropFirst(2)) : []

        // Check for echo response (0x8000)
        if responseCode == 0x8000 && payload.count >= 2 {
            let echoedCmd = UInt16(payload[0]) | (UInt16(payload[1]) << 8)
            let actualPayload = payload.count > 2 ? Array(payload.dropFirst(2)) : []

            if let continuation = responseCompleters.removeValue(forKey: echoedCmd) {
                continuation.resume(returning: actualPayload)
            }
        } else if let continuation = responseCompleters.removeValue(forKey: responseCode) {
            continuation.resume(returning: payload)
        }
    }

    // MARK: - Audio Processing

    /// Process AAC audio packet with ADTS framing
    private func processAudioPacket(_ data: [UInt8]) -> [UInt8]? {
        guard data.count >= 2 else { return nil }

        audioBuffer.append(contentsOf: data.dropFirst(2))

        while audioBuffer.count >= 7 {
            // Look for ADTS sync word (0xFF 0xFx)
            guard audioBuffer[0] == 0xFF, (audioBuffer[1] & 0xF0) == 0xF0 else {
                audioBuffer.removeFirst()
                continue
            }

            // Extract frame length from ADTS header
            let frameLength = (Int(audioBuffer[3] & 0x03) << 11) |
                              (Int(audioBuffer[4]) << 3) |
                              (Int(audioBuffer[5] & 0xE0) >> 5)

            if audioBuffer.count >= frameLength {
                let frame = Array(audioBuffer.prefix(frameLength))
                audioBuffer.removeFirst(frameLength)
                return frame
            }
            break
        }
        return nil
    }

    // MARK: - Command Sending

    private func sendCommand(cmdId: UInt16, payload: [UInt8]) async throws -> [UInt8]? {
        let command: [UInt8] = [UInt8(cmdId & 0xFF), UInt8((cmdId >> 8) & 0xFF)] + payload

        try await transport.writeCharacteristic(
            data: Data(command),
            serviceUUID: DeviceUUIDs.Bee.service,
            characteristicUUID: CBUUID(string: Self.controlCharacteristicUUID),
            withResponse: true
        )

        return await withCheckedContinuation { continuation in
            responseCompleters[cmdId] = continuation

            Task {
                try? await Task.sleep(nanoseconds: 5_000_000_000) // 5 second timeout
                if let cont = responseCompleters.removeValue(forKey: cmdId) {
                    cont.resume(returning: nil)
                }
            }
        }
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            guard let response = try await sendCommand(cmdId: Command.battery, payload: []),
                  response.count >= 2 else {
                return -1
            }
            return Int(response[0])
        } catch {
            logger.debug("Error retrieving battery: \(error.localizedDescription)")
            return -1
        }
    }

    /// Get battery state including charging status
    func getBatteryState() async -> (level: Int, isCharging: Bool)? {
        guard await isConnected() else { return nil }

        do {
            guard let response = try await sendCommand(cmdId: Command.battery, payload: []),
                  response.count >= 2 else {
                return nil
            }
            return (level: Int(response[0]), isCharging: response[1] != 0)
        } catch {
            return nil
        }
    }

    override func getBatteryLevelStream() -> AsyncThrowingStream<Int, Error> {
        // Bee uses command-based battery retrieval, poll every 60 seconds
        return AsyncThrowingStream { [weak self] continuation in
            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                var lastLevel: Int?

                // Get initial battery level
                let initialLevel = await self.getBatteryLevel()
                if initialLevel >= 0 {
                    lastLevel = initialLevel
                    continuation.yield(initialLevel)
                }

                // Poll every 60 seconds
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
        .aac
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            guard let self = self else {
                continuation.finish()
                return
            }

            Task { [weak self] in
                guard let self = self else {
                    continuation.finish()
                    return
                }

                // Send unmute command to start audio
                _ = try? await self.sendCommand(cmdId: Command.unmute, payload: [0x01])
                self.isRecording = true

                let cancellable = self.audioStreamSubject
                    .sink(
                        receiveCompletion: { _ in continuation.finish() },
                        receiveValue: { data in continuation.yield(data) }
                    )

                continuation.onTermination = { @Sendable _ in
                    cancellable.cancel()
                    Task { @MainActor in
                        self.isRecording = false
                        _ = try? await self.sendCommand(cmdId: Command.mute, payload: [0x00])
                    }
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

    // MARK: - Device Info

    override func updateDeviceInfo() async {
        device.modelNumber = "Bee"
        device.firmwareRevision = "1.0.0"
        device.hardwareRevision = "1.0.0"
        device.manufacturerName = "Bee"
    }
}
