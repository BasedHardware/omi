import Cocoa
import FlutterMacOS
import SwiftUI

/// Manages the AI conversation window functionality.
class FloatingChatWindowManager: NSObject, ObservableObject {
    @Published var aiResponseText: String = ""
    @Published var isAIResponseLoading: Bool = true
    @Published var askAIInputText: String = ""
    @Published var isShowingAIResponse: Bool = false
    @Published var aiConversationWindowWidth: CGFloat = 400
    @Published var currentScreenshotURL: URL?

    static let shared = FloatingChatWindowManager()

    private var aiConversationWindow: AIConversationWindow?
    private var askAIChannel: FlutterMethodChannel?
    var floatingButton: FloatingControlBar?

    private override init() {}

    func configure(flutterEngine: FlutterEngine, askAIChannel: FlutterMethodChannel) {
        self.askAIChannel = askAIChannel
    }
    
    // MARK: - Ask AI Window Management

    func floatingButtonDidMove() {
        // Only sync width when button moves (position is handled by parent/child relationship)
        syncWindowWidth()
    }
    
    private func syncWindowWidth() {
        guard let window = aiConversationWindow, 
              window.isVisible,
              let button = floatingButton else { return }
        
        let buttonWidth = button.frame.width
        if abs(window.frame.width - buttonWidth) > 1.0 {
            aiConversationWindowWidth = buttonWidth
            let currentHeight = window.frame.height
            window.setContentSize(NSSize(width: buttonWidth, height: currentHeight))
            // Update min/max size to maintain fixed width
            window.minSize = NSSize(width: buttonWidth, height: 150)
            window.maxSize = NSSize(width: buttonWidth, height: 800)
        }
    }

    func positionAIConversationWindow() {
        guard let window = aiConversationWindow else { return }

        if let button = floatingButton {
            // Position relative to floating control bar
            let buttonFrame = button.frame
            let spacing: CGFloat = 8
            let windowFrame = window.frame
            let newX = buttonFrame.origin.x
            let newY = buttonFrame.origin.y - windowFrame.height - spacing
            
            // Set initial position (subsequent moves handled by parent/child relationship)
            window.setFrameOrigin(NSPoint(x: newX, y: newY))
        } else {
            // If no floating control bar, center the window on screen
            if let screen = NSScreen.main {
                let screenFrame = screen.visibleFrame
                let windowFrame = window.frame
                let newX = screenFrame.origin.x + (screenFrame.width - windowFrame.width) / 2
                let newY = screenFrame.origin.y + (screenFrame.height - windowFrame.height) / 2
                window.setFrameOrigin(NSPoint(x: newX, y: newY))
            }
        }
    }

    func toggleAIConversationWindow(screenshotURL: URL?) {
        DispatchQueue.main.async {
            // If window exists and is visible, hide it
            if let window = self.aiConversationWindow, window.isVisible {
                self.clearAndHideAIConversationWindow()
                return
            }
            
            // Otherwise, show the window
            self.currentScreenshotURL = screenshotURL
            self.isShowingAIResponse = false
            self.isAIResponseLoading = true
            self.aiResponseText = ""
            
            // Create window if it doesn't exist
            if self.aiConversationWindow == nil {
                // Use current width or default
                let initialWidth = self.floatingButton?.frame.width ?? self.aiConversationWindowWidth
                let windowRect = NSRect(x: 0, y: 0, width: initialWidth, height: 300)
                self.aiConversationWindow = AIConversationWindow(contentRect: windowRect, defer: false)
                
                // No need to observe move events - parent/child relationship handles this
            }
            
            // Update view
            let conversationView = AIConversationView(manager: self)
            let hostingController = NSHostingController(rootView: conversationView)
            self.aiConversationWindow?.contentViewController = hostingController

            // Resize window to fit content
            if let contentView = self.aiConversationWindow?.contentView {
                let newSize = contentView.intrinsicContentSize
                let currentWidth = self.floatingButton?.frame.width ?? self.aiConversationWindowWidth
                self.aiConversationWindow?.setContentSize(NSSize(width: currentWidth, height: newSize.height))
            }
            
            // Position the window first
            self.positionAIConversationWindow()
            
            // Make chat window a child of floating button for synchronized movement
            if let button = self.floatingButton, let chatWindow = self.aiConversationWindow {
                button.addChildWindow(chatWindow, ordered: .below)
            }
            
            // Show the window
            self.aiConversationWindow?.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
    
    // Keep the old method for backward compatibility, but make it use toggle
    func showAIConversationWindow(screenshotURL: URL?) {
        toggleAIConversationWindow(screenshotURL: screenshotURL)
    }

    func sendAIQuery(message: String, url: URL?) {
        print("DEBUG: Send tapped. Message: \(message), URL: \(url?.path ?? "nil")")
        var arguments: [String: Any] = ["message": message]
        if let path = url?.path {
            arguments["filePath"] = path
        }
        askAIChannel?.invokeMethod("sendQuery", arguments: arguments)
        
        // Switch to response view
        isShowingAIResponse = true
        
        // Resize window to fit response view and maintain alignment
        DispatchQueue.main.async {
            if let window = self.aiConversationWindow {
                // Synchronize width with floating control bar if available
                if let buttonWidth = self.floatingButton?.frame.width {
                    self.aiConversationWindowWidth = buttonWidth
                }
                window.setContentSize(NSSize(width: self.aiConversationWindowWidth, height: 300)) // AIResponseView size
                self.positionAIConversationWindow()
            }
        }
    }

    func removeScreenshotFromAIConversation() {
        DispatchQueue.main.async {
            self.currentScreenshotURL = nil
        }
    }

    func clearAndHideAIConversationWindow() {
        DispatchQueue.main.async {
            self.askAIInputText = ""
            self.currentScreenshotURL = nil
            self.isShowingAIResponse = false
            
            // Remove as child window before hiding
            if let button = self.floatingButton, let chatWindow = self.aiConversationWindow {
                button.removeChildWindow(chatWindow)
            }
            
            self.aiConversationWindow?.orderOut(nil)
        }
    }

    func handleAIResponseChunk(arguments: Any?) {
        guard let args = arguments as? [String: Any],
              let type = args["type"] as? String else {
            print("ERROR: Invalid AI response chunk arguments")
            return
        }
        
        DispatchQueue.main.async {
            switch type {
            case "data":
                if self.isAIResponseLoading {
                    self.isAIResponseLoading = false
                }
                let textChunk = args["text"] as? String ?? ""
                self.aiResponseText += textChunk
            case "done":
                self.isAIResponseLoading = false
                // The final text might be in the 'done' chunk if the message was short
                if let finalText = args["text"] as? String, !finalText.isEmpty {
                    self.aiResponseText = finalText
                }
            case "error":
                self.isAIResponseLoading = false
                self.aiResponseText = args["text"] as? String ?? "An unknown error occurred."
            default:
                print("WARNING: Unknown AI response chunk type: \(type)")
            }
        }
    }
}
