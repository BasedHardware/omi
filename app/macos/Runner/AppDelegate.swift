import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
    
    // Keep a strong reference to HotKeyManager to prevent deallocation
    private var hotKeyManager: HotKeyManager?
    
    override func applicationDidFinishLaunching(_ notification: Notification) {
        super.applicationDidFinishLaunching(notification)
        
        print("🚀 AppDelegate: applicationDidFinishLaunching called - STARTING HOTKEY SETUP")
        
        // Force a slight delay to ensure everything is loaded
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            print("🚀 AppDelegate: About to initialize HotKeyManager")
            
            // Initialize the HotKey manager for global shortcuts and keep a strong reference
            self.hotKeyManager = HotKeyManager.shared
            self.hotKeyManager?.initialize()
            
            print("🚀 AppDelegate: HotKeyManager initialization completed")
        }
    }
    
    override func applicationDidBecomeActive(_ notification: Notification) {
        super.applicationDidBecomeActive(notification)
        
        // Recheck accessibility permissions when app becomes active
        hotKeyManager?.recheckPermissions()
    }
    
    override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
    
    override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
    
    override func applicationWillTerminate(_ notification: Notification) {
        // Clean up HotKey manager
        hotKeyManager?.cleanup()
        hotKeyManager = nil
        super.applicationWillTerminate(notification)
    }
}
