import Foundation

/// "Record with… › Apple Watch": the iPhone asks the watch to start; the watch then opens the
/// recording as if it was started on the wrist (`startRecording` back, then its microphone audio).
public extension WatchStore {
    /// The watch app has reported in (battery or info) since launch.
    var isAvailable: Bool {
        battery != nil || info != nil
    }

    func startFromPhone() {
        link.send(.startRecording)
    }

    var isWatchPaired: Bool {
        link.isWatchPaired
    }

    var isWatchAppInstalled: Bool {
        link.isWatchAppInstalled
    }

    /// Asks the watch for its battery and details, so `isAvailable` can turn true.
    func ping() {
        link.send(.requestBattery)
        link.send(.requestWatchInfo)
    }
}
