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
                guard args[i + 1] == "wearable" else { return nil }
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

final class ProbeViewController: UIViewController {
    let status = UILabel()
    private var didAutoStart = false
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        let title = UILabel(); title.text = "Omi Wearable Probe"; title.font = .preferredFont(forTextStyle: .largeTitle)
        status.text = "Tests reconnect and audio packet delivery from your Omi wearable."
        status.numberOfLines = 0; status.font = .preferredFont(forTextStyle: .body)
        let wearable = UIButton(type: .system); wearable.setTitle("Start wearable reconnect test", for: .normal)
        wearable.addTarget(self, action: #selector(startWearable), for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [title, status, wearable]); stack.axis = .vertical; stack.spacing = 28
        stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 40),
        ])
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
        if options.mode == "wearable" { showWearable(duration: options.duration) }
    }
    private func showWearable(duration: Double) {
        let controller = WearableViewController(); controller.duration = duration
        controller.modalPresentationStyle = .fullScreen
        present(controller, animated: true)
    }
    @objc private func startWearable() {
        showWearable(duration: 90)
    }
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
