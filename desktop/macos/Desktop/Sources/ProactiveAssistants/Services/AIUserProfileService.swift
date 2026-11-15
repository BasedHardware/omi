import Foundation

// MARK: - Model

/// The user's AI profile as the backend stores it (`users/{uid}.ai_user_profile`).
struct AIUserProfile: Equatable, Sendable {
  let profileText: String
  let generatedAt: Date?
  let dataSourcesUsed: Int
  let source: String?
  let refreshedAt: Date?

  /// nil when the backend has no profile or only blank text.
  init?(_ response: AIUserProfileResponse?) {
    guard let response, let text = response.profileText,
      !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return nil }
    profileText = text
    generatedAt = response.generatedAt ?? response.refreshedAt
    dataSourcesUsed = response.dataSourcesUsed ?? 0
    source = response.source
    refreshedAt = response.refreshedAt
  }
}

// MARK: - Errors

/// Why a manual refresh produced no profile. Each case is the message Settings shows.
enum AIUserProfileRefreshError: LocalizedError, Equatable {
  case usageBudgetExhausted
  case alreadyRefreshing
  case insufficientData
  case synthesisFailed
  case rateLimited
  case unavailable

  init(_ error: Error) {
    if let mapped = error as? Self {
      self = mapped
      return
    }
    guard case APIError.httpError(let statusCode, _) = error else {
      self = .unavailable
      return
    }
    switch statusCode {
    case 402: self = .usageBudgetExhausted
    case 409: self = .alreadyRefreshing
    case 422: self = .insufficientData
    case 429: self = .rateLimited
    case 502: self = .synthesisFailed
    default: self = .unavailable
    }
  }

  var errorDescription: String? {
    switch self {
    case .usageBudgetExhausted:
      return "You've reached your plan's AI usage limit. Upgrade or wait for it to reset, then try again."
    case .alreadyRefreshing:
      return "Your profile is already being generated. Try again in a minute."
    case .insufficientData:
      return "There isn't enough to build a profile yet. Keep using Omi and try again later."
    case .synthesisFailed:
      return "Omi couldn't generate your profile just now. Try again later."
    case .rateLimited:
      return "Too many requests. Try again in a few minutes."
    case .unavailable:
      return "Couldn't reach Omi to generate your profile. Check your connection and try again."
    }
  }
}

// MARK: - Client

/// Network seam over the backend profile routes; tests inject a fake.
struct AIUserProfileClient: Sendable {
  var fetch: @Sendable () async throws -> AIUserProfileResponse?
  var refresh: @Sendable () async throws -> AIUserProfileResponse
  var update: @Sendable (String, AIUserProfileEditSource) async throws -> AIUserProfileResponse
  var delete: @Sendable () async throws -> Void

  static let live = AIUserProfileClient(
    fetch: { try await APIClient.shared.getAIUserProfile() },
    refresh: { try await APIClient.shared.refreshAIUserProfile() },
    update: { try await APIClient.shared.updateAIUserProfile(profileText: $0, source: $1) },
    delete: { try await APIClient.shared.deleteAIUserProfile() })
}

// MARK: - Service

/// Reader for the backend-owned AI user profile.
///
/// The backend selects the sources, synthesizes the profile and owns its daily cadence.
/// This actor keeps the last fetched profile in memory so the prompt builders that read
/// it on every turn stay cheap, refreshes that cache when it ages out, and routes the
/// Settings and file-exploration mutations to the backend.
actor AIUserProfileService {
  static let shared = AIUserProfileService()

  /// A cached read older than this is revalidated in the background.
  static let cacheTTL: TimeInterval = 60 * 60
  /// After a failed read, consumers use the cache instead of retrying for this long.
  static let failureBackoff: TimeInterval = 60
  /// Backend limit on `profile_text`.
  static let maxProfileLength = 10_000
  static let explorationSeparator = "\n\n--- File Exploration Insights ---\n"

  private let client: AIUserProfileClient
  private let now: @Sendable () -> Date

  private var cached: AIUserProfile?
  /// When the cache was last confirmed by the backend; nil until the first good read.
  private var cachedAt: Date?
  private var lastFailureAt: Date?
  private var inFlight: Task<AIUserProfile?, Never>?
  private var inFlightID = 0
  private var isRefreshing = false
  /// Bumped on owner switch: nothing started for the previous owner may land in the cache.
  private var ownerEpoch = 0
  /// Bumped on every mutation: a read that started earlier must not overwrite it.
  private var writeRevision = 0

  init(client: AIUserProfileClient = .live, now: @escaping @Sendable () -> Date = { Date() }) {
    self.client = client
    self.now = now
  }

  /// Forget the cached profile (user switch / sign-out). The next read fetches the new owner's.
  func invalidateCache() {
    ownerEpoch += 1
    inFlight = nil
    cached = nil
    cachedAt = nil
    lastFailureAt = nil
  }

  // MARK: Reads

  /// The profile for prompt consumers. Served from memory; only the first read for an
  /// owner waits on the network, and a stale cache is revalidated in the background.
  func getLatestProfile() async -> AIUserProfile? {
    if let lastFailureAt, now().timeIntervalSince(lastFailureAt) < Self.failureBackoff {
      return cached
    }
    guard let cachedAt else { return await fetchProfile() }
    if now().timeIntervalSince(cachedAt) >= Self.cacheTTL {
      _ = startFetch()
    }
    return cached
  }

  /// Read the profile from the backend now (Settings open). Joins a read already in flight;
  /// on failure returns the cached profile.
  @discardableResult
  func fetchProfile() async -> AIUserProfile? {
    await startFetch().value
  }

  private func startFetch() -> Task<AIUserProfile?, Never> {
    if let inFlight { return inFlight }
    let epoch = ownerEpoch
    let revision = writeRevision
    inFlightID += 1
    let id = inFlightID
    let client = client
    let task = Task<AIUserProfile?, Never> {
      let result: Result<AIUserProfile?, Error>
      do {
        result = .success(AIUserProfile(try await client.fetch()))
      } catch {
        result = .failure(error)
      }
      return self.finishFetch(result, id: id, epoch: epoch, revision: revision)
    }
    inFlight = task
    return task
  }

  private func finishFetch(
    _ result: Result<AIUserProfile?, Error>, id: Int, epoch: Int, revision: Int
  ) -> AIUserProfile? {
    guard epoch == ownerEpoch else { return nil }
    if id == inFlightID { inFlight = nil }
    switch result {
    case .success(let profile):
      guard revision == writeRevision else { return cached }
      cached = profile
      cachedAt = now()
      lastFailureAt = nil
    case .failure(let error):
      lastFailureAt = now()
      log("AIUserProfileService: Fetch failed: \(error.localizedDescription)")
    }
    return cached
  }

  // MARK: Mutations

  /// Regenerate on the backend now. Throws `AIUserProfileRefreshError`.
  func refresh() async throws -> AIUserProfile? {
    guard !isRefreshing else { throw AIUserProfileRefreshError.alreadyRefreshing }
    isRefreshing = true
    defer { isRefreshing = false }
    let epoch = ownerEpoch
    do {
      let response = try await client.refresh()
      return store(AIUserProfile(response), epoch: epoch)
    } catch {
      log("AIUserProfileService: Refresh failed: \(error.localizedDescription)")
      throw AIUserProfileRefreshError(error)
    }
  }

  /// Replace the profile text. A user edit is kept by the next synthesis as a correction.
  func updateProfileText(_ text: String, source: AIUserProfileEditSource = .userEdit) async throws
    -> AIUserProfile?
  {
    let epoch = ownerEpoch
    let response = try await client.update(text, source)
    return store(AIUserProfile(response), epoch: epoch)
  }

  /// Delete the profile. The backend generates a new one on its next trigger.
  func deleteProfile() async throws {
    let epoch = ownerEpoch
    try await client.delete()
    _ = store(nil, epoch: epoch)
  }

  /// Fold a file-exploration answer into the profile (or start one with it).
  func appendExploration(_ text: String) async -> Bool {
    let existing = await fetchProfile()?.profileText
    let combined = Self.combine(existing: existing, exploration: text)
    do {
      _ = try await updateProfileText(combined, source: .exploration)
      return true
    } catch {
      log("AIUserProfileService: Failed to save exploration: \(error.localizedDescription)")
      return false
    }
  }

  /// Keep the newest insights whole; trim the older profile to fit the backend limit.
  static func combine(existing: String?, exploration: String) -> String {
    let insights = String(exploration.prefix(maxProfileLength))
    guard let existing, !existing.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return insights
    }
    let room = maxProfileLength - explorationSeparator.count - insights.count
    guard room > 0 else { return insights }
    return String(existing.prefix(room)) + explorationSeparator + insights
  }

  private func store(_ profile: AIUserProfile?, epoch: Int) -> AIUserProfile? {
    guard epoch == ownerEpoch else { return nil }
    writeRevision += 1
    inFlight = nil
    cached = profile
    cachedAt = now()
    lastFailureAt = nil
    return profile
  }
}
