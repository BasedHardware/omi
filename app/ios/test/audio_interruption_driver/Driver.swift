import UIKit
import AVFoundation
import CallKit

// A separate process requests real OS audio ownership; only the microphone
// trace can prove an interruption occurred. No network or audio retention.
final class Driver: UIViewController {
    private var player: AVAudioPlayer?
    private var engine: AVAudioEngine?
    private var events: [[String: Any]] = []
    private var began = Date()
    private let runID = UUID().uuidString
    private var started = ProcessInfo.processInfo.systemUptime
    private let label = UILabel()
    private var build: [String: Any] = [:]
    private var callProvider: CXProvider?
    private let callController = CXCallController()
    private var callID: UUID?
    private var callStartRequested = false
    private var providerReady = false
    private var callActivated = false
    private var callEnded = false
    private var callDeactivated = false
    private var terminal = false
    private var cleanupTask: DispatchWorkItem?
    private var backgroundTask = UIBackgroundTaskIdentifier.invalid
    private var mode = "playback"

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        label.text = "Preparing audio interruption…"
        label.numberOfLines = 0
        label.textAlignment = .center
        label.frame = view.bounds.insetBy(dx: 20, dy: 100)
        label.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(label)
        if let url = Bundle.main.url(forResource: "build", withExtension: "json"),
           let data = try? Data(contentsOf: url),
           let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { build = value }
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard events.isEmpty else { return }
        began = Date()
        started = ProcessInfo.processInfo.systemUptime
        let args = Array(CommandLine.arguments.dropFirst())
        guard args.isEmpty || args == ["--capture"] || args == ["--local-call"] else {
            record("invalid_arguments"); record("completed"); return
        }
        mode = args == ["--local-call"] ? "local-call" : args == ["--capture"] ? "capture" : "playback"
        record("scene_active")
        if mode == "local-call" { beginLocalCall(); return }
        if mode == "capture" {
            AVAudioSession.sharedInstance().requestRecordPermission { [weak self] granted in
                DispatchQueue.main.async {
                    guard let self else { return }
                    guard granted else {
                        self.record("permission_denied")
                        self.label.text = "Microphone permission is required for competing capture."
                        self.record("completed")
                        return
                    }
                    self.beginCapture()
                }
            }
            return
        }
        beginPlayback()
    }

    private func beginLocalCall() {
        // A generic, synthetic handle cannot dial a phone number. There is no
        // SIP stack, PushKit, socket, contact lookup, or external participant.
        guard !callController.callObserver.calls.contains(where: { !$0.hasEnded }) else {
            record("existing_call_refused"); record("completed")
            label.text = "A call is already active. No local test started."
            return
        }
        guard AVAudioSession.sharedInstance().recordPermission == .granted else {
            record("permission_denied"); record("completed")
            label.text = "Local CallKit test requires this helper's microphone grant."
            return
        }
        label.text = "Omi Local Test\nLocal CallKit audio only. No external call."
        backgroundTask = UIApplication.shared.beginBackgroundTask { [weak self] in
            self?.abortLocalCall("background_time_expired")
        }
        let config = CXProviderConfiguration(localizedName: "Omi Local Test")
        config.includesCallsInRecents = false
        config.supportsVideo = false
        config.maximumCallGroups = 1
        config.maximumCallsPerCallGroup = 1
        config.supportedHandleTypes = [.generic]
        let provider = CXProvider(configuration: config)
        callProvider = provider
        callID = UUID()
        let deadline = DispatchWorkItem { [weak self] in self?.abortLocalCall("local_call_deadline") }
        cleanupTask = deadline
        DispatchQueue.main.asyncAfter(deadline: .now() + 10, execute: deadline)
        record("provider_configured", extra: ["maximum_call_groups": config.maximumCallGroups,
                                              "maximum_calls_per_group": config.maximumCallsPerCallGroup,
                                              "supports_generic_handle": config.supportedHandleTypes.contains(.generic)])
        // A freshly constructed provider is not yet registered with CallKit.
        // providerDidBegin is the SDK's readiness boundary for sending actions.
        provider.setDelegate(self, queue: .main)
    }

    private func requestLocalCallStart() {
        guard !terminal, providerReady, !callStartRequested, let callID else { return }
        let activeCalls = callController.callObserver.calls.filter { !$0.hasEnded }.count
        record("pre_start_call_inventory", extra: ["active_call_count": activeCalls])
        guard activeCalls == 0 else { abortLocalCall("existing_call_refused"); return }
        callStartRequested = true
        let action = CXStartCallAction(call: callID, handle: CXHandle(type: .generic, value: "omi-local-test"))
        action.isVideo = false
        record("local_call_start_requested")
        callController.request(CXTransaction(action: action)) { [weak self] error in
            DispatchQueue.main.async {
                guard let self, !self.terminal else { return }
                if let error { self.abortLocalCall("start_transaction_failed", error: error) }
                else { self.record("start_transaction_accepted") }
            }
        }
    }

    private func requestLocalCallEnd() {
        guard !terminal, let callID, !callEnded else { return }
        record("local_call_end_requested")
        callController.request(CXTransaction(action: CXEndCallAction(call: callID))) { [weak self] error in
            DispatchQueue.main.async {
                guard let self, !self.terminal else { return }
                if let error { self.abortLocalCall("end_transaction_failed", error: error) }
                else { self.record("end_transaction_accepted") }
            }
        }
    }

    private func completeLocalCallIfReady() {
        guard !terminal, callEnded, callDeactivated else { return }
        terminal = true
        cleanupTask?.cancel(); cleanupTask = nil
        record("completed")
        label.text = "Omi Local Test ended.\nCallKit released audio; check the microphone trace."
        callProvider?.invalidate(); callProvider = nil
        endBackgroundTask()
    }

    private func abortLocalCall(_ reason: String, error: Error? = nil) {
        guard !terminal else { return }
        terminal = true
        cleanupTask?.cancel(); cleanupTask = nil
        record(reason, extra: error.map { ["error_code": ($0 as NSError).code,
                                          "error_domain": ($0 as NSError).domain] } ?? [:])
        // Report only our own UUID ended, then invalidate our own provider.
        // This also clears a call whose transaction/delegate never completed.
        if let callID { callProvider?.reportCall(with: callID, endedAt: Date(), reason: .failed) }
        callProvider?.invalidate(); callProvider = nil
        record("local_call_cleanup_requested")
        record("completed")
        label.text = "Local test stopped without qualification.\nCheck driver and microphone receipts."
        endBackgroundTask()
    }

    private func endBackgroundTask() {
        if backgroundTask != .invalid {
            UIApplication.shared.endBackgroundTask(backgroundTask)
            backgroundTask = .invalid
        }
    }

    private func beginCapture() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .default, options: [])
            try session.setActive(true)
            record("capture_session_active")
            let engine = AVAudioEngine()
            // Real competing microphone ownership, with no samples retained.
            engine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: nil) { _, _ in }
            self.engine = engine
            try engine.start()
            record("capture_started")
            label.text = "Competing microphone capture for five seconds…"
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in self?.finish() }
        } catch {
            record("capture_failed", extra: ["error_code": (error as NSError).code, "error_domain": (error as NSError).domain])
            finish()
        }
    }

    private func beginPlayback() {
        do {
            // Eight seconds of PCM silence avoids calls, speech, and a second
            // microphone permission prompt. Activation is deliberately exclusive.
            let rate: UInt32 = 16000
            let byteCount: UInt32 = rate * 2 * 8
            var wav = Data()
            func ascii(_ s: String) { wav.append(s.data(using: .ascii)!) }
            func u32(_ v: UInt32) { var n = v.littleEndian; withUnsafeBytes(of: &n) { wav.append(contentsOf: $0) } }
            func u16(_ v: UInt16) { var n = v.littleEndian; withUnsafeBytes(of: &n) { wav.append(contentsOf: $0) } }
            ascii("RIFF"); u32(36 + byteCount); ascii("WAVEfmt "); u32(16)
            u16(1); u16(1); u32(rate); u32(rate * 2); u16(2); u16(16)
            ascii("data"); u32(byteCount); wav.append(Data(count: Int(byteCount)))
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [])
            try session.setActive(true)
            record("session_active")
            player = try AVAudioPlayer(data: wav)
            guard player!.play() else { throw NSError(domain: "Driver", code: 1) }
            label.text = "Holding test audio for five seconds…"
            record("playback_started")
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in self?.finish() }
        } catch {
            record("failed", extra: ["error_code": (error as NSError).code, "error_domain": (error as NSError).domain])
            finish()
        }
    }

    private func finish() {
        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        engine = nil
        player?.stop()
        player = nil
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            record("session_deactivated")
        } catch { record("deactivation_failed", extra: ["error_code": (error as NSError).code, "error_domain": (error as NSError).domain]) }
        label.text = "Audio stimulus ended. Check the separate microphone trace."
        record("completed")
    }

    private func record(_ kind: String, extra: [String: Any] = [:]) {
        var event = extra
        event["kind"] = kind
        event["elapsed_ms"] = Int((ProcessInfo.processInfo.systemUptime - started) * 1000)
        events.append(event)
        let payload: [String: Any] = ["schema": "omi-audio-interruption-driver/v1",
            "audio_retained": false, "build": build, "events": events,
            "mode": mode, "run_id": runID, "started_at": ISO8601DateFormatter().string(from: began),
            "external_call": false, "includes_calls_in_recents": false]
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("interruption.json")
        if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: url, options: .atomic)
        }
    }
}

extension Driver: CXProviderDelegate {
    func providerDidBegin(_ provider: CXProvider) {
        guard !terminal, provider === callProvider else { return }
        guard !providerReady else { abortLocalCall("duplicate_provider_ready"); return }
        providerReady = true
        record("provider_ready", extra: ["maximum_call_groups": provider.configuration.maximumCallGroups,
                                          "maximum_calls_per_group": provider.configuration.maximumCallsPerCallGroup,
                                          "supports_generic_handle": provider.configuration.supportedHandleTypes.contains(.generic)])
        requestLocalCallStart()
    }

    func providerDidReset(_ provider: CXProvider) {
        guard !terminal else { return }
        abortLocalCall("provider_reset")
    }

    func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        guard !terminal, action.callUUID == callID else { action.fail(); return }
        record("local_call_start_action")
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .voiceChat, options: [])
            // CallKit owns activation. Never call setActive(true) here.
            record("local_call_audio_configured")
            let update = CXCallUpdate()
            update.localizedCallerName = "Omi Local Test"
            update.remoteHandle = CXHandle(type: .generic, value: "omi-local-test")
            update.hasVideo = false
            update.supportsHolding = false; update.supportsGrouping = false; update.supportsUngrouping = false
            update.supportsDTMF = false
            provider.reportCall(with: action.callUUID, updated: update)
            action.fulfill()
            provider.reportOutgoingCall(with: action.callUUID, startedConnectingAt: Date())
            provider.reportOutgoingCall(with: action.callUUID, connectedAt: Date())
            record("local_call_connected_reported")
        } catch {
            action.fail()
            abortLocalCall("local_call_configuration_failed", error: error)
        }
    }

    func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        guard !terminal else { return }
        guard !callActivated else { abortLocalCall("duplicate_audio_activation"); return }
        callActivated = true
        record("callkit_audio_activated")
        // No tap or audio engine: CallKit audio ownership itself is the stimulus.
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) { [weak self] in self?.requestLocalCallEnd() }
    }

    func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        guard !terminal, action.callUUID == callID else { action.fail(); return }
        record("local_call_end_action")
        callEnded = true
        action.fulfill()
        record("local_call_end_fulfilled")
        completeLocalCallIfReady()
    }

    func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        guard !terminal else { return }
        callDeactivated = true
        record("callkit_audio_deactivated")
        completeLocalCallIfReady()
    }

    func provider(_ provider: CXProvider, timedOutPerforming action: CXAction) {
        action.fail()
        abortLocalCall("callkit_action_timed_out")
    }
}

final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        window = UIWindow(windowScene: scene)
        window?.rootViewController = Driver()
        window?.makeKeyAndVisible()
    }
}

@main final class AppDelegate: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, configurationForConnecting session: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Default", sessionRole: session.role)
        configuration.delegateClass = SceneDelegate.self
        return configuration
    }
}
