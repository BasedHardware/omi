import Foundation
import Combine

// MARK: - API Response Models
struct APIResponse: Codable {
    let success: Bool
    let data: Data?
    let error: String?
}

struct MessageRequest: Codable {
    let text: String
    let fileIds: [String]?
    
    enum CodingKeys: String, CodingKey {
        case text
        case fileIds = "file_ids"
    }
}

struct MessageChunk: Codable {
    let type: String
    let text: String
    let messageId: String?
    let message: ServerMessage?
    
    enum CodingKeys: String, CodingKey {
        case type, text
        case messageId = "message_id"
        case message
    }
}

struct ServerMessage: Codable, Identifiable {
    let id: String
    let text: String
    let createdAt: String
    let sender: String
    let type: String
    let appId: String?
    let fromIntegration: Bool
    let memories: [MessageMemory]
    let askForNps: Bool
    
    enum CodingKeys: String, CodingKey {
        case id, text, sender, type, memories
        case createdAt = "created_at"
        case appId = "app_id"
        case fromIntegration = "from_integration"
        case askForNps = "ask_for_nps"
    }
}

struct MessageMemory: Codable {
    let id: String
    let title: String
    let emoji: String
}

// MARK: - API Client
class OmiAPIClient: ObservableObject {
    static let shared = OmiAPIClient()
    
    private let session = URLSession.shared
    private var cancellables = Set<AnyCancellable>()
    
    private init() {}
    
    // MARK: - Authentication
    private func createAuthenticatedRequest(url: URL, method: String = "GET") -> URLRequest? {
        guard let authHeader = OmiConfig.authHeader() else {
            print("No authentication token available")
            return nil
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        
        return request
    }
    
    // MARK: - Send Message
    func sendMessage(text: String, appId: String? = nil, fileIds: [String] = []) -> AsyncThrowingStream<MessageChunk, Error> {
        return AsyncThrowingStream { continuation in
            Task {
                do {
                    let urlString = appId != nil ? 
                        "\(OmiConfig.fullMessagesURL())?plugin_id=\(appId!)" : 
                        OmiConfig.fullMessagesURL()
                    
                    guard let url = URL(string: urlString),
                          var request = createAuthenticatedRequest(url: url, method: "POST") else {
                        continuation.finish(throwing: APIError.authenticationRequired)
                        return
                    }
                    
                    let messageRequest = MessageRequest(text: text, fileIds: fileIds.isEmpty ? nil : fileIds)
                    request.httpBody = try JSONEncoder().encode(messageRequest)
                    
                    let (data, response) = try await session.data(for: request)
                    
                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        continuation.finish(throwing: APIError.serverError("Failed to send message"))
                        return
                    }
                    
                    // Parse streaming response
                    let responseString = String(data: data, encoding: .utf8) ?? ""
                    let lines = responseString.components(separatedBy: "\n\n")
                    
                    for line in lines {
                        if line.isEmpty { continue }
                        
                        if let chunk = parseMessageChunk(line) {
                            continuation.yield(chunk)
                            
                            if chunk.type == "done" || chunk.type == "error" {
                                continuation.finish()
                                return
                            }
                        }
                    }
                    
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
    
    // MARK: - Get Messages
    func getMessages(appId: String? = nil, limit: Int = 50) async throws -> [ServerMessage] {
        let urlString = appId != nil ? 
            "\(OmiConfig.fullMessagesURL())?plugin_id=\(appId!)&limit=\(limit)" : 
            "\(OmiConfig.fullMessagesURL())?limit=\(limit)"
        
        guard let url = URL(string: urlString),
              let request = createAuthenticatedRequest(url: url) else {
            throw APIError.authenticationRequired
        }
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.serverError("Failed to get messages")
        }
        
        let messages = try JSONDecoder().decode([ServerMessage].self, from: data)
        return messages
    }
    
    // MARK: - Get Initial Message
    func getInitialMessage(appId: String? = nil) async throws -> ServerMessage {
        let urlString = appId != nil ? 
            "\(OmiConfig.fullInitialMessageURL())?app_id=\(appId!)" : 
            OmiConfig.fullInitialMessageURL()
        
        guard let url = URL(string: urlString),
              var request = createAuthenticatedRequest(url: url, method: "POST") else {
            throw APIError.authenticationRequired
        }
        
        request.httpBody = Data() // Empty body for POST request
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw APIError.serverError("Failed to get initial message")
        }
        
        let message = try JSONDecoder().decode(ServerMessage.self, from: data)
        return message
    }
    
    // MARK: - Helper Methods
    private func parseMessageChunk(_ line: String) -> MessageChunk? {
        if line.hasPrefix("think: ") {
            let text = String(line.dropFirst(7)).replacingOccurrences(of: "__CRLF__", with: "\n")
            return MessageChunk(type: "think", text: text, messageId: nil, message: nil)
        }
        
        if line.hasPrefix("data: ") {
            let text = String(line.dropFirst(6)).replacingOccurrences(of: "__CRLF__", with: "\n")
            return MessageChunk(type: "data", text: text, messageId: nil, message: nil)
        }
        
        if line.hasPrefix("done: ") {
            let base64Text = String(line.dropFirst(6))
            if let data = Data(base64Encoded: base64Text),
               let message = try? JSONDecoder().decode(ServerMessage.self, from: data) {
                return MessageChunk(type: "done", text: "", messageId: message.id, message: message)
            }
        }
        
        if line.hasPrefix("message: ") {
            let base64Text = String(line.dropFirst(9))
            if let data = Data(base64Encoded: base64Text),
               let message = try? JSONDecoder().decode(ServerMessage.self, from: data) {
                return MessageChunk(type: "message", text: "", messageId: message.id, message: message)
            }
        }
        
        return nil
    }
}

// MARK: - Error Types
enum APIError: Error, LocalizedError {
    case authenticationRequired
    case serverError(String)
    case decodingError
    case networkError
    
    var errorDescription: String? {
        switch self {
        case .authenticationRequired:
            return "Authentication required. Please sign in to Omi."
        case .serverError(let message):
            return "Server error: \(message)"
        case .decodingError:
            return "Failed to decode server response"
        case .networkError:
            return "Network connection error"
        }
    }
}
