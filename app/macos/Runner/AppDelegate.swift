import Cocoa
import FlutterMacOS

@main
class AppDelegate: FlutterAppDelegate {
  
  // mark: - properties
  private var hotkeyRegistrar: HotkeyRegistrar?
  
  override func applicationDidFinishLaunching(_ notification: Notification) {
    super.applicationDidFinishLaunching(notification)
    
    // set app to run as accessory (menu bar only, no dock icon)
    NSApp.setActivationPolicy(.accessory)
    
    // initialize and register global hotkey
    hotkeyRegistrar = HotkeyRegistrar.shared
    hotkeyRegistrar?.registerGlobalHotkey()
    
    print("INFO: App configured as menu bar app with global hotkey")
  }
  
  override func applicationWillTerminate(_ notification: Notification) {
    // cleanup hotkey registrar
    hotkeyRegistrar?.cleanup()
    hotkeyRegistrar = nil
    
    print("INFO: App terminating, hotkey registrar cleaned up")
    
    super.applicationWillTerminate(notification)
  }
  
   override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
    // don't terminate when last window closes (menu bar app behavior)
    return false
  }
  
   override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
    return true
  }
}
