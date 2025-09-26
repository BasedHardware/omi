import Cocoa
import FlutterMacOS
import SwiftUI

/// Manages the lifecycle of multiple floating chat windows.
class FloatingChatWindowManager: NSObject, NSWindowDelegate, ObservableObject {
    @Published var aiResponseText: String = ""
    @Published var isAIResponseLoading: Bool = true
    @Published var askAIInputText: String = ""
    @Published var isShowingAIResponse: Bool = false
    @Published var aiConversationWindowWidth: CGFloat = 500

    static let shared = FloatingChatWindowManager()
    static let windowCountChangedNotification = Notification.Name("FloatingChatWindowCountChanged")

    private var chatWindows: [String: FloatingChatWindow] = [:]
    private var aiConversationWindow: AIConversationWindow?
    private var currentScreenshotURL: URL?
    private var channel: FlutterMethodChannel?
    private var askAIChannel: FlutterMethodChannel?
    var floatingButton: FloatingControlBar?
    private var isProgrammaticallyMoving: Bool = false

    var windowCount: Int {
        return chatWindows.count
    }

    private override init() {}

    func configure(flutterEngine: FlutterEngine, askAIChannel: FlutterMethodChannel) {
        let messenger = flutterEngine.binaryMessenger
        channel = FlutterMethodChannel(name: "com.omi/floating_chat", binaryMessenger: messenger)
        self.askAIChannel = askAIChannel
    }

    private func invokeMethodWithRetry(method: String, arguments: Any?, maxAttempts: Int = 3, delay: TimeInterval = 0.2) {
        var attempts = 0
        
        func attempt() {
            channel?.invokeMethod(method, arguments: arguments) { result in
                if let error = result as? FlutterError {
                    attempts += 1
                    if attempts < maxAttempts {
                        print("ERROR: Failed to invoke '\(method)' (attempt \(attempts)/\(maxAttempts)): \(error.message ?? "No message"). Retrying...")
                        DispatchQueue.main.asyncAfter(deadline: .now() + delay * Double(attempts)) {
                            attempt()
                        }
                    } else {
                        print("ERROR: Max retries reached for '\(method)'. Giving up. Error: \(error.message ?? "No message")")
                    }
                }
                // Success, do nothing.
            }
        }
        
        attempt()
    }

    func requestHistoryForWindow(id: String) {
        invokeMethodWithRetry(method: "requestHistory", arguments: ["conversationId": id])
    }

    func sendMessageToFlutter(id: String, message: [String: Any]) {
        invokeMethodWithRetry(method: "userMessage", arguments: message)
    }

    func handleAIResponse(arguments: Any?) {
        guard let args = arguments as? [String: Any],
              let id = args["conversationId"] as? String,
              let messageId = args["messageId"] as? String,
              let text = args["text"] as? String,
              let isFinal = args["isFinal"] as? Bool else {
            print("ERROR: Invalid AI response arguments")
            return
        }

        DispatchQueue.main.async {
            if let window = self.chatWindows[id] {
                window.updateAIResponse(messageId: messageId, message: text, isFinal: isFinal)
            }
        }
    }

    func handleChatHistory(arguments: Any?) {
        guard let args = arguments as? [String: Any],
              let id = args["conversationId"] as? String,
              let history = args["history"] as? [[String: Any]] else {
            print("ERROR: Invalid chat history arguments")
            return
        }

        DispatchQueue.main.async {
            if let window = self.chatWindows[id] {
                window.displayHistory(messages: history)
            }
        }
    }

    /// Creates and shows a new chat window or brings an existing one to the front.
    func showWindow(id: String) {
        DispatchQueue.main.async {
            if let window = self.chatWindows[id] {
                window.makeKeyAndOrderFront(nil)
                NSApp.activate(ignoringOtherApps: true)
                if id == "default", let button = self.floatingButton {
                    self.positionWindow(for: button, and: window)
                }
                return
            }

            let window = FloatingChatWindow(id: id)
            
            window.delegate = self

            self.chatWindows[id] = window
            
            if id == "default", let button = self.floatingButton {
                self.positionWindow(for: button, and: window)
            }

            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            NotificationCenter.default.post(name: FloatingChatWindowManager.windowCountChangedNotification, object: nil)
        }
    }

    /// Hides a chat window.
    func hideWindow(id: String) {
        DispatchQueue.main.async {
            if let window = self.chatWindows[id] {
                window.orderOut(nil)
            }
        }
    }
    
    func resetAllPositions() {
        DispatchQueue.main.async {
            for (_, window) in self.chatWindows {
                window.resetPosition()
            }
        }
    }
    
    // MARK: - NSWindowDelegate
    
    func windowWillClose(_ notification: Notification) {
        guard let window = notification.object as? FloatingChatWindow else { return }
        
        // Find the ID for this window and remove it from our tracking dictionary.
        if let (id, _) = chatWindows.first(where: { $0.value == window }) {
            chatWindows.removeValue(forKey: id)
            print("DEBUG: Closed and removed chat window with id \(id)")
            NotificationCenter.default.post(name: FloatingChatWindowManager.windowCountChangedNotification, object: nil)
        }
    }

    func windowDidMove(_ notification: Notification) {
        guard !isProgrammaticallyMoving, let window = notification.object as? FloatingChatWindow else { return }
        positionButton(for: window)
    }
    
    func windowDidResize(_ notification: Notification) {
        guard let window = notification.object as? FloatingChatWindow else { return }
        positionButton(for: window)
    }
    
    private func positionButton(for window: FloatingChatWindow) {
        guard window.windowId == "default", let button = floatingButton, button.isVisible, !isProgrammaticallyMoving else {
            return
        }
        
        isProgrammaticallyMoving = true
        
        let windowFrame = window.frame
        let buttonFrame = button.frame
        
        let newX = windowFrame.origin.x + (windowFrame.width - buttonFrame.width) / 2
        let newY = windowFrame.origin.y + windowFrame.height
        
        button.setFrameOrigin(NSPoint(x: newX, y: newY))
        
        isProgrammaticallyMoving = false
    }
    
    func positionWindowFromButton() {
        guard let button = floatingButton, let window = chatWindows["default"], window.isVisible, !isProgrammaticallyMoving else {
            return
        }
        
        isProgrammaticallyMoving = true
        
        let buttonFrame = button.frame
        let windowFrame = window.frame
        
        let newX = buttonFrame.origin.x - (windowFrame.width - buttonFrame.width) / 2
        let newY = buttonFrame.origin.y - windowFrame.height
        
        window.setFrameOrigin(NSPoint(x: newX, y: newY))
        
        isProgrammaticallyMoving = false
    }
    
    private func positionWindow(for button: FloatingControlBar, and window: FloatingChatWindow) {
        isProgrammaticallyMoving = true
        
        let buttonFrame = button.frame
        let windowFrame = window.frame
        
        let newX = buttonFrame.origin.x - (windowFrame.width - buttonFrame.width) / 2
        let newY = buttonFrame.origin.y - windowFrame.height
        
        window.setFrameOrigin(NSPoint(x: newX, y: newY))
        
        isProgrammaticallyMoving = false
    }

    // MARK: - Ask AI Window Management

    func floatingButtonDidMove() {
        positionWindowFromButton()
        positionAIConversationWindow()
    }

    private func positionAIConversationWindow() {
        guard let button = floatingButton, let window = aiConversationWindow, window.isVisible else { return }

        let buttonFrame = button.frame
        let spacing: CGFloat = 8

        let windowFrame = window.frame
        let newX = buttonFrame.origin.x
        let newY = buttonFrame.origin.y - windowFrame.height - spacing
        window.setFrameOrigin(NSPoint(x: newX, y: newY))
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
            
            if let buttonWidth = self.floatingButton?.frame.width {
                self.aiConversationWindowWidth = buttonWidth
            }

            if self.aiConversationWindow == nil {
                let windowRect = NSRect(x: 0, y: 0, width: self.aiConversationWindowWidth, height: 300) // dummy rect
                self.aiConversationWindow = AIConversationWindow(contentRect: windowRect, backing: .buffered, defer: false)
            }
            
            // Update view
            let conversationView = AIConversationView(manager: self, screenshotURL: self.currentScreenshotURL)
            let hostingController = NSHostingController(rootView: conversationView)
            self.aiConversationWindow?.contentViewController = hostingController

            // Resize window to fit content before positioning
            if let contentView = self.aiConversationWindow?.contentView {
                let newSize = contentView.intrinsicContentSize
                self.aiConversationWindow?.setContentSize(NSSize(width: self.aiConversationWindowWidth, height: newSize.height))
            }
            
            self.positionAIConversationWindow()
            
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
        
        // Resize window to fit response view
        DispatchQueue.main.async {
            if let window = self.aiConversationWindow {
                window.setContentSize(NSSize(width: self.aiConversationWindowWidth, height: 300)) // AIResponseView size
                self.positionAIConversationWindow()
            }
        }
    }

    func removeScreenshotFromAIConversation() {
        showAIConversationWindow(screenshotURL: nil)
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
