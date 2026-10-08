import Foundation

/// Per-provider health-check pings for BYOK keys. We never activate the free
/// plan with a dead key — that's why onboarding/settings reject unverified keys.
///
/// Each ping hits the provider's cheapest auth-gated endpoint; any 2xx means
/// the key is at least authenticated (it may still have billing issues, but
/// that shows up later as a normal inference error — at least it's not a key
/// shape problem we could have caught up front).
enum BYOKValidator {
  enum Status: Equatable {
    case notChecked
    case checking
    case ok
    /// The provider answered about the key: it does not authenticate.
    case failed(String)
    /// The check produced no verdict about the key — transport failure,
    /// timeout, a provider 5xx, or a rate limit. Never deactivate an
    /// enrollment on this; the next validation retries.
    case transient(String)
  }

  /// True when the outcome says nothing about whether the key works.
  ///
  /// Only a provider verdict (`.ok`, `.failed`) may drive enrollment
  /// activation or teardown. Treating a transient non-answer as a rejection
  /// turned an offline launch or a provider blip into a permanent BYOK
  /// teardown: the key text stayed in Settings, the server-side free-plan
  /// flag flipped off, and every later chat silently rode the managed lane
  /// into billing 402s.
  static func isTransient(_ status: Status) -> Bool {
    if case .transient = status { return true }
    return false
  }

  /// Hit the provider and return whether the key authenticates.
  static func validate(_ provider: BYOKProvider, key: String) async -> Status {
    let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .failed("Empty") }

    switch provider {
    case .openrouter:
      return await ping(
        url: URL(string: "https://openrouter.ai/api/v1/auth/key")!,
        headers: ["Authorization": "Bearer \(trimmed)"]
      )
    case .openai:
      return await ping(
        url: URL(string: "https://api.openai.com/v1/models")!,
        headers: ["Authorization": "Bearer \(trimmed)"]
      )
    case .anthropic:
      return await ping(
        url: URL(string: "https://api.anthropic.com/v1/models?limit=1")!,
        headers: [
          "x-api-key": trimmed,
          "anthropic-version": "2023-06-01",
        ]
      )
    case .gemini:
      var components = URLComponents(string: "https://generativelanguage.googleapis.com/v1beta/models")!
      components.queryItems = [URLQueryItem(name: "key", value: trimmed)]
      return await ping(url: components.url!, headers: [:])
    case .deepgram:
      return await ping(
        url: URL(string: "https://api.deepgram.com/v1/projects")!,
        headers: ["Authorization": "Token \(trimmed)"]
      )
    }
  }

  private static func ping(url: URL, headers: [String: String]) async -> Status {
    var request = URLRequest(url: url)
    request.timeoutInterval = 8
    for (name, value) in headers {
      request.setValue(value, forHTTPHeaderField: name)
    }
    do {
      let (_, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse else {
        return .transient("No HTTP response")
      }
      if (200..<300).contains(http.statusCode) {
        return .ok
      }
      if http.statusCode == 401 || http.statusCode == 403 {
        return .failed("Rejected (HTTP \(http.statusCode))")
      }
      if http.statusCode == 429 || (500...599).contains(http.statusCode) {
        return .transient("HTTP \(http.statusCode)")
      }
      return .failed("HTTP \(http.statusCode)")
    } catch {
      return .transient(error.localizedDescription)
    }
  }

  /// Validate every provider in parallel. Returns map of provider -> status.
  static func validateAll(_ keys: [BYOKProvider: String]) async -> [BYOKProvider: Status] {
    await withTaskGroup(of: (BYOKProvider, Status).self, returning: [BYOKProvider: Status].self) {
      group in
      for (provider, key) in keys {
        group.addTask { (provider, await validate(provider, key: key)) }
      }
      var results: [BYOKProvider: Status] = [:]
      for await (provider, status) in group {
        results[provider] = status
      }
      return results
    }
  }
}
