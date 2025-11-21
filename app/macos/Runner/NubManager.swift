import Cocoa
import FlutterMacOS

class NubManager {

    // MARK: - Singleton
    static let shared = NubManager()

    // MARK: - Properties
    private var nubWindow: NubWindow?
    private weak var mainFlutterWindow: NSWindow?

    // MARK: - Initialization
    private init() {
        setupNotifications()
    }

    // MARK: - Setup

    private func setupNotifications() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleNubClicked),
            name: .nubClicked,
            object: nil
        )
    }

    // MARK: - Configuration

    func setMainWindow(_ window: NSWindow) {
        self.mainFlutterWindow = window
        print("NubManager: Main window reference set")
    }

    // MARK: - Public Methods

    func showNub(for appName: String = "Meeting") {
        print("NubManager: showNub called for \(appName)")
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { 
                print("NubManager: Self is nil")
                return 
            }

            if self.nubWindow == nil {
                print("NubManager: Creating new NubWindow")
                self.nubWindow = NubWindow(
                    contentRect: NSRect.zero,
                    styleMask: [.borderless],
                    backing: .buffered,
                    defer: false
                )
                print("NubManager: NubWindow created: \(self.nubWindow != nil)")
            } else {
                print("NubManager: Reusing existing NubWindow")
            }

            self.nubWindow?.updateMeetingApp(appName)
            print("NubManager: About to call show() on nubWindow")
            self.nubWindow?.show()
            print("NubManager: Nub shown for \(appName), window visible: \(self.nubWindow?.isVisible ?? false)")
        }
    }

    func hideNub() {
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.nubWindow?.hide()
            print("NubManager: Nub hidden")
        }
    }

    func isNubVisible() -> Bool {
        return nubWindow?.isVisible ?? false
    }

    // MARK: - Event Handlers

    @objc private func handleNubClicked() {
        print("NubManager: Nub clicked - opening main window")
        openMainWindow()
    }

    private func openMainWindow() {
        guard let mainWindow = mainFlutterWindow else {
            print("NubManager: Main window not available")
            return
        }

        DispatchQueue.main.async { [weak self] in
            // Bring app to front
            NSApp.activate(ignoringOtherApps: true)

            // Show and focus the main window
            mainWindow.makeKeyAndOrderFront(nil)
            mainWindow.orderFrontRegardless()

            // Optionally hide the nub when main window opens
            // Uncomment if you want this behavior
            // self?.hideNub()

            print("NubManager: Main window opened and focused")
        }
    }

    // MARK: - Cleanup

    deinit {
        NotificationCenter.default.removeObserver(self)
    }
}
