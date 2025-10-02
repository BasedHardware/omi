import Cocoa
import FlutterMacOS
import app_links

@main
class AppDelegate: FlutterAppDelegate {
    override func applicationDidFinishLaunching(_ aNotification: Notification) {
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
      return true
    }
  
    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
      return true
    }

    public override func application(_ application: NSApplication,
                                 continue userActivity: NSUserActivity,
                                 restorationHandler: @escaping ([any NSUserActivityRestoring]) -> Void) -> Bool {

    guard let url = AppLinks.shared.getUniversalLink(userActivity) else {
      return false
    }
  
    AppLinks.shared.handleLink(link: url.absoluteString)
  
    return false // Returning true will stop the propagation to other packages
  }
}
