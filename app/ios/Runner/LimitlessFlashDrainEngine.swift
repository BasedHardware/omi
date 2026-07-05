import Flutter
import Foundation

/// Native flash-drain engine for the Limitless pendant (Transcribe Later).
///
/// With batch mode on, the pendant records to its onboard flash (the Dart connector
/// suppresses live streaming). This engine periodically drains that flash with the
/// Flutter engine idle: it queries the storage state (msg21), switches the pendant
/// into download mode (msg8 {1,0}), reassembles the pushed flash pages, appends the
/// extracted opus frames to `LimitlessBatchAudioWriter`, and ACKs (msg7) — strictly
/// after an fsync barrier, because an ACK deletes the pendant's copy. When caught up
/// (or stalled) it returns the pendant to record-to-flash ({0,0}).
///
/// Hooked from `OmiBleManager`; all state is confined to `queue`. Wire codec lives
/// in `LimitlessProtocol` (pure, mirrors the Android/Dart golden fixtures).
final class LimitlessFlashDrainEngine {
    static let shared = LimitlessFlashDrainEngine()

    private static let limitlessServiceUuid = "632de001-604c-446b-a80f-7963e950f3fb"
    private static let limitlessTxCharUuid = "632de002-604c-446b-a80f-7963e950f3fb"

    private let cycleMs = 90_000
    private let firstCycleDelayMs = 5_000
    private let statusTimeoutMs = 8_000
    private let stallMs: Int64 = 30_000
    private let stallCheckMs = 5_000
    private let ackEveryPages = 25
    private let storageFullFraction = 0.05

    private enum Phase { case idle, awaitingStatus, draining }

    private struct Config {
        let deviceId: String
        let serviceUuid: String
        let characteristicUuid: String
    }

    private let queue = DispatchQueue(label: "com.omi.limitlessDrain")
    private let writer = LimitlessBatchAudioWriter()

    // All fields below are queue-confined.
    private var phase: Phase = .idle
    private var deviceUuid: String?
    private var messageIndex = 0
    private var requestId: Int64 = 0
    private var fragmentBuffer: [Int: [Int: Data]] = [:]
    private var endPage = 0
    private var maxSeenPageIndex = -1
    private var lastAppendedPageIndex = -1
    private var lastAckedPageIndex = -1
    private var pagesSinceAck = 0
    private var lastPageAtMs: Int64 = 0
    private var cycleTimer: DispatchSourceTimer?
    private var statusTimeoutTask: DispatchWorkItem?
    private var stallCheckTimer: DispatchSourceTimer?

    private init() {}

    /// Call on the main queue where the manager fires onDeviceReady. Subscribes the
    /// configured RX characteristic natively so drain works even when Dart never
    /// subscribed (state restoration without the Flutter engine).
    func onDeviceReady(_ peripheralUuid: String) {
        if let config = loadConfig(), config.deviceId == peripheralUuid.lowercased() {
            OmiBleManager.shared.subscribeCharacteristic(
                peripheralUuid: peripheralUuid,
                serviceUuid: config.serviceUuid,
                characteristicUuid: config.characteristicUuid
            )
        }
        queue.async {
            if let config = self.loadConfig(), config.deviceId != peripheralUuid.lowercased() { return }
            self.deviceUuid = peripheralUuid
            if self.phase != .draining { self.setBoolPref("pendantDraining", false) }
            self.cycleTimer?.cancel()
            let timer = DispatchSource.makeTimerSource(queue: self.queue)
            timer.schedule(
                deadline: .now() + .milliseconds(self.firstCycleDelayMs),
                repeating: .milliseconds(self.cycleMs)
            )
            timer.setEventHandler { [weak self] in self?.runCycle() }
            timer.resume()
            self.cycleTimer = timer
        }
    }

    func onDeviceDisconnected(_ peripheralUuid: String) {
        queue.async {
            guard self.deviceUuid?.lowercased() == peripheralUuid.lowercased() else { return }
            self.cycleTimer?.cancel()
            self.cycleTimer = nil
            self.resetDrainState("disconnected")
            self.deviceUuid = nil
            self.messageIndex = 0
            self.requestId = 0
            self.writer.stop("ble_disconnected")
        }
    }

    func stop(_ reason: String) {
        queue.async {
            self.cycleTimer?.cancel()
            self.cycleTimer = nil
            self.resetDrainState(reason)
        }
        writer.stop(reason)
    }

    /// Returns true when the packet was consumed for the drain engine (batch config
    /// matches this device + RX characteristic) — the caller must then skip the Dart
    /// forward so the Flutter engine stays idle.
    @discardableResult
    func handle(peripheralUuid: String, serviceUuid: String, characteristicUuid: String, value: Data) -> Bool {
        guard let config = loadConfig() else { return false }
        guard config.deviceId == peripheralUuid.lowercased() else { return false }
        guard config.serviceUuid == serviceUuid.lowercased(),
            config.characteristicUuid == characteristicUuid.lowercased() else { return false }
        queue.async { self.processPacket(value) }
        return true
    }

    // MARK: - Cycle (on `queue`)

    private func runCycle() {
        guard let uuid = deviceUuid else { return }
        guard phase == .idle else { return }
        guard let config = loadConfig() else {
            writer.stop("batch_disabled")
            return
        }
        guard config.deviceId == uuid.lowercased() else { return }

        phase = .awaitingStatus
        write(uuid, LimitlessProtocol.encodeSetCurrentTime(
            messageIndex: nextMessageIndex(), requestId: nextRequestId(), timestampMs: nowMs()))
        write(uuid, LimitlessProtocol.encodeGetDeviceStatus(
            messageIndex: nextMessageIndex(), requestId: nextRequestId()))

        statusTimeoutTask?.cancel()
        let task = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            if self.phase == .awaitingStatus {
                NSLog("[LimitlessDrain] storage status timed out — retrying next cycle")
                self.phase = .idle
            }
        }
        statusTimeoutTask = task
        queue.asyncAfter(deadline: .now() + .milliseconds(statusTimeoutMs), execute: task)
    }

    private func processPacket(_ data: Data) {
        if phase == .awaitingStatus, let state = LimitlessProtocol.parseDeviceStatus(data) {
            onStorageState(state)
        }

        guard let packet = LimitlessProtocol.parseBlePacket(data) else { return }
        fragmentBuffer[packet.index, default: [:]][packet.seq] = packet.payload
        guard let fragments = fragmentBuffer[packet.index], fragments.count == packet.numFrags else { return }

        var complete = Data(capacity: fragments.values.reduce(0) { $0 + $1.count })
        for i in 0 ..< packet.numFrags {
            guard let fragment = fragments[i] else { continue }
            complete.append(fragment)
        }
        fragmentBuffer.removeValue(forKey: packet.index)

        if phase == .draining {
            for page in LimitlessProtocol.parsePendantMessage(complete) {
                processFlashPage(page)
            }
        }
    }

    private func onStorageState(_ state: LimitlessProtocol.StorageState) {
        publishStorageState(state)
        guard phase == .awaitingStatus else { return }
        statusTimeoutTask?.cancel()
        statusTimeoutTask = nil

        let pageCount = state.newestFlashPage - state.oldestFlashPage + 1
        if state.newestFlashPage < state.oldestFlashPage || pageCount <= 0 {
            phase = .idle
            return
        }

        guard let uuid = deviceUuid else {
            phase = .idle
            return
        }
        fragmentBuffer.removeAll()
        endPage = state.newestFlashPage
        maxSeenPageIndex = -1
        lastAppendedPageIndex = -1
        lastAckedPageIndex = -1
        pagesSinceAck = 0
        lastPageAtMs = nowMs()
        phase = .draining
        setBoolPref("pendantDraining", true)
        NSLog("[LimitlessDrain] drain start: pages \(state.oldestFlashPage)..\(state.newestFlashPage) (\(pageCount))")
        write(uuid, LimitlessProtocol.encodeDownloadFlashPages(
            messageIndex: nextMessageIndex(), requestId: nextRequestId(), batchMode: true, realTime: false))

        stallCheckTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(
            deadline: .now() + .milliseconds(stallCheckMs),
            repeating: .milliseconds(stallCheckMs)
        )
        timer.setEventHandler { [weak self] in
            guard let self = self else { return }
            if self.phase == .draining, self.nowMs() - self.lastPageAtMs > self.stallMs {
                self.finishDrain("stall")
            }
        }
        timer.resume()
        stallCheckTimer = timer
    }

    private func processFlashPage(_ page: LimitlessProtocol.FlashPage) {
        lastPageAtMs = nowMs()
        guard let index = page.index else { return }

        if !page.opusFrames.isEmpty {
            if !writer.append(page.opusFrames, pageTimestampMs: page.timestampMs) {
                NSLog("[LimitlessDrain] append failed (storage guard?) — pausing drain without ACKing unwritten pages")
                finishDrain("append_failed")
                return
            }
        }
        lastAppendedPageIndex = max(lastAppendedPageIndex, index)
        maxSeenPageIndex = max(maxSeenPageIndex, index)
        pagesSinceAck += 1

        if pagesSinceAck >= ackEveryPages {
            if !ackWritten() {
                finishDrain("fsync_failed")
                return
            }
        }
        if maxSeenPageIndex >= endPage {
            finishDrain("caught_up")
        }
    }

    /// fsync barrier, then ACK everything appended so far. Never ACKs unwritten pages.
    /// On a failed barrier the watermark rolls back to the last ACK — a later ACK is
    /// up-to-index and would otherwise cover the unconfirmed pages — and the caller
    /// must end the drain so those pages redeliver next cycle.
    @discardableResult
    private func ackWritten() -> Bool {
        guard let uuid = deviceUuid else { return true }
        if lastAppendedPageIndex <= lastAckedPageIndex { return true }
        if !writer.syncToDisk() {
            NSLog("[LimitlessDrain] fsync failed — dropping ACK watermark, pages redrain next cycle")
            lastAppendedPageIndex = lastAckedPageIndex
            return false
        }
        write(uuid, LimitlessProtocol.encodeAcknowledgeProcessedData(
            messageIndex: nextMessageIndex(), requestId: nextRequestId(), upToIndex: lastAppendedPageIndex))
        lastAckedPageIndex = lastAppendedPageIndex
        pagesSinceAck = 0
        return true
    }

    private func finishDrain(_ reason: String) {
        guard phase == .draining else { return }
        stallCheckTimer?.cancel()
        stallCheckTimer = nil
        ackWritten()
        // Return the pendant to record-to-flash — unless batch mode was turned off
        // mid-drain, in which case the Dart connector owns the mode ({0,1}) and a
        // late {0,0} here would silently stop realtime streaming.
        if let uuid = deviceUuid, loadConfig() != nil {
            write(uuid, LimitlessProtocol.encodeDownloadFlashPages(
                messageIndex: nextMessageIndex(), requestId: nextRequestId(), batchMode: false, realTime: false))
        }
        phase = .idle
        setBoolPref("pendantDraining", false)
        NSLog("[LimitlessDrain] drain finished (\(reason)): appended<=\(lastAppendedPageIndex) acked<=\(lastAckedPageIndex) end=\(endPage)")
    }

    private func resetDrainState(_ reason: String) {
        statusTimeoutTask?.cancel()
        stallCheckTimer?.cancel()
        statusTimeoutTask = nil
        stallCheckTimer = nil
        fragmentBuffer.removeAll()
        if phase == .draining {
            NSLog("[LimitlessDrain] drain aborted (\(reason)): acked<=\(lastAckedPageIndex)")
            setBoolPref("pendantDraining", false)
        }
        phase = .idle
    }

    // MARK: - IO helpers

    private func nextMessageIndex() -> Int {
        let value = messageIndex
        messageIndex += 1
        return value
    }

    private func nextRequestId() -> Int64 {
        requestId += 1
        return requestId
    }

    private func nowMs() -> Int64 {
        return Int64(Date().timeIntervalSince1970 * 1000)
    }

    private func write(_ peripheralUuid: String, _ data: Data) {
        DispatchQueue.main.async {
            OmiBleManager.shared.writeCharacteristic(
                peripheralUuid: peripheralUuid,
                serviceUuid: Self.limitlessServiceUuid,
                characteristicUuid: Self.limitlessTxCharUuid,
                data: FlutterStandardTypedData(bytes: data)
            ) { result in
                if case .failure(let error) = result {
                    NSLog("[LimitlessDrain] TX write failed: \(error.localizedDescription)")
                }
            }
        }
    }

    private func publishStorageState(_ state: LimitlessProtocol.StorageState) {
        let pageCount = max(0, state.newestFlashPage - state.oldestFlashPage + 1)
        let d = UserDefaults.standard
        d.set(pageCount, forKey: "flutter.pendantPagesStored")
        if state.totalCapturePages > 0 {
            let almostFull = Double(state.freeCapturePages) < Double(state.totalCapturePages) * storageFullFraction
            d.set(almostFull, forKey: "flutter.pendantStorageAlmostFull")
        }
    }

    private func setBoolPref(_ key: String, _ value: Bool) {
        UserDefaults.standard.set(value, forKey: "flutter.\(key)")
    }

    // MARK: - Config

    private func loadConfig() -> Config? {
        let d = UserDefaults.standard
        guard d.bool(forKey: "flutter.batchModeEnabled") else { return nil }
        guard let raw = d.string(forKey: "flutter.nativeBleStreamConfig"), !raw.isEmpty,
            let data = raw.data(using: .utf8),
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        guard (json["deviceType"] as? String) == "limitless" else { return nil }
        guard let deviceId = json["deviceId"] as? String, !deviceId.isEmpty,
            let serviceUuid = json["serviceUuid"] as? String, !serviceUuid.isEmpty,
            let charUuid = json["characteristicUuid"] as? String, !charUuid.isEmpty else { return nil }
        return Config(
            deviceId: deviceId.lowercased(),
            serviceUuid: serviceUuid.lowercased(),
            characteristicUuid: charUuid.lowercased()
        )
    }
}
