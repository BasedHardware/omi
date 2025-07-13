import Cocoa
import SwiftUI

// mark: - global hotkey registrar
class HotkeyRegistrar: NSObject {
    
    // mark: - properties
    static let shared = HotkeyRegistrar()
    
    private var globalEventMonitor: Any?
    private var chatOverlayManager: ChatOverlayManager?
    
    // mark: - initialization
    override init() {
        super.init()
        chatOverlayManager = ChatOverlayManager()
    }
    
    // mark: - hotkey registration
    func registerGlobalHotkey() {
        // remove existing monitor if present
        if let monitor = globalEventMonitor {
            NSEvent.removeMonitor(monitor)
            globalEventMonitor = nil
        }
        
        // register global hotkey monitor for option + space
        globalEventMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self = self else { return }
            
            // check for option + space combination
            // option key flag: nsevent.modifierflags.option
            // space key code: 49
            if event.modifierFlags.contains(.option) && event.keyCode == 49 {
                print("DEBUG: Global hotkey (Option + Space) triggered")
                self.handleHotkeyTrigger()
            }
        }
        
        if globalEventMonitor != nil {
            print("INFO: Global hotkey registered successfully (Option + Space)")
        } else {
            print("ERROR: Failed to register global hotkey")
        }
    }
    
    // mark: - hotkey handler
    private func handleHotkeyTrigger() {
        guard let overlayManager = chatOverlayManager else {
            print("ERROR: ChatOverlayManager not initialized")
            return
        }
        
        // check if popup is already open to avoid duplicates
        if overlayManager.isPopupVisible() {
            print("DEBUG: Popup already visible, ignoring hotkey")
            return
        }
        
        // show the popup
        overlayManager.showPopup()
        print("DEBUG: Popup shown via hotkey")
    }
    
    // mark: - cleanup
    func cleanup() {
        if let monitor = globalEventMonitor {
            NSEvent.removeMonitor(monitor)
            globalEventMonitor = nil
            print("INFO: Global hotkey monitor removed")
        }
        
        chatOverlayManager?.cleanup()
        chatOverlayManager = nil
    }
    
    // mark: - deinitialization
    deinit {
        cleanup()
    }
} 