import Foundation

#if os(iOS)
    @preconcurrency import AVFoundation
    import UIKit
#endif

/// What iOS does to a running capture. The OS owns the microphone, so every one of these is a change
/// the app did not ask for and has to answer: a recording never stops without the app knowing why.
public enum AudioSessionEvent: Equatable, Sendable {
    /// Something else took the microphone: a call, Siri, another recorder.
    case interrupted
    /// The interruption ended. `shouldResume` is iOS's permission to take the microphone back, which
    /// other apps' audio often omits, so a probe is worth trying either way.
    case interruptionEnded(shouldResume: Bool)
    /// The input route changed. `input` is the microphone in use now, nil when the session has none.
    case routeChanged(input: String?)
    /// The audio stack was torn down: every session and engine object is dead and must be rebuilt.
    case mediaServicesReset
    /// The app came back to the front, a chance to take a stopped capture's microphone back.
    case appBecameActive
}

/// The OS signals a capture has to answer. The store owns the policy; this only parses and forwards.
@MainActor
public protocol AudioSessionMonitoring: AnyObject {
    /// Starts delivering events on the main actor. Calling it twice is a no-op.
    func start(_ onEvent: @escaping @MainActor (AudioSessionEvent) -> Void)
    /// Stops delivering events and drops the handler.
    func stop()
}

/// `AVAudioSession` notifications. On macOS (`swift test`) there is no session, and the monitor
/// stays silent, which keeps the store testable with a fake.
@MainActor
public final class AVAudioSessionMonitor: AudioSessionMonitoring {
    private var handler: (@MainActor (AudioSessionEvent) -> Void)?
    private var tokens: [NSObjectProtocol] = []

    public init() {}

    public func start(_ onEvent: @escaping @MainActor (AudioSessionEvent) -> Void) {
        guard tokens.isEmpty else { return }
        handler = onEvent
        #if os(iOS)
            observe(AVAudioSession.interruptionNotification, Self.interruption)
            observe(AVAudioSession.routeChangeNotification, Self.route)
            observe(AVAudioSession.mediaServicesWereResetNotification) { _ in AudioSessionEvent.mediaServicesReset }
            observe(UIApplication.didBecomeActiveNotification) { _ in AudioSessionEvent.appBecameActive }
        #endif
    }

    public func stop() {
        for token in tokens { NotificationCenter.default.removeObserver(token) }
        tokens = []
        handler = nil
    }

    /// Notifications arrive on whichever thread posted them; the main queue keeps the store's state
    /// single-threaded.
    private func observe(_ name: Notification.Name, _ parse: @escaping @Sendable (Notification) -> AudioSessionEvent?) {
        let token = NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] note in
            guard let event = parse(note) else { return }
            MainActor.assumeIsolated { self?.handler?(event) }
        }
        tokens.append(token)
    }

    #if os(iOS)
        /// Only a route that moved between inputs changes what the tap listens to.
        nonisolated static let rebuildReasons: Set<AVAudioSession.RouteChangeReason> = [
            .newDeviceAvailable, .oldDeviceUnavailable, .override, .routeConfigurationChange,
        ]

        nonisolated static func interruption(_ note: Notification) -> AudioSessionEvent? {
            guard let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
                  let type = AVAudioSession.InterruptionType(rawValue: raw)
            else { return nil }
            switch type {
            case .began:
                return .interrupted
            case .ended:
                let rawOption = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
                let options = AVAudioSession.InterruptionOptions(rawValue: rawOption)
                return .interruptionEnded(shouldResume: options.contains(.shouldResume))
            @unknown default:
                return nil
            }
        }

        nonisolated static func route(_ note: Notification) -> AudioSessionEvent? {
            guard let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
                  let reason = AVAudioSession.RouteChangeReason(rawValue: raw), rebuildReasons.contains(reason)
            else { return nil }
            return .routeChanged(input: AVAudioSession.sharedInstance().currentRoute.inputs.first?.portName)
        }
    #endif
}
