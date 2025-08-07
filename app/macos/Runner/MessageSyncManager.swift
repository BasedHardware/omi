import Foundation

// MARK: - Message Sync Manager
// Handles synchronizing messages between Swift overlay and Flutter app
class MessageSyncManager: ObservableObject {
    static let shared = MessageSyncManager()
    
    private let userDefaults = UserDefaults.standard
    private let syncKey = "swift_overlay_messages"
    private let notificationKey = "swift_overlay_message_notification"
    
    private init() {}
    
    // MARK: - Message Synchronization
    
    /// Sync a new message to Flutter app
    func syncMessageToFlutter(_ message: ChatMessage) {
        let messageData = MessageSyncData(
            id: message.id.uuidString,
            content: message.content,
            isUser: message.isUser,
            timestamp: message.timestamp,
            source: "swift_overlay"
        )
        
        // Get existing synced messages
        var syncedMessages = getSyncedMessages()
        syncedMessages.append(messageData)
        
        // Keep only last 50 messages to avoid bloating UserDefaults
        if syncedMessages.count > 50 {
            syncedMessages = Array(syncedMessages.suffix(50))
        }
        
        // Save to UserDefaults
        if let encoded = try? JSONEncoder().encode(syncedMessages) {
            userDefaults.set(encoded, forKey: syncKey)
            
            // Send notification to Flutter app
            let notification = MessageNotification(
                type: "new_message",
                messageId: messageData.id,
                timestamp: Date()
            )
            
            if let notificationData = try? JSONEncoder().encode(notification) {
                userDefaults.set(notificationData, forKey: notificationKey)
            }
            
            print("📤 Synced message to Flutter: \(message.content.prefix(50))...")
        }
    }
    
    /// Flush all current messages to Flutter app (for expand functionality)
    func flushMessagesToFlutter(_ messages: [ChatMessage]) {
        let messageDataArray = messages.map { message in
            MessageSyncData(
                id: message.id.uuidString,
                content: message.content,
                isUser: message.isUser,
                timestamp: message.timestamp,
                source: "swift_overlay"
            )
        }
        
        // Save all messages to UserDefaults
        if let encoded = try? JSONEncoder().encode(messageDataArray) {
            userDefaults.set(encoded, forKey: syncKey)
            print("📤 Flushed \(messages.count) messages to Flutter for expansion")
        }
    }
    
    /// Get messages that were synced from Flutter
    func getMessagesFromFlutter() -> [ChatMessage] {
        guard let data = userDefaults.data(forKey: "flutter_to_swift_messages"),
              let syncedMessages = try? JSONDecoder().decode([MessageSyncData].self, from: data) else {
            return []
        }
        
        return syncedMessages.map { syncData in
            ChatMessage(
                content: syncData.content,
                isUser: syncData.isUser
            )
        }
    }
    
    /// Clear synced messages (cleanup)
    func clearSyncedMessages() {
        userDefaults.removeObject(forKey: syncKey)
        userDefaults.removeObject(forKey: notificationKey)
        print("🧹 Cleared synced messages")
    }
    
    // MARK: - Private Methods
    
    private func getSyncedMessages() -> [MessageSyncData] {
        guard let data = userDefaults.data(forKey: syncKey),
              let messages = try? JSONDecoder().decode([MessageSyncData].self, from: data) else {
            return []
        }
        return messages
    }
}

// MARK: - Data Models

struct MessageSyncData: Codable {
    let id: String
    let content: String
    let isUser: Bool
    let timestamp: Date
    let source: String
}

struct MessageNotification: Codable {
    let type: String
    let messageId: String
    let timestamp: Date
}

// MARK: - ChatMessage Extension
extension ChatMessage {
    func toSyncData(source: String = "swift_overlay") -> MessageSyncData {
        return MessageSyncData(
            id: self.id.uuidString,
            content: self.content,
            isUser: self.isUser,
            timestamp: self.timestamp,
            source: source
        )
    }
}
