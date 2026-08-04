import CryptoKit
import Foundation

enum AgentContextRevision {
  static func make(
    source: AgentContextSource,
    payload: [String: Any],
    outcome: AgentContextSourceOutcome
  ) throws -> String {
    let material: [String: Any] = [
      "source": source.rawValue,
      "outcome": outcome.rawValue,
      "payload": payload,
    ]
    guard JSONSerialization.isValidJSONObject(material) else {
      throw BridgeError.agentError("Context source payload is not valid JSON")
    }
    let data = try JSONSerialization.data(withJSONObject: material, options: [.sortedKeys])
    return "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }
}
