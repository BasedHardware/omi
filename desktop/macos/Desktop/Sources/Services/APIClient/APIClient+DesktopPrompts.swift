import Foundation

/// Remote in-app prompt authored on admin.omi.me (`desktop_prompts` in
/// Firestore) and served by `GET /v2/desktop/prompts`. Adding one needs no
/// app release — clients poll and render natively.
struct RemotePromptSpec: Decodable, Equatable, Identifiable {
  let id: String
  let type: String
  let question: String
  let options: [String]
  let ctaLabel: String?
  let ctaURL: String?
  let triggerKind: String
  let triggerCount: Int

  enum CodingKeys: String, CodingKey {
    case id, type, question, options
    case ctaLabel = "cta_label"
    case ctaURL = "cta_url"
    case triggerKind = "trigger_kind"
    case triggerCount = "trigger_count"
  }
}

struct RemotePromptsResponse: Decodable, Equatable {
  let prompts: [RemotePromptSpec]
}

extension APIClient {
  func getDesktopPrompts(channel: String, build: Int) async throws -> RemotePromptsResponse {
    try await get(
      "v2/desktop/prompts?channel=\(channel)&build=\(build)",
      customBaseURL: DesktopBackendEnvironment.authBaseURL()
    )
  }
}
