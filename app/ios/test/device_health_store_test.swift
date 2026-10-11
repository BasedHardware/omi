import Foundation

@main
struct DeviceHealthStoreTest {
    static func main() {
        let suite = "device-health-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = OmiDeviceHealthStore(defaults: defaults)
        first.setPolicy(enabled: true, epoch: 7, retire: true)
        first.start("device", at: 1000)
        precondition(first.openSince("device") == nil)
        let restarted = OmiDeviceHealthStore(defaults: defaults)
        precondition(restarted.openSince("device") == 1000)
        restarted.start("device", at: 12000)
        precondition(restarted.openSince("device") == 1000)
        defaults.removeObject(forKey: "ble_audio_outage_device")
        precondition(restarted.openSince("device") == nil)
        restarted.end("device", at: 15000)
        precondition(defaults.object(forKey: "ble_session_device") == nil)
        precondition(restarted.openSince("device") == 15000)
        defaults.set([["ts": 1]], forKey: "battery_history_device")
        defaults.set([["timestamp": 1]], forKey: "ble_diagnostics_disconnect_history_device")
        restarted.setPolicy(enabled: false, epoch: 8, retire: true)
        precondition(defaults.object(forKey: "battery_history_device") == nil)
        precondition(defaults.object(forKey: "ble_diagnostics_disconnect_history_device") == nil)
        precondition(defaults.object(forKey: "ble_audio_outage_device") == nil)
        restarted.start("device", at: 16000)
        restarted.end("device", at: 17000)
        precondition(defaults.object(forKey: "ble_session_device") == nil)
        precondition(defaults.object(forKey: "ble_audio_outage_device") == nil)
        print("Device health store: 14 assertions passed")
    }
}
