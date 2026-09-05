import Foundation
import Network

/// Whether this Mac currently has a usable network path.
///
/// Dictation must keep working with no wifi and no service. The model that
/// types is already on-device; only the *routing* decision ever needed the
/// network. Asking the path monitor up front is what keeps an offline turn
/// fast — the alternative is holding the key while the realtime hub waits out
/// its warm deadline, only to discover there was never a network to reach.
///
/// Started at launch (`applicationDidFinishLaunching`), so the first turn
/// already has a real answer. Deliberately optimistic before the first path
/// update: a turn taken in the first moments after launch must not be forced
/// on-device on no evidence. Being wrong that way is safe, because the
/// existing warm-deadline fallback still catches it.
@MainActor
final class NetworkReachability {

  static let shared = NetworkReachability()

  private let monitor = NWPathMonitor()
  private let queue = DispatchQueue(label: "com.omi.network-reachability")
  private var started = false
  private var online = true

  private init() {}

  /// True while a network path is satisfied. Also starts the monitor, for the
  /// callers (tests, early paths) that run before launch has.
  var isOnline: Bool {
    start()
    return online
  }

  /// Begins watching. Safe to call repeatedly; only the first call starts.
  func start() {
    guard !started else { return }
    started = true
    monitor.pathUpdateHandler = { path in
      let satisfied = path.status == .satisfied
      Task { @MainActor [weak self] in
        guard let self, self.online != satisfied else { return }
        self.online = satisfied
        log("NetworkReachability: network \(satisfied ? "available" : "unavailable")")
      }
    }
    monitor.start(queue: queue)
  }
}
