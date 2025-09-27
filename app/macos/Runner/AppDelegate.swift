import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    override func applicationDidFinishLaunching(_ aNotification: Notification) {
        super.applicationDidFinishLaunching(aNotification)
        
        // Show the main window by default
        let mainWindow = NSApp.windows.first { $0 is MainFlutterWindow }
        mainWindow?.makeKeyAndOrderFront(nil)
    }
}
