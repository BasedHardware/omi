import Foundation

extension URLRequest {
  mutating func applyGeminiProxyHeaders(
    lane: GeminiLane,
    workload: GeminiWorkloadClass,
    authorization: String
  ) {
    setValue(authorization, forHTTPHeaderField: "Authorization")
    setValue(lane.rawValue, forHTTPHeaderField: "X-Omi-Lane")
    setValue(workload.rawValue, forHTTPHeaderField: "X-Omi-Workload")
    setValue("macos", forHTTPHeaderField: "X-Omi-Client-Platform")
  }
}
