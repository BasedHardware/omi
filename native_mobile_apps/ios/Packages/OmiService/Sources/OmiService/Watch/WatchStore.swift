import Foundation
import Observation

/// The iPhone's end of WatchConnectivity (real `WCSession` in the app, a fake in tests).
public protocol WatchLink: AnyObject, Sendable {
    /// Decoded messages from the watch, in arrival order.
    var messages: AsyncStream<WatchMessage> { get }
    func send(_ message: WatchMessage)
    /// Latest state only (application context): the watch reads it whenever it runs.
    func updateState(_ state: WatchPhoneState)
    /// An Apple Watch is paired with this iPhone (onboarding offers it as a recording source).
    var isWatchPaired: Bool { get }
    /// The Omi watch app is installed on it.
    var isWatchAppInstalled: Bool { get }
}

public extension WatchLink {
    var isWatchPaired: Bool {
        false
    }

    var isWatchAppInstalled: Bool {
        false
    }
}

/// The Apple Watch companion: a recording started on the watch streams its microphone through the
/// iPhone into `/v4/listen` (`source=apple_watch`), like the Flutter app's watch device. Messages
/// are handled one at a time, so audio that arrives while the conversation opens waits its turn.
@MainActor
@Observable
public final class WatchStore {
    /// The watch's own battery, 0–100, as it last reported it.
    public private(set) var battery: Int?
    public private(set) var info: WatchInfo?
    /// The watch's answer to `requestMicrophone()`: nil until it gave one.
    public private(set) var microphoneGranted: Bool?
    /// Asked the watch for its microphone and waiting for the answer.
    public private(set) var isRequestingMicrophone = false

    let link: any WatchLink
    private let capture: CaptureStore
    private let isSignedIn: () -> Bool?
    private let omiBattery: () -> Int?
    private let signInWait: Duration
    @ObservationIgnored private var loop: Task<Void, Never>?
    @ObservationIgnored private var microphoneWait: Task<Void, Never>?
    @ObservationIgnored private var lastState: WatchPhoneState?
    /// The watch asked to stop: no need to tell it back.
    @ObservationIgnored private var stoppingFromWatch = false

    /// - Parameters:
    ///   - isSignedIn: ready for capture; nil while the session is still restoring.
    ///   - signInWait: how long a recording started from the watch waits for the session to restore
    ///     (the watch can launch the iPhone app in the background).
    public init(
        link: any WatchLink,
        capture: CaptureStore,
        isSignedIn: @escaping () -> Bool?,
        omiBattery: @escaping () -> Int?,
        signInWait: Duration = .seconds(10)
    ) {
        self.link = link
        self.capture = capture
        self.isSignedIn = isSignedIn
        self.omiBattery = omiBattery
        self.signInWait = signInWait
    }

    /// Starts handling watch messages and mirroring the iPhone's state to the watch.
    public func start() {
        guard loop == nil else { return }
        capture.onWatchCaptureEnded = { [weak self] in self?.captureEnded() }
        let messages = link.messages
        loop = Task { [weak self] in
            for await message in messages {
                await self?.handle(message)
            }
        }
        publishState()
    }

    /// The Apple Watch permission page (Flutter `apple_watch_permission_page`): the watch asks for
    /// its microphone and answers with `microphonePermissionResult`.
    /// A watch that is not reachable never answers: the wait ends after `answerWait`.
    public func requestMicrophone(answerWait: Duration = .seconds(20)) {
        isRequestingMicrophone = true
        link.send(.requestMicrophonePermission)
        microphoneWait?.cancel()
        microphoneWait = Task { [weak self] in
            try? await Task.sleep(for: answerWait)
            guard !Task.isCancelled else { return }
            self?.isRequestingMicrophone = false
        }
    }

    func handle(_ message: WatchMessage) async {
        switch message {
        case .startRecording:
            await watchStarted()
        case .stopRecording:
            guard capture.source == .watch, capture.isLive else { return }
            stoppingFromWatch = true
            await capture.stop()
            stoppingFromWatch = false
        case let .audioChunk(chunk):
            // Like Flutter: audio outside a watch recording (e.g. queued from before a relaunch) is dropped.
            guard !chunk.data.isEmpty else { return }
            capture.ingestWatchAudio(chunk.data)
        case let .batteryUpdate(level, _):
            battery = max(0, min(100, Int(level.rounded())))
        case let .watchInfoUpdate(info):
            self.info = info
        case let .microphonePermissionResult(granted):
            microphoneGranted = granted
            isRequestingMicrophone = false
            microphoneWait?.cancel()
        case .recordingError, .requestMicrophonePermission, .requestBattery, .requestWatchInfo:
            break
        }
    }

    private func watchStarted() async {
        if capture.isLive {
            if capture.source != .watch { link.send(.stopRecording(reason: .busy)) }
            return
        }
        guard await waitForSignIn() else {
            link.send(.stopRecording(reason: .signedOut))
            return
        }
        await capture.startWatch()
        if !(capture.source == .watch && capture.isLive) {
            link.send(.stopRecording(reason: .failed))
        }
    }

    private func waitForSignIn() async -> Bool {
        let deadline = ContinuousClock.now + signInWait
        while true {
            if let signedIn = isSignedIn() { return signedIn }
            guard ContinuousClock.now < deadline else { return false }
            try? await Task.sleep(for: .milliseconds(50))
        }
    }

    /// A watch recording ended on the iPhone (Stop in the app): the watch stops its microphone.
    private func captureEnded() {
        guard !stoppingFromWatch else { return }
        link.send(.stopRecording(reason: nil))
    }

    /// Sends the iPhone's capture state and the Omi battery whenever either changes.
    private func publishState() {
        let state = withObservationTracking {
            WatchPhoneState(capture: Self.captureState(capture), omiBattery: omiBattery())
        } onChange: { [weak self] in
            Task { @MainActor in self?.publishState() }
        }
        guard state != lastState else { return }
        lastState = state
        link.updateState(state)
    }

    static func captureState(_ capture: CaptureStore) -> WatchPhoneState.Capture {
        guard capture.isLive else { return .idle }
        switch capture.source {
        case .watch: return .watch
        case .device: return .omi
        case .phone, nil: return .phone
        }
    }
}
