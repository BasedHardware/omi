import AVFoundation
import CallKit
import UIKit

/// Observes every OS signal relevant to capture and forwards parsed, typed
/// events to the controller on its control queue. Parse-and-forward only — no
/// recovery policy lives here.
///
/// startObserving()/stopObserving()/bindEngine() must be called on the control
/// queue; `observing` and `hadActiveCall` are confined to it (the CXCallObserver
/// delegate queue is the control queue too).
final class PhoneMicInterruptionMonitor: NSObject, CXCallObserverDelegate {
    enum Event {
        case interruptionBegan
        /// shouldResume is true only when the interruption-options key was
        /// present AND its shouldResume bit was set — resuming without the OS's
        /// sanction just re-breaks the session.
        case interruptionEnded(shouldResume: Bool)
        case routeChanged(reason: AVAudioSession.RouteChangeReason)
        case engineConfigChanged
        case mediaServicesReset
        /// From CXCallObserver: covers the declined-call case where the
        /// interruption .ended notification is never delivered (issue #6499).
        case allCallsEnded
        case appBecameActive
    }

    /// Route-change reasons that require re-installing the tap: a device
    /// appeared/disappeared, the route was overridden, or its configuration
    /// changed underneath the engine.
    static let rebuildReasons: Set<AVAudioSession.RouteChangeReason> = [
        .newDeviceAvailable, .oldDeviceUnavailable, .override, .routeConfigurationChange,
    ]

    private let controlQueue: DispatchQueue
    private let onEvent: (Event) -> Void
    private let callObserver = CXCallObserver()
    private var observing = false
    private var hadActiveCall = false
    private var engineToken: NSObjectProtocol?

    init(controlQueue: DispatchQueue, onEvent: @escaping (Event) -> Void) {
        self.controlQueue = controlQueue
        self.onEvent = onEvent
        super.init()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        if let token = engineToken {
            NotificationCenter.default.removeObserver(token)
        }
    }

    func startObserving() {
        guard !observing else { return }
        observing = true
        let center = NotificationCenter.default
        center.addObserver(
            self, selector: #selector(handleInterruption(_:)),
            name: AVAudioSession.interruptionNotification, object: nil)
        center.addObserver(
            self, selector: #selector(handleRouteChange(_:)),
            name: AVAudioSession.routeChangeNotification, object: nil)
        center.addObserver(
            self, selector: #selector(handleMediaServicesReset(_:)),
            name: AVAudioSession.mediaServicesWereResetNotification, object: nil)
        center.addObserver(
            self, selector: #selector(handleAppBecameActive(_:)),
            name: UIApplication.didBecomeActiveNotification, object: nil)
        hadActiveCall = false
        callObserver.setDelegate(self, queue: controlQueue)
    }

    func stopObserving() {
        guard observing else { return }
        observing = false
        NotificationCenter.default.removeObserver(self)
        unbindEngine()
        callObserver.setDelegate(nil, queue: nil)
    }

    /// The config-change observer is engine-object-specific; re-bind whenever
    /// the controller brings up a fresh engine.
    func bindEngine(_ engine: AVAudioEngine) {
        unbindEngine()
        engineToken = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil
        ) { [weak self] _ in
            self?.forward(.engineConfigChanged)
        }
    }

    private func unbindEngine() {
        if let token = engineToken {
            NotificationCenter.default.removeObserver(token)
            engineToken = nil
        }
    }

    // MARK: - CXCallObserverDelegate (delivered on controlQueue)

    func callObserver(_ callObserver: CXCallObserver, callChanged call: CXCall) {
        guard observing else { return }
        let hasActive = callObserver.calls.contains { !$0.hasEnded }
        if hasActive {
            hadActiveCall = true
        } else if hadActiveCall {
            hadActiveCall = false
            onEvent(.allCallsEnded)
        }
    }

    // MARK: - Notification handlers (posting thread; parse then hop)

    @objc private func handleInterruption(_ notification: Notification) {
        guard
            let info = notification.userInfo,
            let typeValue = info[AVAudioSessionInterruptionTypeKey] as? UInt,
            let type = AVAudioSession.InterruptionType(rawValue: typeValue)
        else { return }
        switch type {
        case .began:
            forward(.interruptionBegan)
        case .ended:
            let rawOption = info[AVAudioSessionInterruptionOptionKey] as? UInt
            let shouldResume =
                rawOption.map { AVAudioSession.InterruptionOptions(rawValue: $0).contains(.shouldResume) } ?? false
            forward(.interruptionEnded(shouldResume: shouldResume))
        @unknown default:
            break
        }
    }

    @objc private func handleRouteChange(_ notification: Notification) {
        guard
            let reasonValue = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
            let reason = AVAudioSession.RouteChangeReason(rawValue: reasonValue),
            Self.rebuildReasons.contains(reason)
        else { return }
        forward(.routeChanged(reason: reason))
    }

    @objc private func handleMediaServicesReset(_ notification: Notification) {
        forward(.mediaServicesReset)
    }

    @objc private func handleAppBecameActive(_ notification: Notification) {
        forward(.appBecameActive)
    }

    private func forward(_ event: Event) {
        controlQueue.async { [weak self] in
            guard let self, self.observing else { return }
            self.onEvent(event)
        }
    }
}
