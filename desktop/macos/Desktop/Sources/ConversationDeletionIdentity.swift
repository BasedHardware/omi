import CryptoKit
import Foundation

/// Mirrors the backend UUIDv5 from-segments identity; timestamps alone are never a delete join.
enum ConversationDeletionIdentity {
  static func fromSegmentsID(uid: String, clientSessionID: String) -> String {
    var namespace = UUID(uuidString: "fb2f1f36-3c84-47a4-9c62-b3f6fdb3fd13")!.uuid
    var bytes = withUnsafeBytes(of: &namespace) { Array($0) }
    bytes.append(contentsOf: "\(uid)\0\(clientSessionID)".utf8)
    var hash = Array(Insecure.SHA1.hash(data: Data(bytes)).prefix(16))
    hash[6] = (hash[6] & 0x0f) | 0x50
    hash[8] = (hash[8] & 0x3f) | 0x80
    let hex = hash.map { String(format: "%02x", $0) }
    return [hex[0..<4], hex[4..<6], hex[6..<8], hex[8..<10], hex[10..<16]]
      .map { $0.joined() }.joined(separator: "-")
  }

  static func matches(_ session: TranscriptionSessionRecord, conversationID: String, uid: String?) -> Bool {
    if session.backendId == conversationID { return true }
    // A bound row belongs to that backend ID, even if its old client ID differs.
    guard session.backendId?.isEmpty != false else { return false }
    if session.clientConversationId == conversationID { return true }
    guard let uid, let id = session.id else { return false }
    return fromSegmentsID(
      uid: uid,
      clientSessionID: ConversationFinalizationService.localClientConversationId(session: session, sessionId: id)
    ) == conversationID
  }
}
