import Cocoa
import FlutterMacOS

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
}
