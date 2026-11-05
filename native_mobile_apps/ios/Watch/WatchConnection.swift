import Foundation
import WatchConnectivity

/// The watch's end of WatchConnectivity. Live `sendMessage` while the iPhone is reachable (it
/// launches the Omi app in the background), otherwise `transferUserInfo`, which is queued and
/// delivered in order.
final class WatchConnection: NSObject, WCSessionDelegate, @unchecked Sendable {
    let messages: AsyncStream<WatchMessage>
    let phoneStates: AsyncStream<WatchPhoneState>
    private let messageSink: AsyncStream<WatchMessage>.Continuation
    private let stateSink: AsyncStream<WatchPhoneState>.Continuation
    private let session = WCSession.default
    private let lock = NSLock()
    /// Once one message of a recording had to be queued, the rest is queued too: a live message
    /// would overtake it, and the iPhone could see the stop before the last audio.
    private var queued = false

    override init() {
        (messages, messageSink) = AsyncStream.makeStream(of: WatchMessage.self)
        (phoneStates, stateSink) = AsyncStream.makeStream(of: WatchPhoneState.self, bufferingPolicy: .bufferingNewest(1))
        super.init()
    }

    func activate() {
        session.delegate = self
        session.activate()
    }

    /// A new recording may go live again.
    func beginRecording() {
        lock.withLock { queued = false }
    }

    func send(_ message: WatchMessage) {
        let live = lock.withLock {
            if !session.isReachable { queued = true }
            return !queued
        }
        guard live else {
            session.transferUserInfo(message.payload)
            return
        }
        session.sendMessage(message.payload, replyHandler: nil) { [weak self] _ in
            guard let self else { return }
            lock.withLock { queued = true }
            session.transferUserInfo(message.payload)
        }
    }

    private func receive(_ payload: [String: Any]) {
        if let state = WatchPhoneState(payload: payload) {
            stateSink.yield(state)
        } else if let message = WatchMessage(payload: payload) {
            messageSink.yield(message)
        }
    }

    // MARK: WCSessionDelegate (WatchConnectivity's own queue)

    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error _: (any Error)?) {
        guard state == .activated else { return }
        receive(session.receivedApplicationContext)
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

    func session(_: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        receive(applicationContext)
    }
}
