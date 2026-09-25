import CoreBluetooth
import UIKit

/// Observes the real iOS GATT callback contract, not OmiBleManager policy.
/// Only subscribes to the audio characteristic; never writes firmware/storage
/// controls. Payloads are counted and discarded. Names/identifiers stay in UI.
final class WearableProbe: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    var update: ((String) -> Void)?
    var choose: (([CBPeripheral]) -> Void)?
    private var central: CBCentralManager!
    private var candidates = [CBPeripheral]()
    private var peripheral: CBPeripheral?
    private var events = [[String: Any]]()
    private var began = Date()
    private var origin = ProcessInfo.processInfo.systemUptime
    private var runID = UUID().uuidString
    private var packets = 0
    private var bytes = 0
    private var generation = 0
    private var firstPacket = false
    private var stopped = false
    private var scanning = false
    private var scanFinished = false
    private var timer: Timer?
    private var duration = 90.0
    private var lastPacketAt: Double?
    private var maxPacketGapMS = 0.0
    private var intervalPacketGapMS = 0.0

    func begin(duration: Double = 90) {
        self.duration = duration
        began = Date(); origin = ProcessInfo.processInfo.systemUptime
        record("scan_requested")
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.record("sample", probeResources()); self.intervalPacketGapMS = 0
            if self.packets > 0 {
                self.update?("\(self.packets) audio packets · connection \(self.generation)\n\nAudio discarded. Test stops after \(Int(self.duration)) seconds.")
            }
            if ProcessInfo.processInfo.systemUptime - self.origin >= self.duration { self.stop() }
        }
        central = CBCentralManager(delegate: self, queue: .main,
                                   options: [CBCentralManagerOptionShowPowerAlertKey: false])
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        record("bluetooth_state", ["state": central.state.rawValue, "authorization": CBCentralManager.authorization.rawValue])
        guard !stopped else { return }
        guard central.state == .poweredOn else {
            update?("Bluetooth is unavailable. Allow Bluetooth access and turn it on, return here. The trace records permission state.")
            return
        }
        guard !scanning && !scanFinished else { return }
        scanning = true
        candidates = central.retrieveConnectedPeripherals(withServices: [CBUUID(string: ProbeBleUUIDs.service)])
        central.scanForPeripherals(withServices: [CBUUID(string: ProbeBleUUIDs.service)])
        update?("Looking for Omi wearables…")
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in
            guard let self, !self.stopped else { return }
            self.central.stopScan(); self.scanning = false; self.scanFinished = true
            self.record("scan_finished", ["candidate_count": self.candidates.count])
            if self.candidates.isEmpty { self.update?("No Omi wearable found. Bring it nearby and start a new test.") }
            else { self.choose?(self.candidates) }
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        if !candidates.contains(where: { $0.identifier == peripheral.identifier }) { candidates.append(peripheral) }
    }
    func connect(_ selected: CBPeripheral) {
        guard !stopped else { return }
        peripheral = selected; selected.delegate = self
        record("connect_requested")
        update?("Connecting…")
        central.connect(selected)

    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        guard !stopped else { central.cancelPeripheralConnection(peripheral); return }
        generation += 1; firstPacket = false
        record("connected")
        peripheral.discoverServices([CBUUID(string: ProbeBleUUIDs.service)])
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard !stopped else { return }
        guard error == nil, let service = peripheral.services?.first(where: { $0.uuid == CBUUID(string: ProbeBleUUIDs.service) }) else {
            record("services_failed"); return
        }
        record("services_discovered")
        peripheral.discoverCharacteristics([CBUUID(string: ProbeBleUUIDs.audio)], for: service)
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard !stopped else { return }
        guard error == nil, let characteristic = service.characteristics?.first(where: { $0.uuid == CBUUID(string: ProbeBleUUIDs.audio) }) else {
            record("characteristics_failed"); return
        }
        record("audio_characteristic_ready", ["can_notify": characteristic.properties.contains(.notify)])
        peripheral.setNotifyValue(true, for: characteristic)
        record("subscribe_requested")
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard !stopped else { return }
        record(error == nil && characteristic.isNotifying ? "subscribed" : "subscription_failed")
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard !stopped, characteristic.uuid == CBUUID(string: ProbeBleUUIDs.audio) else { return }
        guard error == nil, let data = characteristic.value, !data.isEmpty else { record("notification_error"); return }
        let now = ProcessInfo.processInfo.systemUptime
        if let lastPacketAt {
            let gap = (now - lastPacketAt) * 1000
            maxPacketGapMS = max(maxPacketGapMS, gap); intervalPacketGapMS = max(intervalPacketGapMS, gap)
        }
        lastPacketAt = now
        packets += 1; bytes += data.count
        if !firstPacket { firstPacket = true; record("audio_started", ["packet_bytes": data.count]) }
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        record("disconnected", ["expected": stopped, "error_code": (error as NSError?)?.code ?? 0])
        if !stopped {
            record("reconnect_requested")
            central.connect(peripheral)
        }
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        record("connect_failed", ["error_code": (error as NSError?)?.code ?? 0])
        update?("Connection failed. Stop this test and try again.")
    }
    func stop() {
        guard !stopped else { return }
        stopped = true; timer?.invalidate(); timer = nil
        central?.stopScan()
        if let peripheral { central.cancelPeripheralConnection(peripheral) }
        record("completed")
        update?("Wearable trace saved.\n\(packets) packets across \(generation) connections.\n\nNo audio was retained.")
    }
    private func record(_ kind: String, _ extra: [String: Any] = [:]) {
        var event = extra
        event["kind"] = kind; event["elapsed_ms"] = Int((ProcessInfo.processInfo.systemUptime - origin) * 1000)
        event["packets"] = packets; event["bytes"] = bytes; event["generation"] = generation
        event["app_state"] = UIApplication.shared.applicationState == .background ? "background" : "foreground"
        event["max_packet_gap_ms"] = maxPacketGapMS
        event["interval_packet_gap_ms"] = intervalPacketGapMS
        events.append(event)
        let buildURL = Bundle.main.url(forResource: "build", withExtension: "json")!
        let build = (try? Data(contentsOf: buildURL)).flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? [:]
        let receipt: [String: Any] = ["schema": "omi-ble-radio-probe/v1", "run_id": runID,
                                    "scope": "corebluetooth-radio-only", "audio_retained": false,
                                    "started_at": ISO8601DateFormatter().string(from: began),
                                    "build": build, "events": events, "requested_duration_seconds": duration]
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("wearable-\(runID).json")
        do {
            let data = try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        } catch { update?("Evidence could not be saved; this run cannot qualify.") }
    }
}

final class WearableViewController: UIViewController {
    let probe = WearableProbe()
    let status = UILabel()
    var duration = 90.0
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .systemBackground
        let title = UILabel(); title.text = "Omi Wearable Probe"; title.font = .preferredFont(forTextStyle: .title1)
        status.numberOfLines = 0
        let stop = UIButton(type: .system); stop.setTitle("Stop wearable test", for: .normal)
        stop.addTarget(self, action: #selector(stopRun), for: .touchUpInside)
        let done = UIButton(type: .system); done.setTitle("Back", for: .normal)
        done.addTarget(self, action: #selector(close), for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [title, status, stop, done]); stack.axis = .vertical; stack.spacing = 30
        stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 40),
        ])
        probe.update = { [weak self] text in self?.status.text = text }
        probe.choose = { [weak self] candidates in
            guard let self else { return }
            let alert = UIAlertController(title: "Choose your Omi wearable", message: "Only select your own device.", preferredStyle: .alert)
            for candidate in candidates {
                alert.addAction(UIAlertAction(title: candidate.name ?? "Omi \(candidate.identifier.uuidString.suffix(4))", style: .default) { _ in
                    self.probe.connect(candidate)
                })
            }
            alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in self.probe.stop() })
            self.present(alert, animated: true)
        }
        probe.begin(duration: duration)
    }
    @objc private func stopRun() { probe.stop() }
    @objc private func close() { probe.stop(); dismiss(animated: true) }
}
