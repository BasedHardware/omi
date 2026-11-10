import AppKit
import CoreBluetooth
import Darwin
import Foundation

func now() -> String { ISO8601DateFormatter().string(from: Date()) }
func stderr(_ text: String) { FileHandle.standardError.write(Data((text + "\n").utf8)) }

// Reserve the receipt before constructing any Bluetooth object. O_EXCL also rejects symlinks.
func exclusiveFile(_ path: String) throws -> FileHandle {
    let fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard fd >= 0 else { throw InputError.invalid("Cannot exclusively create file (errno \(errno)): \(path)") }
    return FileHandle(fileDescriptor: fd, closeOnDealloc: true)
}

final class ReceiptWriter: @unchecked Sendable {
    private let lock = NSLock()
    private var latest: Receipt
    private var emitted = false
    private let file: FileHandle
    private let path: String
    init(receipt: Receipt, file: FileHandle, path: String) { latest = receipt; self.file = file; self.path = path }
    func update(_ receipt: Receipt) { lock.lock(); defer { lock.unlock() }; latest = receipt }
    func finish(_ receipt: Receipt? = nil, watchdog: Bool = false, interrupted: Bool = false) -> Never {
        lock.lock()
        if emitted { lock.unlock(); _exit(2) }
        emitted = true
        var result = receipt ?? latest
        if watchdog {
            result.outcome = result.progress.outcome(.deadline)
            result.detail = "Hard watchdog deadline; cleanup acknowledgments may be absent"
        }
        if interrupted {
            result.outcome = result.progress.outcome(.interrupted)
            result.detail = "Interrupted by SIGINT/SIGTERM; process exit drops the connection"
        }
        result.completedAt = now()
        do {
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try file.write(contentsOf: encoder.encode(result) + Data([10]))
            try file.close()
            FileHandle.standardOutput.write(Data((path + "\n").utf8))
        } catch { stderr("Receipt write failed: \(error)"); _exit(2) }
        _exit(result.outcome == .passed ? 0 : 1)
    }
}

final class Central: NSObject, NSApplicationDelegate, CBCentralManagerDelegate, CBPeripheralDelegate {
    let options: Options
    let writer: ReceiptWriter
    var receipt: Receipt { didSet { writer.update(receipt) } }
    var manager: CBCentralManager!
    var target: CBPeripheral?
    var audioCharacteristic: CBCharacteristic?
    var readQueue: [CBCharacteristic] = []
    var pendingRead: CBCharacteristic?
    var discoveryRemaining = 0
    var connectionNumber = 0
    var audioFile: FileHandle?
    var savedBytes = 0
    var deadline: DispatchWorkItem?
    var setupEnd: DispatchWorkItem?
    var captureEnd: DispatchWorkItem?
    var cleanupEnd: DispatchWorkItem?
    var captureDeadline: TimeInterval?
    var unsubscriptionRequested = false, disconnectRequested = false
    var stopped = false

    init(options: Options, receipt: Receipt, writer: ReceiptWriter, audioFile: FileHandle?) {
        self.options = options; self.receipt = receipt; self.writer = writer; self.audioFile = audioFile
    }
    func phase(_ phase: Phase) { receipt.progress.phase = phase }
    func applicationDidFinishLaunching(_ notification: Notification) {
        let timer = DispatchWorkItem { [weak self] in self?.stop(.deadline, "Command deadline reached") }
        deadline = timer
        DispatchQueue.main.asyncAfter(deadline: .now() + options.deadlineSeconds, execute: timer)
        if options.command == .audio {
            let setup = DispatchWorkItem { [weak self] in
                guard let self else { return }
                if ![Phase.audio, .unsubscribing, .disconnectFinal].contains(self.receipt.progress.phase) {
                    self.stop(.deadline, "Audio setup exceeded 30 seconds")
                }
            }
            setupEnd = setup
            DispatchQueue.main.asyncAfter(deadline: .now() + 30, execute: setup)
        }
        let auth = CBManager.authorization
        receipt.progress.permissionPending = auth == .notDetermined
        if auth == .denied || auth == .restricted { stop(.permission, "Bluetooth authorization denied or restricted"); return }
        manager = CBCentralManager(delegate: self, queue: .main, options: [CBCentralManagerOptionShowPowerAlertKey: false])
    }
    func stop(_ reason: StopReason, _ detail: String) {
        guard !stopped else { return }
        stopped = true
        deadline?.cancel(); setupEnd?.cancel(); captureEnd?.cancel(); cleanupEnd?.cancel()
        receipt.outcome = receipt.progress.outcome(reason)
        receipt.detail = detail
        manager?.stopScan()
        // Errors/deadlines cannot wait indefinitely for cleanup callbacks. Disconnect also removes the CCC subscription.
        if let target {
            if let audioCharacteristic, audioCharacteristic.isNotifying, !unsubscriptionRequested {
                unsubscriptionRequested = true
                target.setNotifyValue(false, for: audioCharacteristic)
            }
            requestDisconnect(target)
        }
        do { try audioFile?.close() } catch {
            if reason != .gatt { receipt.outcome = .audioFailed }
            receipt.detail += "; audio file close failed"
        }
        writer.finish(receipt)
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard !stopped else { return }
        receipt.progress.permissionPending = CBManager.authorization == .notDetermined
        if central.state == .unauthorized { stop(.permission, "CoreBluetooth unauthorized"); return }
        if central.state == .poweredOff || central.state == .unsupported { stop(.bluetooth, "Bluetooth off or unsupported"); return }
        if central.state != .poweredOn {
            if receipt.progress.phase != .waiting { stop(.bluetooth, "Bluetooth became unavailable") }
            return
        }
        guard receipt.progress.phase == .waiting else { return }
        phase(.scanning)
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true])
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard !stopped, receipt.progress.phase == .scanning,
              let name = advertisementData[CBAdvertisementDataLocalNameKey] as? String,
              matches(name: name, prefix: options.prefix) else { return }
        let services = ((advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? [])
            + (advertisementData[CBAdvertisementDataOverflowServiceUUIDsKey] as? [CBUUID] ?? []))
            .map { $0.uuidString }.sorted()
        let ad = Advertisement(name: name, rssi: RSSI.intValue, advertisedServices: services,
                               connectable: advertisementData[CBAdvertisementDataIsConnectable] as? Bool)
        receipt.progress.matched = true
        if receipt.advertisements.count < 512 { receipt.advertisements.append(ad) }
        else { receipt.advertisementsOmitted += 1 }
        if options.command == .scan { return }
        central.stopScan()
        target = peripheral; peripheral.delegate = self
        phase(.connecting)
        central.connect(peripheral, options: nil)
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        stop(.connection, "Connection failed; no retry: \(error?.localizedDescription ?? "unknown error")")
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        guard !stopped else { return }
        connectionNumber += 1
        disconnectRequested = false
        phase(.gatt)
        receipt.connections.append(ConnectionRecord(number: connectionNumber,
            maximumWriteWithResponse: peripheral.maximumWriteValueLength(for: .withResponse),
            maximumWriteWithoutResponse: peripheral.maximumWriteValueLength(for: .withoutResponse)))
        readQueue = []; pendingRead = nil; audioCharacteristic = nil
        peripheral.discoverServices(nil)
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard !stopped else { return }
        guard error == nil, let services = peripheral.services, !services.isEmpty else { stop(.gatt, "Service discovery failed"); return }
        receipt.connections[connectionNumber - 1].services = services.map { $0.uuid.uuidString }.sorted()
        // Enumerate all service UUIDs, but only discover characteristics in the read/notify allowlist.
        let wanted = services.filter { [UUIDs.information, UUIDs.featuresService, UUIDs.diagnosticsService, UUIDs.audioService].contains($0.uuid.uuidString) }
        discoveryRemaining = wanted.count
        guard discoveryRemaining > 0 else { stop(.gatt, "Required Device Information service absent"); return }
        for service in wanted {
            peripheral.discoverCharacteristics([UUIDs.firmware, UUIDs.serial, UUIDs.features, UUIDs.diagnostics, UUIDs.recovery, UUIDs.audioData].map { CBUUID(string: $0) }, for: service)
        }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard !stopped else { return }
        guard error == nil else { stop(.gatt, "Characteristic discovery failed"); return }
        for characteristic in service.characteristics ?? [] {
            let uuid = characteristic.uuid.uuidString
            let serviceUUID = service.uuid.uuidString
            if uuid == UUIDs.audioData && serviceUUID == UUIDs.audioService { audioCharacteristic = characteristic }
            let allowed = (serviceUUID == UUIDs.information && [UUIDs.firmware, UUIDs.serial].contains(uuid))
                || (connectionNumber == 1 && ((serviceUUID == UUIDs.featuresService && uuid == UUIDs.features)
                    || (serviceUUID == UUIDs.diagnosticsService && [UUIDs.diagnostics, UUIDs.recovery].contains(uuid))))
            if allowed && (connectionNumber == 1 || uuid == UUIDs.firmware) {
                guard characteristic.properties.contains(.read) else { stop(.gatt, "Refused: \(uuid) requires an operation other than read"); return }
                readQueue.append(characteristic)
            }
        }
        discoveryRemaining -= 1
        if discoveryRemaining == 0 {
            guard readQueue.contains(where: { $0.uuid == CBUUID(string: UUIDs.firmware) }) else {
                stop(.gatt, "Required firmware revision characteristic absent"); return
            }
            if connectionNumber == 1 {
                do {
                    let plan = try FirstConnectionReads(discovered: Set(readQueue.map { $0.uuid.uuidString }))
                    receipt.connections[0].absentOptionalCharacteristics = plan.absentOptional
                    readQueue = plan.ordered.compactMap { uuid in readQueue.first { $0.uuid.uuidString == uuid } }
                } catch { stop(.gatt, String(describing: error)); return }
            }
            readNext(peripheral)
        }
    }
    func readNext(_ peripheral: CBPeripheral) {
        observeLengths(peripheral)
        // DIS is ordered before optional reads. Resolve identity immediately after DIS, before reconnect/subscription.
        if connectionNumber == 1, receipt.identity.status == .pending,
           !readQueue.contains(where: { [UUIDs.firmware, UUIDs.serial].contains($0.uuid.uuidString) }) {
            receipt.identity.evaluate(serial: receipt.connections[0].reads[UUIDs.serial]?.text)
            guard receipt.identity.allowsContinuation else {
                stop(.gatt, receipt.identity.failureDetail ?? "Identity check incomplete"); return
            }
        }
        if !readQueue.isEmpty {
            let characteristic = readQueue.removeFirst(); pendingRead = characteristic
            peripheral.readValue(for: characteristic)
            return
        }
        pendingRead = nil
        if connectionNumber == 1 {
            phase(.disconnectForReconnect)
            requestDisconnect(peripheral)
        } else {
            receipt.progress.sessionComplete = true
            if options.command == .audio {
                guard let characteristic = audioCharacteristic, characteristic.properties.contains(.notify) else {
                    stop(.audio, "Audio notify characteristic absent; no enabling writes attempted"); return
                }
                phase(.subscribing)
                peripheral.setNotifyValue(true, for: characteristic)
            } else { disconnectFinal(peripheral) }
        }
    }
    func observeLengths(_ peripheral: CBPeripheral) {
        receipt.connections[connectionNumber - 1].maximumWriteWithResponse = peripheral.maximumWriteValueLength(for: .withResponse)
        receipt.connections[connectionNumber - 1].maximumWriteWithoutResponse = peripheral.maximumWriteValueLength(for: .withoutResponse)
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard !stopped else { return }
        if characteristic === audioCharacteristic && receipt.progress.phase == .audio {
            if let limit = captureDeadline, ProcessInfo.processInfo.systemUptime >= limit { endCapture(peripheral); return }
            guard error == nil, let data = characteristic.value else { stop(.audio, "Audio notification failed"); return }
            receipt.progress.audio.consume(data)
            if let audioFile {
                guard savedBytes + data.count + 4 <= 4 * 1024 * 1024 else { stop(.audio, "Audio output exceeded 4 MiB safety bound"); return }
                let count = UInt32(data.count)
                let length = Data((0..<4).map { UInt8(truncatingIfNeeded: count >> (8 * $0)) })
                do { try audioFile.write(contentsOf: length + data); savedBytes += data.count + 4; receipt.audioStored = true }
                catch { stop(.audio, "Audio file write failed"); return }
            }
            return
        }
        guard characteristic === pendingRead else { return }
        guard error == nil, let data = characteristic.value else { stop(.gatt, "Read failed (including protected attributes); no pairing or write retry: \(error?.localizedDescription ?? "no data")"); return }
        let uuid = characteristic.uuid.uuidString
        let decoded: DecodedValue
        if uuid == UUIDs.diagnostics { decoded = decodeDiagnostics(data) }
        else if uuid == UUIDs.recovery { decoded = decodeRecovery(data) }
        else if uuid == UUIDs.features { decoded = decodeFeatures(data) }
        else {
            decoded = decodeText(data)
            if decoded.text?.isEmpty != false {
                receipt.connections[connectionNumber - 1].reads[uuid] = decoded
                if uuid == UUIDs.serial && receipt.identity.status == .pending {
                    receipt.identity.evaluate(serial: nil)
                    stop(.gatt, receipt.identity.failureDetail ?? "Identity check failed: DIS serial was absent"); return
                }
                stop(.gatt, "Invalid DIS UTF-8 or empty value"); return
            }
        }
        receipt.connections[connectionNumber - 1].reads[uuid] = decoded
        readNext(peripheral)
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard !stopped, characteristic === audioCharacteristic else { return }
        guard error == nil else { stop(.audio, "Notification state change failed"); return }
        if receipt.progress.phase == .subscribing {
            guard characteristic.isNotifying else { stop(.audio, "Subscription was not enabled"); return }
            receipt.subscriptionAcknowledged = true
            phase(.audio)
            captureDeadline = ProcessInfo.processInfo.systemUptime + options.seconds
            let timer = DispatchWorkItem { [weak self] in
                guard let self, !self.stopped else { return }
                self.endCapture(peripheral)
            }
            captureEnd = timer
            DispatchQueue.main.asyncAfter(deadline: .now() + options.seconds, execute: timer)
        } else if receipt.progress.phase == .unsubscribing && !characteristic.isNotifying {
            receipt.unsubscriptionAcknowledged = true
            receipt.progress.audioComplete = true
            disconnectFinal(peripheral)
        }
    }
    func endCapture(_ peripheral: CBPeripheral) {
        guard receipt.progress.phase == .audio, let characteristic = audioCharacteristic else { return }
        phase(.unsubscribing)
        observeLengths(peripheral)
        let timer = DispatchWorkItem { [weak self] in self?.stop(.audio, "Audio cleanup exceeded two seconds") }
        cleanupEnd = timer
        DispatchQueue.main.asyncAfter(deadline: .now() + 2, execute: timer)
        unsubscriptionRequested = true
        peripheral.setNotifyValue(false, for: characteristic)
    }
    func disconnectFinal(_ peripheral: CBPeripheral) {
        phase(.disconnectFinal)
        requestDisconnect(peripheral)
    }
    func requestDisconnect(_ peripheral: CBPeripheral) {
        guard peripheral.state != .disconnected, !disconnectRequested else { return }
        disconnectRequested = true
        manager?.cancelPeripheralConnection(peripheral)
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        guard !stopped else { return }
        receipt.disconnectsAcknowledged += 1
        if receipt.progress.phase == .disconnectForReconnect && error == nil {
            disconnectRequested = false
            phase(.reconnecting)
            central.connect(peripheral, options: nil) // The sole reconnect; never retry a failure.
        } else if receipt.progress.phase == .disconnectFinal && error == nil {
            stop(.complete, "Session and requested cleanup completed")
        } else { stop(.connection, "Unexpected disconnect; no retry") }
    }
}

do {
    let options = try Options.parse(Array(CommandLine.arguments.dropFirst()))
    let file = try exclusiveFile(options.output)
    var receipt = Receipt(startedAt: now(), requestedSeconds: options.seconds, deadlineSeconds: options.deadlineSeconds,
                          progress: Progress(command: options.command, permissionPending: true))
    receipt.identity = IdentityCheck(expectedSerial: options.expectSerial)
    let writer = ReceiptWriter(receipt: receipt, file: file, path: options.output)
    signal(SIGINT, SIG_IGN); signal(SIGTERM, SIG_IGN)
    let signals = [SIGINT, SIGTERM].map { value -> DispatchSourceSignal in
        let source = DispatchSource.makeSignalSource(signal: value, queue: .global())
        source.setEventHandler { writer.finish(interrupted: true) }
        source.resume()
        return source
    }
    // Independent of AppKit's main queue: permission UI and missing callbacks cannot leave a run unbounded.
    DispatchQueue.global().asyncAfter(deadline: .now() + options.deadlineSeconds + 1) { writer.finish(watchdog: true) }
    var audioFile: FileHandle?
    if let path = options.keepAudio {
        do { audioFile = try exclusiveFile(path) }
        catch { var failed = receipt; failed.outcome = .audioFailed; failed.detail = "Cannot exclusively create audio output"; writer.finish(failed) }
    }
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let central = Central(options: options, receipt: receipt, writer: writer, audioFile: audioFile)
    app.delegate = central
    withExtendedLifetime((central, signals)) { app.run() }
    central.stop(.interrupted, "Application run loop ended")
} catch {
    stderr("\(error)\nUsage: CV1BLECentral scan|session|audio --seconds N --output NEW.json [--name-prefix Omi] [--expect-serial VALUE] [--keep-audio NEW.bin]\naudio requires --expect-serial VALUE")
    exit(2) // Invalid invocations/file collisions never initialize CoreBluetooth.
}
