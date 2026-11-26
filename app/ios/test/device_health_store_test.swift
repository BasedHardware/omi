import Foundation

@main
struct DeviceHealthStoreTest {
    static func main() {
        let suite = "device-health-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = OmiDeviceHealthStore(defaults: defaults)
        first.setPolicy(enabled: true, epoch: 7, retire: true)
        precondition(!first.connectedBefore("device"))
        first.recordConnected("device")
        precondition(OmiDeviceHealthStore(defaults: defaults).connectedBefore("device"))
        first.start("device", at: 1000)
        precondition(first.openSince("device") == nil)
        let restarted = OmiDeviceHealthStore(defaults: defaults)
        precondition(restarted.openSince("device") == 1000)
        restarted.start("device", at: 12000)
        precondition(restarted.openSince("device") == 1000)
        defaults.removeObject(forKey: "ble_audio_outage_device")
        precondition(restarted.openSince("device") == nil)
        restarted.end("device", at: 15000)
        restarted.recordDisconnect("device", at: 15000)
        precondition(OmiDeviceHealthStore(defaults: defaults).reconnectEvent("device") == 15000)
        // Audio outage accounting may retain a different, older start.
        defaults.set(Int64(1000), forKey: "ble_audio_outage_device")
        precondition(restarted.reconnectEvent("device") == 15000)
        precondition(OmiBleReconnectDiagnostics.eventType(["timestamp": Int64(1000), "lostAudioResolvedAt": Int64(17000)]) == "audio_recovered")
        precondition(OmiBleReconnectDiagnostics.eventType(["reasonCode": 8, "lostAudioResolvedAt": Int64(17000)]) == "disconnect")
        var reconnect = OmiBleReconnectDiagnostics()
        reconnect.recordEvent(timestampMs: restarted.reconnectEvent("device")!, eventType: "disconnect", isManual: false)
        let rows: [[String: Any]] = [["timestamp": Int64(15000), "timeToReconnectMs": Int64(0)]]
        let backfilled = reconnect.backfilledHistory(rows, nowMs: 17000, hadConnection: restarted.connectedBefore("device"),
            timestampOf: OmiBleReconnectDiagnostics.eventTimestamp, resolvedAtOf: { _ in nil },
            onLookupMiss: { _ in preconditionFailure("event timestamp must match its row") },
            withDuration: { row, duration in var result = row; result["timeToReconnectMs"] = duration; return result })
        precondition(backfilled?.first?["timeToReconnectMs"] as? Int64 == 2000)
        restarted.recordConnected("device")
        precondition(restarted.reconnectEvent("device") == nil)
        precondition(defaults.object(forKey: "ble_session_device") == nil)
        precondition(restarted.openSince("device") == 1000)
        defaults.set([["ts": 1]], forKey: "battery_history_device")
        defaults.set([["timestamp": 1]], forKey: "ble_diagnostics_disconnect_history_device")
        restarted.setPolicy(enabled: false, epoch: 8, retire: true)
        precondition(defaults.object(forKey: "battery_history_device") == nil)
        precondition(defaults.object(forKey: "ble_diagnostics_disconnect_history_device") == nil)
        precondition(defaults.object(forKey: "ble_audio_outage_device") == nil)
        precondition(!restarted.connectedBefore("device"))
        precondition(restarted.reconnectEvent("device") == nil)
        restarted.start("device", at: 16000)
        restarted.end("device", at: 17000)
        precondition(defaults.object(forKey: "ble_session_device") == nil)
        precondition(defaults.object(forKey: "ble_audio_outage_device") == nil)
        print("Device health store: 14 assertions passed")
    }
}
