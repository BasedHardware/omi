import Cocoa
import FirebaseAuth
import FirebaseCore
import FirebaseMessaging
import FlutterMacOS
import app_links

@main
class AppDelegate: FlutterAppDelegate {
    // Method channel for direct URL delivery to Flutter
    private var urlChannel: FlutterMethodChannel?

    // Required for app_links plugin to register Apple Event handler for URL schemes
    override func applicationWillFinishLaunching(_ notification: Notification) {
        // Register our own Apple Event handler for URL schemes
        NSAppleEventManager.shared().setEventHandler(
            self,
            andSelector: #selector(handleURLEvent(_:withReplyEvent:)),
            forEventClass: AEEventClass(kInternetEventClass),
            andEventID: AEEventID(kAEGetURL)
        )
        NSLog("DEBUG: Registered Apple Event handler for URL schemes")

        super.applicationWillFinishLaunching(notification)
    }

    @objc func handleURLEvent(_ event: NSAppleEventDescriptor, withReplyEvent replyEvent: NSAppleEventDescriptor) {
        if let urlString = event.paramDescriptor(forKeyword: AEKeyword(keyDirectObject))?.stringValue {
            NSLog("DEBUG: Received URL via Apple Event: %@", urlString)

            // Bring app to front when receiving OAuth callback
            NSApp.activate(ignoringOtherApps: true)
            if let mainWindow = NSApp.windows.first(where: { $0 is MainFlutterWindow }) {
                mainWindow.makeKeyAndOrderFront(nil)
            }

            // Try app_links first
            AppLinks.shared.handleLink(link: urlString)
            NSLog("DEBUG: Called AppLinks.shared.handleLink")

            // Also send via direct method channel as fallback
            sendURLToFlutter(urlString)
        }
    }

    private func sendURLToFlutter(_ url: String) {
        // Get the Flutter view controller and set up method channel if needed
        if urlChannel == nil {
            if let mainWindow = NSApp.windows.first(where: { $0 is MainFlutterWindow }) as? MainFlutterWindow,
               let flutterViewController = mainWindow.contentViewController as? FlutterViewController {
                urlChannel = FlutterMethodChannel(
                    name: "com.omi/deep_links",
                    binaryMessenger: flutterViewController.engine.binaryMessenger
                )
                NSLog("DEBUG: Created deep_links method channel")
            }
        }

        urlChannel?.invokeMethod("onDeepLink", arguments: url)
        NSLog("DEBUG: Sent URL to Flutter via method channel: %@", url)
    }

    override func applicationDidFinishLaunching(_ aNotification: Notification) {
        // Explicitly register for remote notifications
        NSApplication.shared.registerForRemoteNotifications()

        super.applicationDidFinishLaunching(aNotification)

        // Delay to check if app was launched hidden (e.g., as a login item)
        DispatchQueue.main.async {
            if !NSApp.isHidden {
                let mainWindow = NSApp.windows.first { $0 is MainFlutterWindow }
                mainWindow?.makeKeyAndOrderFront(nil)
            }
        }
    }

    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
      // Keep app running in menu bar when main window closes
      return false
    }

    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }

    public override func application(
        _ application: NSApplication,
        continue userActivity: NSUserActivity,
        restorationHandler: @escaping ([any NSUserActivityRestoring]) -> Void
    ) -> Bool {

        guard let url = AppLinks.shared.getUniversalLink(userActivity) else {
            return false
        }

        AppLinks.shared.handleLink(link: url.absoluteString)

        return false  // Returning true will stop the propagation to other packages
    }

    // Handle custom URL schemes (e.g., omi://auth/callback for OAuth)
    override func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls {
            print("DEBUG: Received URL scheme callback: \(url.absoluteString)")
            AppLinks.shared.handleLink(link: url.absoluteString)
        }
    }
}
