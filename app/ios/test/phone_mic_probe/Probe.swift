import AVFoundation
import UIKit
import Darwin

// Explicit launch controls for an already-authorized local device session.
// Invalid arguments fail closed; no system permissions/settings are changed.
struct ProbeRunOptions {
    let mode: String?
    let duration: Double
    static func parse() -> ProbeRunOptions? {
        let args = Array(CommandLine.arguments.dropFirst())
        var mode: String?; var duration = 60.0
        var i = 0
        while i < args.count {
            guard i + 1 < args.count else { return nil }
            switch args[i] {
            case "--probe-mode":
                guard ["mic", "wearable"].contains(args[i + 1]) else { return nil }
                mode = args[i + 1]
            case "--probe-duration":
                guard let n = Double(args[i + 1]), n.isFinite, (10...300).contains(n) else { return nil }
                duration = n
            default: return nil
            }
            i += 2
        }
        return ProbeRunOptions(mode: mode, duration: duration)
    }
}

// Process measurements include probe instrumentation overhead. CPU is total
// user+system seconds; resident memory is a sample, not peak or battery usage.
func probeResources() -> [String: Any] {
    var result = [String: Any]()
    var usage = rusage()
    if getrusage(RUSAGE_SELF, &usage) == 0 {
        result["cpu_seconds"] = Double(usage.ru_utime.tv_sec + usage.ru_stime.tv_sec)
            + Double(usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) / 1_000_000
    }
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / MemoryLayout<natural_t>.size)
    let status = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
        }
    }
    if status == KERN_SUCCESS { result["resident_bytes"] = info.resident_size }
    return result
}

// Native stream-capture qualification only. No Flutter, network, account,
// batch writer, or audio retention. Production controller/engine/monitor run
// unchanged; the sink counts and immediately discards PCM bytes.
extension PhoneMicCaptureEngine: PhoneMicEngineControlling {
    var audioEngineForMonitor: AVAudioEngine? { engine }
}
extension PhoneMicInterruptionMonitor: PhoneMicInterruptionSource {
    func bindEngine(_ engine: AVAudioEngine?) {
        if let engine { bindEngine(engine) }
    }
}
final class ProbePermission: PhoneMicPermissionChecking {
    func current() -> PhoneMicPermissionStatus {
        switch PhoneMicPermissionGate.current() {
        case .granted: return .granted
        case .denied: return .denied
        case .undetermined: return .undetermined
        }
    }
    func request(_ completion: @escaping (Bool) -> Void) {
        PhoneMicPermissionGate.request(completion)
    }
}

final class Probe: NSObject, PhoneMicEventSink {
    var update: ((String) -> Void)?
    private var controller: PhoneMicController!
    private var events = [[String: Any]]()
    private var began = Date()
    private var origin = ProcessInfo.processInfo.systemUptime
    private var frames = 0
    private var bytes = 0
    private var energySum = 0.0
    private var pcmSamples = 0
    private var peak = 0
    private var duration = 60.0
    private var previousIdleTimerDisabled = false
    private var lastFrameAt: Double?
    private var maxFrameGapMS = 0.0
    private var intervalFrameGapMS = 0.0
    var isBusy: Bool { active || observingStop }
    private var active = false
    private var observingStop = false
    private var stopCompleted = false
    private var timer: Timer?
    private var runID = ""
    private var sessionID: Int64 = 0
    private var receiptURL: URL!
    private var backgroundTask = UIBackgroundTaskIdentifier.invalid

    override init() {
        super.init()
        controller = PhoneMicController(environment: PhoneMicControllerEnvironment(
            sink: self, permission: ProbePermission(),
            configureSession: { try PhoneMicSessionConfigurator.configureAndActivate() },
            describeRoute: { "probe-redacted-route" },
            makeMonitor: { [weak self] queue, signal in
                PhoneMicInterruptionMonitor(controlQueue: queue) { event in
                    let value: PhoneMicInterruptionSignal
                    var fields = [String: Any]()
                    let name: String
                    switch event {
                    case .interruptionBegan: name = "interruptionBegan"; value = .interruptionBegan
                    case .interruptionEnded(let resume):
                        name = "interruptionEnded"; fields["should_resume"] = resume
                        value = .interruptionEnded(shouldResume: resume)
                    case .routeChanged(let reason):
                        name = "routeChanged"; fields["reason"] = Int(reason.rawValue)
                        value = .routeChanged(reasonDescription: "\(reason.rawValue)")
                    case .engineConfigChanged: name = "engineConfigChanged"; value = .engineConfigChanged
                    case .mediaServicesReset: name = "mediaServicesReset"; value = .mediaServicesReset
                    case .allCallsEnded: name = "allCallsEnded"; value = .allCallsEnded
                    case .appBecameActive: name = "appBecameActive"; value = .appBecameActive
                    }
                    fields["signal"] = name
                    let recordedFields = fields
                    DispatchQueue.main.async { self?.record("os_signal", recordedFields) }
                    signal(value)
                }
            },
            makeEngine: { queue, data, error in
                PhoneMicCaptureEngine(audioQueue: queue, onConvertedData: data, onConvertError: error)
            },
            batchDirectory: { nil }, batchAutoMarker: { false }, makeEncoder: { nil },
            makeWriter: { _, _ in fatalError("This probe supports stream mode only") }
        ))
        for name in [UIApplication.didEnterBackgroundNotification,
                     UIApplication.willEnterForegroundNotification,
                     UIApplication.didBecomeActiveNotification,
                     UIApplication.willResignActiveNotification] {
            NotificationCenter.default.addObserver(self, selector: #selector(lifecycle(_:)), name: name, object: nil)
        }
    }

    @objc private func lifecycle(_ notification: Notification) {
        guard active || observingStop else { return }
        record("app_lifecycle", ["notification": notification.name.rawValue])
    }

    func start(duration: Double = 60) {
        guard !active && !observingStop else { return }
        self.duration = duration
        previousIdleTimerDisabled = UIApplication.shared.isIdleTimerDisabled
        if duration >= 300 { UIApplication.shared.isIdleTimerDisabled = true }
        lastFrameAt = nil; maxFrameGapMS = 0; intervalFrameGapMS = 0
        began = Date(); origin = ProcessInfo.processInfo.systemUptime
        frames = 0; bytes = 0; energySum = 0; pcmSamples = 0; peak = 0
        events = []; active = true; stopCompleted = false
        runID = UUID().uuidString
        sessionID += 1
        receiptURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("probe-\(runID).json")
        record("start_requested", ["permission": String(describing: ProbePermission().current())])
        controller.start(mode: .stream, sessionId: sessionID) { [weak self] result in
            guard let self else { return }
            switch result {
            case .success:
                self.record("start_completed", ["permission": String(describing: ProbePermission().current())])
                self.timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                    guard let self else { return }
                    self.record("sample", probeResources())
                    self.intervalFrameGapMS = 0
                    self.update?("Capturing · \(Int(ProcessInfo.processInfo.systemUptime - self.origin))s\n\(self.frames) frames · audio discarded\n\nLock the screen for 15 seconds, then return.\nCapture stops automatically after \(Int(self.duration)) seconds.")
                    if ProcessInfo.processInfo.systemUptime - self.origin >= self.duration { self.stop() }
                }
            case .failure(let error):
                self.record("start_failed", ["permission": String(describing: ProbePermission().current()),
                                            "code": (error as? PhoneMicPigeonError)?.code ?? "unknown"])
                self.stop()
            }
        }
    }

    func stop() {
        guard active else { return }
        active = false; observingStop = true
        UIApplication.shared.isIdleTimerDisabled = previousIdleTimerDisabled
        timer?.invalidate(); timer = nil
        backgroundTask = UIApplication.shared.beginBackgroundTask { [weak self] in
            self?.record("observation_expired")
            self?.finishBackgroundTask()
        }
        record("stop_requested")
        controller.stop { [weak self] in
            guard let self else { return }
            self.stopCompleted = true
            self.record("stop_completed")
            self.update?("Stopped. Checking for late frames…")
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                self.record("observation_completed")
                self.observingStop = false
                self.update?("Run saved\n\(self.frames) frames counted; no audio saved.\n\nReady for another 60-second run.")
                self.finishBackgroundTask()
            }
        }
    }

    private func finishBackgroundTask() {
        if backgroundTask != .invalid {
            UIApplication.shared.endBackgroundTask(backgroundTask)
            backgroundTask = .invalid
        }
    }

    private func record(_ kind: String, _ fields: [String: Any] = [:]) {
        guard receiptURL != nil else { return }
        var event = fields
        event["kind"] = kind
        event["elapsed_ms"] = Int((ProcessInfo.processInfo.systemUptime - origin) * 1000)
        event["frames"] = frames; event["bytes"] = bytes
        event["pcm_samples"] = pcmSamples; event["pcm_square_sum"] = energySum; event["pcm_peak"] = peak
        event["app_state"] = UIApplication.shared.applicationState == .background ? "background" :
            UIApplication.shared.applicationState == .active ? "active" : "inactive"
        event["max_frame_gap_ms"] = maxFrameGapMS
        event["interval_frame_gap_ms"] = intervalFrameGapMS
        events.append(event)
        let build = (try? Data(contentsOf: Bundle.main.url(forResource: "build", withExtension: "json")!))
            .flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? [:]
        let receipt: [String: Any] = [
            "schema": "phone-mic-device-probe/v1", "run_id": runID,
            "started_at": ISO8601DateFormatter().string(from: began),
            "os_version": UIDevice.current.systemVersion, "build": build,
            "session_id": sessionID, "events": events, "requested_duration_seconds": duration,
            "prevents_automatic_lock": duration >= 300,
            "scope": "native-stream-only", "audio_retained": false,
        ]
        do {
            let data = try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys])
            try data.write(to: receiptURL, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
        } catch { update?("Evidence write failed. This run cannot qualify.") }
    }

    func onAudioFrame(pcm16leMono16k: Data, sessionId: Int64) {
        let now = ProcessInfo.processInfo.systemUptime
        if let lastFrameAt {
            let gap = (now - lastFrameAt) * 1000
            maxFrameGapMS = max(maxFrameGapMS, gap); intervalFrameGapMS = max(intervalFrameGapMS, gap)
        }
        lastFrameAt = now
        frames += 1; bytes += pcm16leMono16k.count
        pcm16leMono16k.withUnsafeBytes { raw in
            for offset in stride(from: 0, to: raw.count - 1, by: 2) {
                let sample = Int(Int16(littleEndian: raw.loadUnaligned(fromByteOffset: offset, as: Int16.self)))
                pcmSamples += 1; energySum += Double(sample) * Double(sample); peak = max(peak, abs(sample))
            }
        }
        if sessionId != sessionID { record("wrong_session") }
        if stopCompleted { record("late_frame") }
    }
    func onStateChanged(state: PhoneMicCaptureState, sessionId: Int64) {
        record("state", ["state": String(describing: state), "session_id": sessionId])
    }
    func onCaptureError(code: String, message: String, sessionId: Int64) {
        // Intentionally discard free-form error text: it can contain device names/paths.
        record("capture_error", ["code": code, "session_id": sessionId])
    }
    func onBatchProgress(capturedSeconds: Double, sessionId: Int64) {
        record("unexpected_batch_progress")
    }
}

final class ProbeViewController: UIViewController {
    let probe = Probe()
    let status = UILabel()
    private var didAutoStart = false
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        let title = UILabel(); title.text = "Omi Mic Probe"; title.font = .preferredFont(forTextStyle: .largeTitle)
        status.text = "Tests Omi’s native microphone lifecycle.\nAudio is counted and discarded. Nothing is uploaded.\n\nStart a run, allow microphone access, then lock the screen for 15 seconds and return."
        status.numberOfLines = 0; status.font = .preferredFont(forTextStyle: .body)
        let start = UIButton(type: .system); start.setTitle("Start 60-second run", for: .normal)
        start.addTarget(self, action: #selector(startRun), for: .touchUpInside)
        let wearable = UIButton(type: .system); wearable.setTitle("Start wearable reconnect test", for: .normal)
        wearable.addTarget(self, action: #selector(startWearable), for: .touchUpInside)
        let stop = UIButton(type: .system); stop.setTitle("Stop now", for: .normal)
        stop.addTarget(self, action: #selector(stopRun), for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [title, status, start, stop, wearable]); stack.axis = .vertical; stack.spacing = 28
        stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 40),
        ])
        probe.update = { [weak self] message in self?.status.text = message }
    }
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        guard !didAutoStart else { return }; didAutoStart = true
        if Array(CommandLine.arguments.dropFirst()) == ["--probe-open-settings"] {
            UIApplication.shared.open(URL(string: UIApplication.openSettingsURLString)!)
            return
        }
        guard let options = ProbeRunOptions.parse() else {
            status.text = "Invalid probe launch arguments. No test started."; return
        }
        if options.mode == "mic" { probe.start(duration: options.duration) }
        if options.mode == "wearable" { showWearable(duration: options.duration) }
    }
    private func showWearable(duration: Double) {
        guard !probe.isBusy else { status.text = "Stop the microphone run before starting a wearable test."; return }
        let controller = WearableViewController(); controller.duration = duration
        controller.modalPresentationStyle = .fullScreen
        present(controller, animated: true)
    }
    @objc private func startWearable() {
        showWearable(duration: 90)
    }
    @objc private func startRun() { probe.start() }
    @objc private func stopRun() { probe.stop() }
}

@main
final class ProbeApp: UIResponder, UIApplicationDelegate {
    func application(_ application: UIApplication, configurationForConnecting session: UISceneSession,
                     options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Probe", sessionRole: session.role)
        configuration.delegateClass = ProbeSceneDelegate.self
        return configuration
    }
}

final class ProbeSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let scene = scene as? UIWindowScene else { return }
        window = UIWindow(windowScene: scene)
        window?.rootViewController = ProbeViewController()
        window?.makeKeyAndVisible()
    }

    func sceneDidBecomeActive(_ scene: UIScene) {
        // A launch command can succeed before UIKit terminates the process.
        // This receipt is emitted only after a visible scene becomes active.
        guard let window, !window.isHidden, window.rootViewController?.view.window === window else { return }
        let destination = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("startup.json")
        let buildURL = Bundle.main.url(forResource: "build", withExtension: "json")!
        let build = (try? Data(contentsOf: buildURL)).flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? [:]
        let receipt: [String: Any] = ["schema": "phone-mic-probe-startup/v1", "scene_active": true,
                                     "at": ISO8601DateFormatter().string(from: Date()), "build": build]
        if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: destination, options: .atomic)
        }
    }
}
