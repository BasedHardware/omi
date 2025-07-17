import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    
    override func applicationDidFinishLaunching(_ notification: Notification) {
        super.applicationDidFinishLaunching(notification)
        
        // Initialize the HotKey manager for global shortcuts
        HotKeyManager.shared.initialize()
    }
    
    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
    
    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
    
    override func applicationWillTerminate(_ notification: Notification) {
        // Clean up HotKey manager
        HotKeyManager.shared.cleanup()
        super.applicationWillTerminate(notification)
    }
}
