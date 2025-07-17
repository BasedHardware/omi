import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    
    override func applicationDidFinishLaunching(_ notification: Notification) {
        super.applicationDidFinishLaunching(notification)
        
        print("🚀 AppDelegate: applicationDidFinishLaunching called")
        
        // Force a slight delay to ensure everything is loaded
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            print("🚀 AppDelegate: About to initialize HotKeyManager")
            
            // Initialize the HotKey manager for global shortcuts
            HotKeyManager.shared.initialize()
            
            print("🚀 AppDelegate: HotKeyManager initialization completed")
        }
    }
    
    override func applicationDidBecomeActive(_ notification: Notification) {
        super.applicationDidBecomeActive(notification)
        
        // Recheck accessibility permissions when app becomes active
        HotKeyManager.shared.recheckPermissions()
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
