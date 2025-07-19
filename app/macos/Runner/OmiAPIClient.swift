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
    private func createAuthenticatedRequest(url: URL, method: String) -> URLRequest? {
        guard let authHeader = OmiConfig.authHeader() else {
            print("❌ No auth token available")
            return nil
        }
        
        // Log token for debugging (first/last 10 chars only)
        let tokenPrefix = String(authHeader.dropFirst(7).prefix(10))
        let tokenSuffix = String(authHeader.dropFirst(7).suffix(10))
        print("🔑 Using auth token: \(tokenPrefix)...\(tokenSuffix)")
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
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
                    
                    print("🌐 Sending request to: \(urlString)")
                    print("🔑 Auth token: \(OmiConfig.userToken?.prefix(20) ?? "nil")...")
                    print("👤 User ID: \(OmiConfig.userId ?? "nil")")
                    
                    guard let url = URL(string: urlString),
                          var request = createAuthenticatedRequest(url: url, method: "POST") else {
                        print("❌ Failed to create authenticated request")
                        continuation.finish(throwing: APIError.authenticationRequired)
                        return
                    }
                    
                    let messageRequest = MessageRequest(text: text, fileIds: fileIds.isEmpty ? nil : fileIds)
                    request.httpBody = try JSONEncoder().encode(messageRequest)
                    
                    print("📤 Request body: \(String(data: request.httpBody!, encoding: .utf8) ?? "nil")")
                    print("📋 Request headers: \(request.allHTTPHeaderFields ?? [:])")
                    
                    let (data, response) = try await session.data(for: request)
                    
                    print("📥 Response status: \((response as? HTTPURLResponse)?.statusCode ?? 0)")
                    print("📥 Response data: \(String(data: data, encoding: .utf8) ?? "nil")")
                    
                    guard let httpResponse = response as? HTTPURLResponse,
                          httpResponse.statusCode == 200 else {
                        let statusCode = (response as? HTTPURLResponse)?.statusCode ?? 0
                        let responseText = String(data: data, encoding: .utf8) ?? "Unknown error"
                        print("❌ Server error - Status: \(statusCode), Response: \(responseText)")
                        
                        // Handle 401 Unauthorized - try to refresh token
                        if statusCode == 401 {
                            print("🔄 401 Unauthorized - requesting token refresh...")
                            AuthBridge.shared.requestTokenRefresh()
                            
                            // Wait for fresh token and retry once
                            let refreshSuccess = await AuthBridge.shared.waitForFreshToken()
                            if refreshSuccess {
                                print("🔄 Retrying request with fresh token...")
                                
                                // Retry the request with fresh token
                                guard let retryUrl = URL(string: urlString),
                                      var retryRequest = createAuthenticatedRequest(url: retryUrl, method: "POST") else {
                                    print("❌ Failed to create retry request")
                                    continuation.finish(throwing: APIError.authenticationRequired)
                                    return
                                }
                                
                                retryRequest.httpBody = try JSONEncoder().encode(messageRequest)
                                let (retryData, retryResponse) = try await session.data(for: retryRequest)
                                
                                guard let retryHttpResponse = retryResponse as? HTTPURLResponse,
                                      retryHttpResponse.statusCode == 200 else {
                                    let retryStatusCode = (retryResponse as? HTTPURLResponse)?.statusCode ?? 0
                                    let retryResponseText = String(data: retryData, encoding: .utf8) ?? "Unknown error"
                                    print("❌ Retry failed - Status: \(retryStatusCode), Response: \(retryResponseText)")
                                    continuation.finish(throwing: APIError.serverError("Failed to send message after token refresh"))
                                    return
                                }
                                
                                // Process successful retry response
                                let retryResponseString = String(data: retryData, encoding: .utf8) ?? ""
                                let retryLines = retryResponseString.components(separatedBy: "\n\n")
                                
                                for line in retryLines {
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
                                return
                            }
                        }
                        
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
              let request = createAuthenticatedRequest(url: url, method: "GET") else {
            throw APIError.authenticationRequired
        }
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError
        }
        
        if httpResponse.statusCode == 401 {
            print("🔄 401 Unauthorized in getMessages - requesting token refresh...")
            AuthBridge.shared.requestTokenRefresh()
            
            let refreshSuccess = await AuthBridge.shared.waitForFreshToken()
            if refreshSuccess {
                print("🔄 Retrying getMessages with fresh token...")
                
                // Retry with fresh token
                guard let retryUrl = URL(string: urlString),
                      let retryRequest = createAuthenticatedRequest(url: retryUrl, method: "GET") else {
                    throw APIError.authenticationRequired
                }
                
                let (retryData, retryResponse) = try await session.data(for: retryRequest)
                
                guard let retryHttpResponse = retryResponse as? HTTPURLResponse,
                      retryHttpResponse.statusCode == 200 else {
                    let retryStatusCode = (retryResponse as? HTTPURLResponse)?.statusCode ?? 0
                    let retryResponseText = String(data: retryData, encoding: .utf8) ?? "Unknown error"
                    print("❌ Retry getMessages failed - Status: \(retryStatusCode), Response: \(retryResponseText)")
                    throw APIError.serverError("Failed to get messages after token refresh")
                }
                
                let messages = try JSONDecoder().decode([ServerMessage].self, from: retryData)
                return messages
            } else {
                throw APIError.serverError("Failed to refresh token for getMessages")
            }
        } else if httpResponse.statusCode == 200 {
            let messages = try JSONDecoder().decode([ServerMessage].self, from: data)
            return messages
        } else {
            let responseText = String(data: data, encoding: .utf8) ?? "Unknown error"
            print("❌ getMessages failed - Status: \(httpResponse.statusCode), Response: \(responseText)")
            throw APIError.serverError("Failed to get messages")
        }
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
