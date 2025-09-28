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

    static let shared = FloatingChatWindowManager()

    private var aiConversationWindow: AIConversationWindow?
    private var currentScreenshotURL: URL?
    private var askAIChannel: FlutterMethodChannel?
    var floatingButton: FloatingControlBar?

    private override init() {}

    func configure(flutterEngine: FlutterEngine, askAIChannel: FlutterMethodChannel) {
        self.askAIChannel = askAIChannel
    }
    
    // MARK: - Ask AI Window Management

    func floatingButtonDidMove() {
        positionAIConversationWindow()
    }

    func positionAIConversationWindow() {
        guard let window = aiConversationWindow, window.isVisible else { return }

        if let button = floatingButton {
            // Synchronize width first
            let buttonWidth = button.frame.width
            if abs(window.frame.width - buttonWidth) > 1.0 { // Only resize if significantly different
                aiConversationWindowWidth = buttonWidth
                let currentHeight = window.frame.height
                window.setContentSize(NSSize(width: buttonWidth, height: currentHeight))
            }
            
            // Position relative to floating control bar
            let buttonFrame = button.frame
            let spacing: CGFloat = 8

            let windowFrame = window.frame
            let newX = buttonFrame.origin.x
            let newY = buttonFrame.origin.y - windowFrame.height - spacing
            
            // Add check to prevent feedback loop
            let newOrigin = NSPoint(x: newX, y: newY)
            if abs(windowFrame.origin.x - newOrigin.x) > 0.1 || abs(windowFrame.origin.y - newOrigin.y) > 0.1 {
                window.setFrameOrigin(newOrigin)
            }
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

    @objc private func aiConversationWindowDidMove(_ notification: Notification) {
        guard let window = notification.object as? AIConversationWindow,
              window == self.aiConversationWindow,
              let floatingButton = self.floatingButton else {
            return
        }
        
        // Position floating button relative to this window
        let windowFrame = window.frame
        let spacing: CGFloat = 8
        let newX = windowFrame.origin.x
        let newY = windowFrame.origin.y + windowFrame.height + spacing
        
        // Add check to prevent feedback loop
        let newOrigin = NSPoint(x: newX, y: newY)
        if abs(floatingButton.frame.origin.x - newOrigin.x) > 0.1 || abs(floatingButton.frame.origin.y - newOrigin.y) > 0.1 {
            floatingButton.setFrameOrigin(newOrigin)
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
                self.aiConversationWindow = AIConversationWindow(contentRect: windowRect, backing: .buffered, defer: false)
                
                // Observe window move events to sync floating button
                NotificationCenter.default.addObserver(
                    self,
                    selector: #selector(self.aiConversationWindowDidMove),
                    name: NSWindow.didMoveNotification,
                    object: self.aiConversationWindow
                )
            }
            
            // Update view
            let conversationView = AIConversationView(manager: self, screenshotURL: self.currentScreenshotURL)
            let hostingController = NSHostingController(rootView: conversationView)
            self.aiConversationWindow?.contentViewController = hostingController

            // Resize window to fit content
            if let contentView = self.aiConversationWindow?.contentView {
                let newSize = contentView.intrinsicContentSize
                let currentWidth = self.floatingButton?.frame.width ?? self.aiConversationWindowWidth
                self.aiConversationWindow?.setContentSize(NSSize(width: currentWidth, height: newSize.height))
            }
            
            // Position and show the window (this will handle width sync)
            self.aiConversationWindow?.makeKeyAndOrderFront(nil)
            self.positionAIConversationWindow()
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
            
            // Update the existing window's view instead of recreating it
            if let window = self.aiConversationWindow, window.isVisible {
                let conversationView = AIConversationView(manager: self, screenshotURL: nil)
                let hostingController = NSHostingController(rootView: conversationView)
                window.contentViewController = hostingController
            }
        }
    }

    func clearAndHideAIConversationWindow() {
        DispatchQueue.main.async {
            self.askAIInputText = ""
            self.currentScreenshotURL = nil
            self.isShowingAIResponse = false
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
