import Foundation
import Network
import Observation

/// Whether the phone has a connection (`NWPathMonitor`), for the chat's offline hint.
@MainActor
@Observable
public final class NetworkMonitor {
    public private(set) var isOffline = false
    private var monitor: NWPathMonitor?

    public init() {}

    public func start() {
        guard monitor == nil else { return }
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            let offline = path.status != .satisfied
            Task { @MainActor in self?.isOffline = offline }
        }
        monitor.start(queue: DispatchQueue(label: "omi.network-monitor"))
        self.monitor = monitor
    }

    /// A stopped monitor cannot restart; `start` makes a new one.
    public func stop() {
        monitor?.cancel()
        monitor = nil
    }
}
