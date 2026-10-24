import Foundation
import OmiExtras
import UIKit
import WidgetKit

/// Writes the widgets' snapshots to the App Group and reloads only the widgets whose snapshot
/// changed, coalesced: a burst of changes (a task list loading, the battery settling after
/// connect) costs one reload.
@MainActor
final class WidgetPublisher {
    private let store: SharedStore?
    /// What the battery widgets showed at their last reload; small moves are measured from it.
    private var reloadedDevice: DeviceSnapshot?
    private var pending: Set<WidgetKind> = []
    private var flush: Task<Void, Never>?
    static let coalescing: Duration = .seconds(2)

    init(store: SharedStore? = .shared) {
        self.store = store
        reloadedDevice = store?.read(DeviceSnapshot.self, for: .device)
    }

    func publish(device: DeviceSnapshot?) {
        guard let store, store.write(device, for: .device) else { return }
        // In front, reloads are free; in the background they come out of a daily budget.
        let foreground = UIApplication.shared.applicationState == .active
        guard foreground || device.map({ $0.needsReload(from: reloadedDevice) }) ?? true else { return }
        reloadedDevice = device
        reload(.battery)
    }

    func publish(upNext: UpNextSnapshot?) {
        guard let store, store.write(upNext, for: .upNext) else { return }
        reload(.upNext)
    }

    func publish(latest: LatestSnapshot?) {
        guard let store, store.write(latest, for: .latest) else { return }
        reload(.latest)
    }

    /// Signed out: the widgets show nothing of the account.
    func clear() {
        reloadedDevice = nil
        store?.clear().forEach(reload)
    }

    private func reload(_ kind: WidgetKind) {
        pending.insert(kind)
        guard flush == nil else { return }
        flush = Task { @MainActor [weak self] in
            try? await Task.sleep(for: Self.coalescing)
            guard let self else { return }
            for kind in pending {
                WidgetCenter.shared.reloadTimelines(ofKind: kind.rawValue)
            }
            pending = []
            flush = nil
        }
    }
}
