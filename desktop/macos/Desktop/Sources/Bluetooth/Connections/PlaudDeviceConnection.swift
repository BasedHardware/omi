@preconcurrency import CoreBluetooth
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

  private let commandOperations: DeviceOperationBroker<Int, Data>
  private let commandGate = UncorrelatedOperationGate<Int>()
  private let commandQueue = DeviceCommandQueue()
  private var notificationSubscription: Task<Void, Never>?
  private var sessionId: Int?
  private var recordingSetupAttempted = false
  private lazy var audioStreamController = DeviceAudioStreamController(
    start: { [weak self] in
      guard let self else { throw DeviceTransportError.disposed }
      try await self.setupRecordingSession()
    },
    stop: { [weak self] in
      guard let self else { return }
      try await self.stopRecordingSession()
    }
  )

  // MARK: - Initialization

  override init(
    device: BtDevice,
    transport: DeviceTransport,
    operationClock: any DeviceOperationClock = ContinuousDeviceOperationClock()
  ) {
    self.commandOperations = DeviceOperationBroker(clock: operationClock)
    super.init(
      device: device,
      transport: transport,
      operationClock: operationClock
    )
  }

  // MARK: - Connection

  override func prepareDeviceAfterConnect() async throws {
    try await operationClock.sleep(for: .seconds(2))

    startNotificationListener()
  }

  override func teardownDevice() async {
    await audioStreamController.finish()
    await commandQueue.close()

    notificationSubscription?.cancel()
    notificationSubscription = nil
    await commandOperations.cancelAll(reason: .disconnected)
    commandGate.reset()
    sessionId = nil
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

  /// Parses one physical notification. Kept internal so adapter-correlation
  /// behavior can be verified without a real CoreBluetooth peripheral.
  func handleNotification(_ data: [UInt8]) {
    guard !data.isEmpty else { return }

    if data[0] == 2 {
      // Audio data packet
      if let chunk = parseAudioChunk(Array(data.dropFirst())) {
        audioStreamController.yield(Data(chunk))
      }
    } else if data.count >= 3 {
      // Command response
      let cmdId = Int(data[1]) | (Int(data[2]) << 8)
      let payload = data.count > 3 ? Array(data.dropFirst(3)) : []

      completeCommand(commandID: cmdId, payload: payload)
    }
  }

  private func completeCommand(commandID: Int, payload: [UInt8]) {
    guard let handle = commandGate.takeHandleForCallback(key: commandID) else { return }
    Task {
      await commandOperations.succeed(
        handle: handle,
        value: Data(payload)
      )
    }
  }

  private func parseAudioChunk(_ payload: [UInt8]) -> [UInt8]? {
    guard payload.count >= 9 else { return nil }

    let position = toInt32(Array(payload[4..<8]))
    if position == 0xFFFF_FFFF { return nil }  // End marker

    let length = Int(payload[8])
    guard payload.count >= 9 + length else { return nil }

    return Array(payload[9..<(9 + length)])
  }

  // MARK: - Command Sending

  func sendCommand(cmdId: Int, payload: [UInt8]) async throws -> [UInt8]? {
    try await commandQueue.run { [weak self] in
      guard let self else { throw DeviceTransportError.disposed }
      return try await self.sendCommandSerially(cmdId: cmdId, payload: payload)
    }
  }

  private func sendCommandSerially(cmdId: Int, payload: [UInt8]) async throws -> [UInt8]? {
    guard commandGate.canStart(cmdId) else {
      throw DeviceConnectionError.operationFailed(
        "A previous command response is ambiguous; reconnect the device"
      )
    }
    let command: [UInt8] = [1, UInt8(cmdId & 0xFF), UInt8((cmdId >> 8) & 0xFF)] + payload

    do {
      let response = try await commandOperations.perform(
        key: cmdId,
        timeout: .seconds(10),
        onTerminal: { [weak self] handle, termination in
          self?.commandGate.terminal(handle: handle, termination: termination)
        }
      ) { [weak self] handle in
        guard let self else { throw DeviceTransportError.disposed }
        guard self.commandGate.register(handle) else {
          throw DeviceConnectionError.operationFailed(
            "Command callback identity is no longer trustworthy"
          )
        }
        try await self.transport.writeCharacteristic(
          data: Data(command),
          serviceUUID: DeviceUUIDs.PLAUD.service,
          characteristicUUID: DeviceUUIDs.PLAUD.writeCharacteristic,
          withResponse: true
        )
      }
      return Array(response)
    } catch DeviceOperationBrokerError.timedOut {
      return nil
    }
  }

  // MARK: - Recording Control

  private func startRecord() async throws -> (sessionId: Int, startTime: Int)? {
    let payload = toBytes32(1) + toBytes32(0) + toBytes32(0)
    guard let response = try await sendCommand(cmdId: Command.startRecord, payload: payload),
      response.count >= 10
    else {
      return nil
    }

    return (
      sessionId: toInt32(Array(response[0..<4])),
      startTime: toInt32(Array(response[4..<8]))
    )
  }

  private func stopRecord(sessionId: Int) async throws {
    let payload = toBytes32(sessionId) + toBytes32(0)
    guard try await sendCommand(cmdId: Command.stopRecord, payload: payload) != nil else {
      throw DeviceConnectionError.operationFailed(
        "PLAUD did not acknowledge STOP_RECORD"
      )
    }
  }

  private func startSync(sessionId: Int, start: Int) async throws -> Bool {
    let payload = toBytes64(sessionId) + toBytes64(start) + toBytes64(0x7FFF_FFFF)
    let response = try await sendCommand(cmdId: Command.syncFileStart, payload: payload)
    return response != nil
  }

  private func stopSync() async throws {
    let command: [UInt8] = [1, UInt8(Command.stopSync & 0xFF), UInt8((Command.stopSync >> 8) & 0xFF), 1]
    try await commandQueue.run { [weak self] in
      guard let self else { throw DeviceTransportError.disposed }
      try await self.transport.writeCharacteristic(
        data: Data(command),
        serviceUUID: DeviceUUIDs.PLAUD.service,
        characteristicUUID: DeviceUUIDs.PLAUD.writeCharacteristic,
        withResponse: true
      )
    }
  }

  private func setupRecordingSession() async throws {
    recordingSetupAttempted = true
    let maxRetries = 3
    var lastError: Error?

    for attempt in 0..<maxRetries {
      try Task.checkCancellation()
      do {
        if attempt > 0 {
          logger.debug("Retry attempt \(attempt)/\(maxRetries)")
          try await operationClock.sleep(for: .seconds(attempt))
        }

        try await stopRecord(sessionId: 0)
        try await operationClock.sleep(for: .milliseconds(500))

        guard let recordInfo = try await startRecord() else { continue }

        sessionId = recordInfo.sessionId

        try await operationClock.sleep(for: .seconds(1))

        if try await startSync(sessionId: recordInfo.sessionId, start: recordInfo.startTime) {
          logger.debug("Recording session setup successful")
          return
        }
      } catch {
        guard !Task.isCancelled else { throw CancellationError() }
        lastError = error
        logger.debug("Setup error (attempt \(attempt + 1)): \(error.localizedDescription)")
      }
    }

    throw lastError
      ?? DeviceConnectionError.operationFailed(
        "PLAUD recording session setup failed"
      )
  }

  private func stopRecordingSession() async throws {
    guard recordingSetupAttempted else { return }
    recordingSetupAttempted = false
    let sessionToStop = sessionId ?? 0
    var failures: [String] = []
    do {
      try await stopSync()
    } catch {
      failures.append(error.localizedDescription)
    }
    do {
      try await stopRecord(sessionId: sessionToStop)
    } catch {
      failures.append(error.localizedDescription)
    }
    sessionId = nil

    guard failures.isEmpty else {
      let message = failures.joined(separator: "; ")
      logger.debug("Error stopping recording session: \(message)")
      await transport.disconnect()
      throw DeviceConnectionError.operationFailed(message)
    }
  }

  // MARK: - Battery

  override func getBatteryLevel() async -> Int {
    guard await isConnected() else { return -1 }

    do {
      guard let response = try await sendCommand(cmdId: Command.getBattery, payload: []),
        response.count >= 2
      else {
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
        response.count >= 2
      else {
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
      let pollingTask = Task { [weak self] in
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
          do {
            try await self.operationClock.sleep(for: .seconds(60))
          } catch {
            break
          }
          guard !Task.isCancelled else { break }

          let level = await self.getBatteryLevel()
          if level >= 0 && level != lastLevel {
            lastLevel = level
            continuation.yield(level)
          }
        }

        continuation.finish()
      }
      continuation.onTermination = { @Sendable _ in
        pollingTask.cancel()
      }
    }
  }

  // MARK: - Audio

  override func getAudioCodec() async -> BleAudioCodec {
    .opusFS320
  }

  override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
    let rawStream = audioStreamController.makeStream()
    return AsyncThrowingStream { continuation in
      let chunkingTask = Task { @MainActor in
        var buffer = [UInt8]()
        do {
          for try await data in rawStream {
            buffer.append(contentsOf: data)
            while buffer.count >= 80 {
              continuation.yield(Data(buffer.prefix(80)))
              buffer.removeFirst(80)
            }
          }
          if !buffer.isEmpty {
            continuation.yield(Data(buffer))
          }
          continuation.finish()
        } catch {
          continuation.finish(throwing: error)
        }
      }
      continuation.onTermination = { @Sendable _ in
        chunkingTask.cancel()
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
      UInt8((value >> 24) & 0xFF),
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
      UInt8((value >> 56) & 0xFF),
    ]
  }

  private func toInt32(_ bytes: [UInt8]) -> Int {
    guard bytes.count >= 4 else { return 0 }
    return Int(bytes[0]) | (Int(bytes[1]) << 8) | (Int(bytes[2]) << 16) | (Int(bytes[3]) << 24)
  }
}
