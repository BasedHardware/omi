// Compiled by omi_ble_connection_policy_test.rb with production manager methods.
// Fake radio and scheduler make suspension, scan coalescing and cooldown deterministic.
import CoreBluetooth
import Foundation

final class TestPeripheral {
    let identifier = UUID()
    var name: String? = "Omi"
    var state: CBPeripheralState = .disconnected
    weak var delegate: ManagerHarness?
}
final class TestCentral {
    var state: CBManagerState = .poweredOn
    var connects = 0
    var scanning = false
    var startDelays: [Double] = []
    func connect(_ peripheral: TestPeripheral, options: [String: Any]?) {
        connects += 1
        startDelays.append((options?[CBConnectPeripheralOptionStartDelayKey] as? NSNumber)?.doubleValue ?? 0)
    }
    func cancelPeripheralConnection(_ peripheral: TestPeripheral) { peripheral.state = .disconnected }
    func retrievePeripherals(withIdentifiers: [UUID]) -> [TestPeripheral] { [] }
    func stopScan() { scanning = false }
    func scanForPeripherals(withServices: [CBUUID], options: [String: Any]) { scanning = true }
}
final class TestWorkItem {
    let body: () -> Void
    var cancelled = false
    init(block: @escaping () -> Void) { body = block }
    func cancel() { cancelled = true }
    func perform() { if !cancelled { body() } }
}
final class TestQueue {
    var now: TimeInterval = 100
    var tasks: [(TimeInterval, TestWorkItem)] = []
    func asyncAfter(deadline: TimeInterval, execute: TestWorkItem) { tasks.append((deadline, execute)) }
    func asyncAfter(deadline: TimeInterval, execute: @escaping () -> Void) {
        asyncAfter(deadline: deadline, execute: TestWorkItem(block: execute))
    }
    func advance(_ seconds: TimeInterval) {
        let end = now + seconds
        while let next = tasks.enumerated().filter({ $0.element.0 <= end }).min(by: { $0.element.0 < $1.element.0 }) {
            tasks.remove(at: next.offset)
            now = next.element.0
            next.element.1.perform()
        }
        now = end
    }
}
struct BlePeripheral {
    let uuid: String
    let name: String
    let rssi: Int64
    let serviceUuids: [String]
}
enum OmiBleDiscoveryNaming {
    static func discoveredName(advertisedLocalName: String?, cachedName: String?, advertisementData: [String: Any]) -> String {
        cachedName ?? ""
    }
}
struct TestDeliveryError: Error { let code = "test" }
final class TestFlutterApi {
    func onPeripheralDiscovered(peripheral: BlePeripheral, completion: (Bool) -> Void) { completion(true) }
    func onPeripheralDisconnected(peripheralUuid: String, error: String?, completion: (Result<Void, TestDeliveryError>) -> Void) {
        completion(.success(()))
    }
}
final class OmiCaptureReconnect {
    enum Stage { case reconnecting, finished }
    var stage: Stage = .reconnecting
    var disconnected = false
    static func acceptsDownCallback(currentOwner: Bool, connected: Bool) -> Bool { currentOwner && !connected }
    func finish(_ success: Bool) { stage = .finished }
    func settleResume(_ settled: Bool) {}
    func didDisconnect(pairingLost: Bool) { disconnected = true; stage = .finished }
}
final class TestCaptureSession {
    func disconnected(recovering: Bool) {}
    func reconnectTransaction(connected: () -> Bool, connect: @escaping () -> Void,
                              reportLink: @escaping (Bool) -> Void, completion: @escaping (Bool) -> Void) -> OmiCaptureReconnect {
        OmiCaptureReconnect()
    }
}
final class TestStorageProgress { func isActive(_ uuid: String, now: TimeInterval) -> Bool { false } }
struct CaptureAdmissionPolicy {
    var muted = false
    static func load(from: UserDefaults) -> Self { Self() }
}
enum OmiBatchAudioWriter {
    static let shared = TestWriter()
    final class TestWriter { func stop(_ reason: String) {} }
}
enum LimitlessFlashDrainEngine {
    static let shared = TestEngine()
    final class TestEngine { func onDeviceDisconnected(_ uuid: String) {} }
}
enum OmiBlePairingPolicy { static func isPairingLost(_ error: Error?) -> Bool { false } }

final class ManagerHarness {
    let queue = TestQueue()
    let centralManager = TestCentral()
    var flutterApi: TestFlutterApi? = TestFlutterApi()
    var reconnectIntent: OmiSavedReconnectIntent
    var savedReconnect: Set<String> { reconnectIntent.saved }
    var peripherals: [String: TestPeripheral] = [:]
    var manuallyDisconnected: Set<String> = []
    var everConnected: Set<String> = []
    var pairingRecoveryInFlight: Set<String> = []
    var pairingLostBlocked: Set<String> = []
    var captureReconnects: [String: OmiCaptureReconnect] = [:]
    var captureSessions: [String: TestCaptureSession] = [:]
    let captureStorageProgress = TestStorageProgress()
    var connectionStartTimes: [String: Int64] = [:]
    var connectPendingSince: [String: Int64] = [:]
    var savedScanTargets: Set<String> = []
    var savedScanTasks: [String: TestWorkItem] = [:]
    var pausedSavedScanTargets: Set<String> = []
    var scanObservations: [String: Int] = [:]
    var diagnosticScanTargets: Set<String> = []
    var diagnosticScanTasks: [String: TestWorkItem] = [:]
    var diagnosticScanStarted: Set<String> = []
    static let reconnectServices = ["19B10000-E8F2-537E-4F6C-D104768A1214"]
    var savedRetryAttempts: [String: Int] = [:]
    var savedRetryTasks: [String: TestWorkItem] = [:]
    var savedSetupRetryAfter: [String: TimeInterval] = [:]
    var savedConnectRetryAfter: [String: TimeInterval] = [:]
    var savedOutageStarted: [String: Date] = [:]
    var failedReadyRequests: Set<String> = []
    var readyRequests: Set<String> = []
    var discoveryRetries: [String: Int] = [:]
    var discoveryStartedAt: [String: TimeInterval] = [:]
    var isScanning = false
    let defaultsSuite = "manager-reconnect-" + UUID().uuidString
    init() {
        reconnectIntent = OmiSavedReconnectIntent(defaults: UserDefaults(suiteName: defaultsSuite)!)
    }
    deinit { UserDefaults.standard.removePersistentDomain(forName: defaultsSuite) }
    func setCaptureAuthorized(uuid: String, authorized: Bool) {}
    func shouldAutoReconnect(uuid: String, pairingLost: Bool) -> Bool { !manuallyDisconnected.contains(uuid) && !pairingLost }
    func logBle(uuid: String, event: String, detail: String) {}
    func reportSavedReconnect(_ uuid: String, result: String) {}
    func finishReadyRequest(uuid: String) { readyRequests.remove(uuid) }
    func peripheralUuidString(_ peripheral: TestPeripheral) -> String { peripheral.identifier.uuidString }
    func fullUuidString(_ uuid: CBUUID) -> String { uuid.uuidString }
    func cleanupPeripheral(_ uuid: String) { failedReadyRequests.remove(uuid) }
    func markPairingLost(uuid: String) { manuallyDisconnected.insert(uuid) }
    func persistDisconnectEvent(uuid: String, reason: String, reasonCode: Int, isManual: Bool, eventType: String) {}
    func incrementFailToConnectCount(uuid: String) {}
    static func bleReasonString(from: Error?) -> String { "test" }
    func getBluetoothState() -> String { "on" }
    func captureSession(_ uuid: String) -> TestCaptureSession { TestCaptureSession() }
    // Production methods are inserted here by the Ruby runner.
}

@main struct SavedReconnectManagerTests {
    static func fixture() -> (ManagerHarness, TestPeripheral, String) {
        let manager = ManagerHarness()
        let peripheral = TestPeripheral()
        let uuid = peripheral.identifier.uuidString
        manager.peripherals[uuid] = peripheral
        manager.reconnectIntent.configure(uuid, enabled: true)
        return (manager, peripheral, uuid)
    }
    static func main() {
        // Each capture down path must submit an OS request before ANY timer runs.
        for failToConnect in [false, true] {
            let (manager, peripheral, uuid) = fixture()
            manager.captureReconnects[uuid] = OmiCaptureReconnect()
            if failToConnect {
                manager.centralManager(manager.centralManager, didFailToConnect: peripheral, error: nil)
            } else {
                manager.centralManager(manager.centralManager, didDisconnectPeripheral: peripheral, error: nil)
            }
            precondition(manager.centralManager.connects == 1, "capture down callback stranded on timer")
            precondition(manager.savedRetryAttempts[uuid, default: 0] == (failToConnect ? 1 : 0))
        }
        // Repeated real failures before the watchdog fires still leave a request.
        do {
            let (manager, peripheral, uuid) = fixture()
            for failure in 1...3 {
                manager.captureReconnects[uuid] = OmiCaptureReconnect()
                manager.centralManager(manager.centralManager, didFailToConnect: peripheral, error: nil)
                precondition(manager.centralManager.connects == failure)
                precondition(manager.savedRetryAttempts[uuid] == failure)
                precondition(manager.centralManager.startDelays.last == OmiBleConnectionPolicy.savedRetryDelay(attempt: failure))
            }
            manager.centralManager(manager.centralManager, didDiscover: peripheral, advertisementData: [:], rssi: -50)
            precondition(manager.centralManager.startDelays.last == 0, "discovery must skip radio backoff")
        }
        // Capture timeout after the down callback hands ownership back immediately.
        do {
            let (manager, peripheral, uuid) = fixture()
            peripheral.state = .connected
            manager.recoverCaptureConnection(uuid: uuid) { _ in }
            let recovery = manager.captureReconnects[uuid]!
            recovery.disconnected = true
            peripheral.state = .disconnected
            manager.queue.advance(OmiCaptureHealth.Policy.reconnectTimeout)
            precondition(manager.centralManager.connects == 1, "capture timeout owes pending OS request")
            precondition(manager.savedRetryAttempts[uuid, default: 0] == 0)
        }
        // Discovery while backoff exists is the one notification with duplicates off.
        do {
            let (manager, peripheral, uuid) = fixture()
            manager.scheduleSavedRetry(peripheral, uuid: uuid)
            let retry = manager.savedRetryTasks[uuid]!
            manager.centralManager(manager.centralManager, didDiscover: peripheral, advertisementData: [:], rssi: -50)
            precondition(retry.cancelled)
            precondition(manager.savedRetryTasks[uuid] == nil)
            precondition(manager.centralManager.connects == 2)
            manager.queue.advance(120)
            precondition(manager.centralManager.connects == 2, "cancelled retry fired")
            precondition(manager.savedRetryAttempts[uuid, default: 0] == 0, "connects are not failures")
        }
        // Actual GATT failures escalate 1, 2, 4 ... 60 seconds. The OS owns
        // the delay even with all app timers held; release/scan cannot bypass it.
        do {
            let (manager, peripheral, uuid) = fixture()
            for failure in 1...10 {
                peripheral.state = .connected
                manager.reportDiscoveryFailure(uuid: uuid, reason: "timeout")
                let delay = OmiBleConnectionPolicy.savedRetryDelay(attempt: failure)
                let count = manager.centralManager.connects
                manager.disconnectPeripheral(uuid: uuid) // Non-user Dart release after terminal GATT failure.
                precondition(manager.savedReconnect.contains(uuid))
                precondition(manager.centralManager.connects == count)
                manager.centralManager(manager.centralManager, didDisconnectPeripheral: peripheral, error: nil)
                precondition(manager.centralManager.connects == count + 1, "OS must own delayed setup retry")
                precondition(manager.centralManager.startDelays.last == delay)
                manager.queue.now += delay / 2 // Timers deliberately remain suspended.
                manager.issueConnect(peripheral, uuid: uuid, source: "transport_release")
                precondition(manager.centralManager.startDelays.last == delay / 2)
                manager.scheduleSavedRetry(peripheral, uuid: uuid)
                let retry = manager.savedRetryTasks[uuid]!
                manager.centralManager(manager.centralManager, didDiscover: peripheral, advertisementData: [:], rssi: -50)
                precondition(retry.cancelled)
                precondition(manager.savedRetryTasks[uuid] == nil)
                precondition(manager.centralManager.startDelays.last == delay / 2)
                precondition(manager.savedRetryAttempts[uuid] == failure)
                precondition(delay <= 60)
                manager.queue.now += delay / 2
                manager.issueConnect(peripheral, uuid: uuid, source: "foreground")
                precondition(manager.centralManager.startDelays.last == 0)
                manager.failedReadyRequests.remove(uuid)
            }
        }
        // No cached record: filtered windows stop after 5s and resume after 55s.
        do {
            let (manager, _, uuid) = fixture()
            manager.peripherals.removeAll()
            manager.reconcileSavedReconnect(uuid, source: "cold_start")
            precondition(manager.centralManager.scanning)
            manager.queue.advance(5)
            precondition(!manager.centralManager.scanning)
            manager.reconcileSavedReconnect(uuid, source: "foreground")
            precondition(!manager.centralManager.scanning, "reconciliation bypassed rest")
            manager.queue.advance(54)
            precondition(!manager.centralManager.scanning)
            manager.queue.advance(1)
            precondition(manager.centralManager.scanning)
            manager.endSavedScan(uuid, reason: "disabled")
            manager.queue.advance(120)
            precondition(!manager.centralManager.scanning, "retired scan resurrected")
        }
        print("saved reconnect manager paths passed")
    }
}
