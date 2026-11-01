import Foundation

extension URLRequest {
  mutating func applyGeminiProxyHeaders(
    lane: GeminiLane,
    workload: GeminiWorkloadClass,
    authorization: String,
    localEmbeddings: LocalEmbeddingKillSwitches = .resolve()
  ) {
    setValue(authorization, forHTTPHeaderField: "Authorization")
    setValue(lane.rawValue, forHTTPHeaderField: "X-Omi-Lane")
    setValue(workload.rawValue, forHTTPHeaderField: "X-Omi-Workload")
    setValue(localEmbeddings.isDisabled ? nil : "1", forHTTPHeaderField: "X-Omi-Local-Embeddings")
    setValue("macos", forHTTPHeaderField: "X-Omi-Client-Platform")
  }
}
