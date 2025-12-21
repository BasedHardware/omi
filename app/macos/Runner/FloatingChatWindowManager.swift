import Cocoa
import FlutterMacOS
import SwiftUI

/// Manages the AI conversation state and communication with Flutter.
class FloatingChatWindowManager: NSObject {
    static let shared = FloatingChatWindowManager()

    private var askAIChannel: FlutterMethodChannel?
    var floatingButton: FloatingControlBar?

    private override init() {}

    func configure(flutterEngine: FlutterEngine, askAIChannel: FlutterMethodChannel) {
        self.askAIChannel = askAIChannel
    }
    
    func toggleAIConversation(fileUrl: URL?) {
        guard let button = floatingButton else { return }
        button.showAIConversation(fileUrl: fileUrl)
    }

    func sendAIQuery(message: String, url: URL?) {
        var arguments: [String: Any] = ["message": message]
        if let path = url?.path {
            arguments["filePath"] = path
        }
        askAIChannel?.invokeMethod("sendQuery", arguments: arguments)
    }

    func handleAIResponseChunk(arguments: Any?) {
        guard let args = arguments as? [String: Any],
              let type = args["type"] as? String else {
            print("ERROR: Invalid AI response chunk arguments")
            return
        }
        
        let text = args["text"] as? String ?? ""
        floatingButton?.updateAIResponse(type: type, text: text)
    }
}
