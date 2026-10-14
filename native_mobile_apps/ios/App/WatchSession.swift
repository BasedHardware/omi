import Foundation
import OmiService
import WatchConnectivity

/// `WatchLink` over `WCSession.default`. Activated at launch, so a recording started on the watch
/// (which can launch the app in the background) is heard. Messages go out live when the watch is
/// reachable and fall back to `transferUserInfo`, which WatchConnectivity queues and delivers in order.
final class WatchSession: NSObject, WatchLink, WCSessionDelegate, @unchecked Sendable {
    let messages: AsyncStream<WatchMessage>
    private let continuation: AsyncStream<WatchMessage>.Continuation
    /// Nil where WatchConnectivity is unsupported (iPad).
    private let session: WCSession?
    private let lock = NSLock()
    /// State set before activation finished; sent once it does.
    private var pendingState: WatchPhoneState?

    override init() {
        (messages, continuation) = AsyncStream.makeStream(of: WatchMessage.self)
        session = WCSession.isSupported() ? WCSession.default : nil
        super.init()
        session?.delegate = self
        session?.activate()
    }

    var isWatchPaired: Bool {
        guard let session, session.activationState == .activated else { return false }
        return session.isPaired
    }

    var isWatchAppInstalled: Bool {
        isWatchPaired && session?.isWatchAppInstalled == true
    }

    private var hasWatchApp: Bool {
        isWatchAppInstalled
    }

    func send(_ message: WatchMessage) {
        guard hasWatchApp, let session else { return }
        guard session.isReachable else {
            session.transferUserInfo(message.payload)
            return
        }
        session.sendMessage(message.payload, replyHandler: nil) { [weak self] _ in
            self?.session?.transferUserInfo(message.payload)
        }
    }

    func updateState(_ state: WatchPhoneState) {
        guard hasWatchApp, let session else {
            lock.withLock { pendingState = state }
            return
        }
        try? session.updateApplicationContext(state.payload)
    }

    private func receive(_ payload: [String: Any]) {
        guard let message = WatchMessage(payload: payload) else { return }
        continuation.yield(message)
    }

    // MARK: WCSessionDelegate (WatchConnectivity's own queue)

    func session(_: WCSession, activationDidCompleteWith state: WCSessionActivationState, error _: (any Error)?) {
        guard state == .activated, let pending = lock.withLock({ pendingState }) else { return }
        lock.withLock { pendingState = nil }
        updateState(pending)
    }

    func sessionDidBecomeInactive(_: WCSession) {}

    /// The user switched watches: activate again for the new one.
    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }

    /// The watch app was installed (or the paired watch changed): it gets the current state.
    func sessionWatchStateDidChange(_ session: WCSession) {
        guard session.isWatchAppInstalled, let pending = lock.withLock({ pendingState }) else { return }
        lock.withLock { pendingState = nil }
        updateState(pending)
    }

    func session(_: WCSession, didReceiveMessage message: [String: Any]) {
        receive(message)
    }

    func session(_: WCSession, didReceiveMessage message: [String: Any], replyHandler: @escaping ([String: Any]) -> Void) {
        receive(message)
        replyHandler([:])
    }

    func session(_: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        receive(userInfo)
    }
}
