import Foundation
import OmiWAL

// MARK: - User Settings API

extension APIClient {

  /// Fetches daily summary settings
  func getDailySummarySettings() async throws -> DailySummarySettings {
    return try await get("v1/users/daily-summary-settings")
  }

  /// Updates daily summary settings
  func updateDailySummarySettings(enabled: Bool? = nil, hour: Int? = nil) async throws
    -> DailySummarySettings
  {
    struct UpdateRequest: Encodable {
      let enabled: Bool?
      let hour: Int?
    }
    let body = UpdateRequest(enabled: enabled, hour: hour)
    return try await patch("v1/users/daily-summary-settings", body: body)
  }

  /// Fetches transcription preferences
  func getTranscriptionPreferences() async throws -> TranscriptionPreferences {
    return try await get("v1/users/transcription-preferences")
  }

  /// Updates transcription preferences
  func updateTranscriptionPreferences(singleLanguageMode: Bool? = nil, vocabulary: [String]? = nil)
    async throws -> TranscriptionPreferences
  {
    struct UpdateRequest: Encodable {
      let singleLanguageMode: Bool?
      let vocabulary: [String]?

      enum CodingKeys: String, CodingKey {
        case singleLanguageMode = "single_language_mode"
        case vocabulary
      }
    }
    let body = UpdateRequest(singleLanguageMode: singleLanguageMode, vocabulary: vocabulary)
    struct StatusResponse: Decodable { let status: String }
    let _: StatusResponse = try await patch("v1/users/transcription-preferences", body: body)
    return try await getTranscriptionPreferences()
  }

  /// Fetches user language preference
  func getUserLanguage() async throws -> UserLanguageResponse {
    return try await get("v1/users/language")
  }

  /// Updates user language preference. The PATCH endpoint's response shape differs
  /// from GET's (`{status, single_language_mode}`, not `{language}`) — decoding into
  /// UserLanguageResponse here always threw ("data couldn't be read because it is
  /// missing") even though the backend had already saved the language, silently
  /// (pre-await-fix) or now visibly blocking the caller on a save that succeeded.
  @discardableResult
  func updateUserLanguage(
    _ language: String,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> SetUserLanguageResponse {
    struct UpdateRequest: Encodable {
      let language: String
    }
    let body = UpdateRequest(language: language)
    return try await patch(
      "v1/users/language",
      body: body,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Persists the "how did you hear about Omi" answer to the user's backend
  /// onboarding state (`acquisition_source`). Previously the desktop only wrote
  /// this to local `@AppStorage` + analytics, so the answer never reached the
  /// user record and was lost on reinstall / other devices.
  @discardableResult
  func updateOnboardingAcquisitionSource(
    _ source: String,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> String {
    struct UpdateRequest: Encodable {
      let acquisitionSource: String
      enum CodingKeys: String, CodingKey { case acquisitionSource = "acquisition_source" }
    }
    struct StatusResponse: Decodable { let status: String }
    let response: StatusResponse = try await patch(
      "v1/users/onboarding",
      body: UpdateRequest(acquisitionSource: source),
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    return response.status
  }

  /// Fetches recording permission status
  func getRecordingPermission() async throws -> RecordingPermissionResponse {
    return try await get("v1/users/store-recording-permission")
  }

  /// Sets recording permission
  func setRecordingPermission(enabled: Bool) async throws {
    guard let url = URL(string: baseURL + "v1/users/store-recording-permission?value=\(enabled)") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    try await performVoidRequest(request)
  }

  /// Fetches private cloud sync setting
  func getPrivateCloudSync() async throws -> PrivateCloudSyncResponse {
    return try await get("v1/users/private-cloud-sync")
  }

  /// Sets private cloud sync
  func setPrivateCloudSync(enabled: Bool) async throws {
    guard let url = URL(string: baseURL + "v1/users/private-cloud-sync?value=\(enabled)") else {
      throw APIError.invalidResponse
    }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)

    try await performVoidRequest(request)
  }

  /// Fetches notification settings
  func getNotificationSettings() async throws -> NotificationSettingsResponse {
    return try await get("v1/users/notification-settings")
  }

  /// Updates notification settings
  func updateNotificationSettings(enabled: Bool? = nil, frequency: Int? = nil) async throws
    -> NotificationSettingsResponse
  {
    struct UpdateRequest: Encodable {
      let enabled: Bool?
      let frequency: Int?
    }
    let body = UpdateRequest(enabled: enabled, frequency: frequency)
    return try await patch("v1/users/notification-settings", body: body)
  }

  /// Fetches user profile
  func getUserProfile() async throws -> UserProfileResponse {
    return try await get("v1/users/profile")
  }

  /// Updates user profile (onboarding data)
  func updateUserProfile(
    name: String? = nil, motivation: String? = nil, useCase: String? = nil, job: String? = nil,
    company: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    struct UpdateRequest: Encodable {
      let name: String?
      let motivation: String?
      let use_case: String?
      let job: String?
      let company: String?
    }
    let body = UpdateRequest(
      name: name, motivation: motivation, use_case: useCase, job: job, company: company)
    let _: UserProfileResponse = try await patch(
      "v1/users/profile",
      body: body,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Deletes the authenticated user's account and all server data.
  func deleteAccount() async throws {
    try await delete("v1/users/delete-account")
  }

  // MARK: - Assistant Settings API

  /// Fetches assistant settings from the backend
  func getAssistantSettings() async throws -> AssistantSettingsResponse {
    return try await get("v1/users/assistant-settings")
  }

  /// Updates assistant settings on the backend (partial update — only non-nil fields are changed)
  func updateAssistantSettings(_ settings: AssistantSettingsResponse) async throws
    -> AssistantSettingsResponse
  {
    return try await patch("v1/users/assistant-settings", body: settings)
  }

  /// Fetches server-controlled desktop update/banner policy.
  func getDesktopUpdatePolicy(currentBuild: Int?) async throws -> DesktopUpdatePolicyResponse {
    var endpoint = "v2/desktop/update-policy?platform=macos"
    if let currentBuild {
      endpoint += "&current_build=\(currentBuild)"
    }
    return try await get(endpoint, requireAuth: false, includeBYOK: false)
  }

  // MARK: - Knowledge Graph API

  func getKnowledgeGraph(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KnowledgeGraphResponse {
    try await getKnowledgeGraphImpl(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func getKnowledgeGraphPage(
    limit: Int = KnowledgeGraphResponse.defaultPageSize,
    cursor: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KnowledgeGraphResponse {
    try await getKnowledgeGraphPageImpl(
      limit: limit,
      cursor: cursor,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func rebuildKnowledgeGraph(
    limit: Int = 500,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> RebuildGraphResponse {
    try await rebuildKnowledgeGraphImpl(
      limit: limit,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func deleteKnowledgeGraph() async throws {
    try await deleteKnowledgeGraphImpl()
  }

  func extractKnowledgeGraph(
    text: String,
    includeExisting: Bool = false,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KnowledgeGraphExtractResponse {
    try await extractKnowledgeGraphImpl(
      text: text,
      includeExisting: includeExisting,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func extractMemoryLog(
    text: String,
    textSource: String,
    existingMemories: [String] = [],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> MemoryLogExtractResponse {
    try await extractMemoryLogImpl(
      text: text,
      textSource: textSource,
      existingMemories: existingMemories,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func synthesizeConnectorItems(
    source: String,
    items: [String],
    existingMemories: [String] = [],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ConnectorSynthesisResponse {
    try await synthesizeConnectorItemsImpl(
      source: source,
      items: items,
      existingMemories: existingMemories,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }
}

// MARK: - User Settings Models

/// Daily summary notification settings
struct DailySummarySettings: Codable {
  let enabled: Bool
  let hour: Int
}

/// Transcription preferences
struct TranscriptionPreferences: Codable {
  let singleLanguageMode: Bool
  let vocabulary: [String]

  enum CodingKeys: String, CodingKey {
    case singleLanguageMode = "single_language_mode"
    case vocabulary
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    singleLanguageMode =
      try container.decodeIfPresent(Bool.self, forKey: .singleLanguageMode) ?? false
    vocabulary = try container.decodeIfPresent([String].self, forKey: .vocabulary) ?? []
  }
}

/// User language response (GET /v1/users/language)
struct UserLanguageResponse: Codable {
  let language: String
}

/// Response shape for PATCH /v1/users/language — deliberately distinct from
/// UserLanguageResponse; the backend's set_user_language handler returns
/// {status, single_language_mode}, never {language}.
struct SetUserLanguageResponse: Codable {
  let status: String
  let single_language_mode: Bool
}

/// Recording permission response
struct RecordingPermissionResponse: Codable {
  let enabled: Bool

  enum CodingKeys: String, CodingKey {
    case enabled = "store_recording_permission"
  }
}

/// Private cloud sync response
struct PrivateCloudSyncResponse: Codable {
  let enabled: Bool

  enum CodingKeys: String, CodingKey {
    case enabled = "private_cloud_sync_enabled"
  }
}

/// Notification settings response
struct NotificationSettingsResponse: Codable {
  let enabled: Bool
  let frequency: Int

  /// Frequency level description
  var frequencyDescription: String {
    switch frequency {
    case 0: return "Off"
    case 1: return "Minimal"
    case 2: return "Low"
    case 3: return "Balanced"
    case 4: return "High"
    case 5: return "Maximum"
    default: return "Unknown"
    }
  }
}

enum SubscriptionPlanType: String, Codable {
  case basic  // display "Free"
  case unlimited  // legacy — display "Unlimited (legacy)"
  case architect  // display "Architect" ($400/mo, cost_usd quota)
  case pro  // backward compat: old Firestore docs may still say "pro"
  case `operator`  // new — display "Operator"
}

enum SubscriptionStatusType: String, Codable {
  case active
  case inactive
}

struct SubscriptionLimitsResponse: Codable {
  let transcriptionSeconds: Int?
  let wordsTranscribed: Int?
  let insightsGained: Int?
  let memoriesCreated: Int?

  enum CodingKeys: String, CodingKey {
    case transcriptionSeconds = "transcription_seconds"
    case wordsTranscribed = "words_transcribed"
    case insightsGained = "insights_gained"
    case memoriesCreated = "memories_created"
  }
}

struct UserSubscriptionInfo: Codable {
  let plan: SubscriptionPlanType
  let status: SubscriptionStatusType
  let currentPeriodEnd: Int?
  let stripeSubscriptionId: String?
  let currentPriceId: String?
  let features: [String]
  let cancelAtPeriodEnd: Bool
  let limits: SubscriptionLimitsResponse
  let deprecated: Bool?
  let deprecationMessage: String?

  enum CodingKeys: String, CodingKey {
    case plan, status, features, limits, deprecated
    case currentPeriodEnd = "current_period_end"
    case stripeSubscriptionId = "stripe_subscription_id"
    case currentPriceId = "current_price_id"
    case cancelAtPeriodEnd = "cancel_at_period_end"
    case deprecationMessage = "deprecation_message"
  }
}

struct SubscriptionPriceOption: Codable, Identifiable {
  let id: String
  let title: String
  let description: String?
  let priceString: String

  enum CodingKeys: String, CodingKey {
    case id, title, description
    case priceString = "price_string"
  }
}

struct SubscriptionPlanOption: Codable, Identifiable {
  let id: String
  let title: String
  let subtitle: String?
  let description: String?
  let eyebrow: String?
  let features: [String]
  let prices: [SubscriptionPriceOption]

  init(
    id: String, title: String, subtitle: String? = nil, description: String? = nil, eyebrow: String? = nil,
    features: [String] = [], prices: [SubscriptionPriceOption] = []
  ) {
    self.id = id
    self.title = title
    self.subtitle = subtitle
    self.description = description
    self.eyebrow = eyebrow
    self.features = features
    self.prices = prices
  }
}

struct UserSubscriptionResponse: Codable {
  let subscription: UserSubscriptionInfo
  let transcriptionSecondsUsed: Int
  let transcriptionSecondsLimit: Int
  let wordsTranscribedUsed: Int
  let wordsTranscribedLimit: Int
  let insightsGainedUsed: Int
  let insightsGainedLimit: Int
  let memoriesCreatedUsed: Int
  let memoriesCreatedLimit: Int
  let availablePlans: [SubscriptionPlanOption]
  let showSubscriptionUI: Bool
  // Set for Neo subscribers whose current billing period started before the
  // policy change in #7496 — they retain desktop access until this unix-seconds
  // timestamp (their `current_period_end`). Null for everyone else.
  let desktopGrandfatherUntil: Int?

  enum CodingKeys: String, CodingKey {
    case subscription
    case transcriptionSecondsUsed = "transcription_seconds_used"
    case transcriptionSecondsLimit = "transcription_seconds_limit"
    case wordsTranscribedUsed = "words_transcribed_used"
    case wordsTranscribedLimit = "words_transcribed_limit"
    case insightsGainedUsed = "insights_gained_used"
    case insightsGainedLimit = "insights_gained_limit"
    case memoriesCreatedUsed = "memories_created_used"
    case memoriesCreatedLimit = "memories_created_limit"
    case availablePlans = "available_plans"
    case showSubscriptionUI = "show_subscription_ui"
    case desktopGrandfatherUntil = "desktop_grandfather_until"
  }

  // Defensive decode: only `subscription` is required. The usage counters and
  // plan catalog default when absent so a backend that's behind on schema and
  // omits newer fields like `memories_created_used` doesn't blank the entire
  // Plan & Usage page with "Failed to load plan information."
  init(from decoder: Decoder) throws {
    let c = try decoder.container(keyedBy: CodingKeys.self)
    subscription = try c.decode(UserSubscriptionInfo.self, forKey: .subscription)
    transcriptionSecondsUsed = try c.decodeIfPresent(Int.self, forKey: .transcriptionSecondsUsed) ?? 0
    transcriptionSecondsLimit = try c.decodeIfPresent(Int.self, forKey: .transcriptionSecondsLimit) ?? 0
    wordsTranscribedUsed = try c.decodeIfPresent(Int.self, forKey: .wordsTranscribedUsed) ?? 0
    wordsTranscribedLimit = try c.decodeIfPresent(Int.self, forKey: .wordsTranscribedLimit) ?? 0
    insightsGainedUsed = try c.decodeIfPresent(Int.self, forKey: .insightsGainedUsed) ?? 0
    insightsGainedLimit = try c.decodeIfPresent(Int.self, forKey: .insightsGainedLimit) ?? 0
    memoriesCreatedUsed = try c.decodeIfPresent(Int.self, forKey: .memoriesCreatedUsed) ?? 0
    memoriesCreatedLimit = try c.decodeIfPresent(Int.self, forKey: .memoriesCreatedLimit) ?? 0
    availablePlans = try c.decodeIfPresent([SubscriptionPlanOption].self, forKey: .availablePlans) ?? []
    showSubscriptionUI = try c.decodeIfPresent(Bool.self, forKey: .showSubscriptionUI) ?? true
    desktopGrandfatherUntil = try c.decodeIfPresent(Int.self, forKey: .desktopGrandfatherUntil)
  }
}

struct CheckoutSessionResponse: Codable {
  let url: String?
  let sessionId: String?
  let status: String?
  let message: String?

  enum CodingKeys: String, CodingKey {
    case url, status, message
    case sessionId = "session_id"
  }
}

struct UpgradeSubscriptionResponse: Codable {
  let status: String
  let message: String
  let daysRemaining: Int?
  let scheduleId: String?

  enum CodingKeys: String, CodingKey {
    case status, message
    case daysRemaining = "days_remaining"
    case scheduleId = "schedule_id"
  }
}

struct AvailablePlanPriceOption: Codable, Identifiable {
  let id: String
  let title: String
  let priceString: String
  let description: String?
  let interval: String
  let unitAmount: Int
  let isActive: Bool

  enum CodingKeys: String, CodingKey {
    case id, title, description, interval
    case priceString = "price_string"
    case unitAmount = "unit_amount"
    case isActive = "is_active"
  }
}

struct AvailablePlansResponse: Codable {
  let plans: [AvailablePlanPriceOption]
}

struct OverageInfoResponse: Codable {
  let plan: String
  let planType: String
  let isOveragePlan: Bool
  let includedQuestions: Int?
  let usedQuestions: Int
  let excessQuestions: Int
  let realCostUsd: Double
  let overageUsd: Double
  let markupMultiplier: Double
  let markupPercent: Double
  let resetAt: Int?
  let explainerTitle: String
  let explainerBody: String
  let byokAvailable: Bool

  enum CodingKeys: String, CodingKey {
    case plan
    case planType = "plan_type"
    case isOveragePlan = "is_overage_plan"
    case includedQuestions = "included_questions"
    case usedQuestions = "used_questions"
    case excessQuestions = "excess_questions"
    case realCostUsd = "real_cost_usd"
    case overageUsd = "overage_usd"
    case markupMultiplier = "markup_multiplier"
    case markupPercent = "markup_percent"
    case resetAt = "reset_at"
    case explainerTitle = "explainer_title"
    case explainerBody = "explainer_body"
    case byokAvailable = "byok_available"
  }
}

struct CustomerPortalResponse: Codable {
  let url: String
}

/// Trial metadata from `/v1/users/me/trial` (Python backend) — timing info for countdown UI
struct TrialMetadataResponse: Codable {
  let trialStartedAt: Int?
  let trialEndsAt: Int?
  let trialRemainingSeconds: Int
  let trialExpired: Bool
  let trialDurationSeconds: Int
  let trialFeatures: [String]
  let planAfterTrial: String

  enum CodingKeys: String, CodingKey {
    case trialStartedAt = "trial_started_at"
    case trialEndsAt = "trial_ends_at"
    case trialRemainingSeconds = "trial_remaining_seconds"
    case trialExpired = "trial_expired"
    case trialDurationSeconds = "trial_duration_seconds"
    case trialFeatures = "trial_features"
    case planAfterTrial = "plan_after_trial"
  }
}

/// User profile response
struct UserProfileResponse: Codable {
  let uid: String
  let email: String?
  let name: String?
  let timeZone: String?
  let createdAt: String?
  let motivation: String?
  let useCase: String?
  let job: String?
  let company: String?

  enum CodingKeys: String, CodingKey {
    case uid, email, name, motivation, job, company
    case timeZone = "time_zone"
    case createdAt = "created_at"
    case useCase = "use_case"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    uid = try container.decode(String.self, forKey: .uid)
    email = try container.decodeIfPresent(String.self, forKey: .email)
    name = try container.decodeIfPresent(String.self, forKey: .name)
    timeZone = try container.decodeIfPresent(String.self, forKey: .timeZone)
    createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    motivation = try container.decodeIfPresent(String.self, forKey: .motivation)
    useCase = try container.decodeIfPresent(String.self, forKey: .useCase)
    job = try container.decodeIfPresent(String.self, forKey: .job)
    company = try container.decodeIfPresent(String.self, forKey: .company)
  }
}

// MARK: - Desktop Update Policy Models

struct DesktopUpdatePolicyResponse: Decodable, Equatable, Sendable {
  static let stableManualDownloadURL = URL(
    string: "https://api.omi.me/v2/desktop/download/latest?channel=stable")!

  enum Severity: String, Codable, Sendable {
    case none
    case banner
    case required
  }

  let id: String
  let active: Bool
  let severity: Severity
  let maximumBuildNumber: Int?
  let latestBuildNumber: Int?
  let title: String?
  let message: String?
  let ctaText: String
  let downloadURL: String
  let canDismiss: Bool

  enum CodingKeys: String, CodingKey {
    case id, active, severity, title, message
    case maximumBuildNumber = "maximum_build_number"
    case latestBuildNumber = "latest_build_number"
    case ctaText = "cta_text"
    case downloadURL = "download_url"
    case canDismiss = "can_dismiss"
  }

  init(
    id: String,
    active: Bool,
    severity: Severity,
    maximumBuildNumber: Int?,
    latestBuildNumber: Int?,
    title: String?,
    message: String?,
    ctaText: String,
    downloadURL: String,
    canDismiss: Bool
  ) {
    self.id = id
    self.active = active
    self.severity = severity
    self.maximumBuildNumber = maximumBuildNumber
    self.latestBuildNumber = latestBuildNumber
    self.title = title
    self.message = message
    self.ctaText = ctaText
    self.downloadURL = Self.resolvedDownloadURL(from: downloadURL).absoluteString
    self.canDismiss = canDismiss
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    let id = Self.nonEmptyString(try? container.decode(String.self, forKey: .id)) ?? "current"
    let active = (try? container.decode(Bool.self, forKey: .active)) ?? false
    let severity =
      (try? container.decode(String.self, forKey: .severity))
      .flatMap(Severity.init(rawValue:)) ?? .none
    let maximumBuildNumber = try? container.decode(Int.self, forKey: .maximumBuildNumber)
    let latestBuildNumber = try? container.decode(Int.self, forKey: .latestBuildNumber)
    let title = Self.nonEmptyString(try? container.decode(String.self, forKey: .title))
    let message = Self.nonEmptyString(try? container.decode(String.self, forKey: .message))
    let ctaText =
      Self.nonEmptyString(try? container.decode(String.self, forKey: .ctaText))
      ?? "Download latest"
    let downloadURL = (try? container.decode(String.self, forKey: .downloadURL)) ?? ""
    let canDismiss = (try? container.decode(Bool.self, forKey: .canDismiss)) ?? true

    self.init(
      id: id,
      active: active,
      severity: severity,
      maximumBuildNumber: maximumBuildNumber,
      latestBuildNumber: latestBuildNumber,
      title: title,
      message: message,
      ctaText: ctaText,
      downloadURL: downloadURL,
      canDismiss: canDismiss
    )
  }

  static func resolvedDownloadURL(from candidate: String?) -> URL {
    guard let candidate = nonEmptyString(candidate),
      let url = URL(string: candidate),
      let scheme = url.scheme?.lowercased(),
      ["http", "https"].contains(scheme),
      url.host != nil
    else {
      return stableManualDownloadURL
    }
    return url
  }

  private static func nonEmptyString(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  var isRequired: Bool {
    active && severity == .required
  }
}

// MARK: - Assistant Settings Models

struct SharedAssistantSettingsResponse: Codable {
  var cooldownInterval: Int?
  var glowOverlayEnabled: Bool?
  var analysisDelay: Int?
  var screenAnalysisEnabled: Bool?

  enum CodingKeys: String, CodingKey {
    case cooldownInterval = "cooldown_interval"
    case glowOverlayEnabled = "glow_overlay_enabled"
    case analysisDelay = "analysis_delay"
    case screenAnalysisEnabled = "screen_analysis_enabled"
  }
}

struct TaskSettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var allowedApps: [String]?
  var browserKeywords: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case allowedApps = "allowed_apps"
    case browserKeywords = "browser_keywords"
  }
}

struct InsightSettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var excludedApps: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case excludedApps = "excluded_apps"
  }
}

struct MemorySettingsResponse: Codable {
  var enabled: Bool?
  var analysisPrompt: String?
  var extractionInterval: Double?
  var minConfidence: Double?
  var notificationsEnabled: Bool?
  var excludedApps: [String]?

  enum CodingKeys: String, CodingKey {
    case enabled
    case analysisPrompt = "analysis_prompt"
    case extractionInterval = "extraction_interval"
    case minConfidence = "min_confidence"
    case notificationsEnabled = "notifications_enabled"
    case excludedApps = "excluded_apps"
  }
}

struct FloatingBarSettingsResponse: Codable {
  var voiceAnswersEnabled: Bool?
  var elevenlabsVoiceId: String?

  enum CodingKeys: String, CodingKey {
    case voiceAnswersEnabled = "voice_answers_enabled"
    case elevenlabsVoiceId = "elevenlabs_voice_id"
  }
}

enum AssistantSettingsJSONValue: Codable, Equatable {
  case null
  case bool(Bool)
  case int(Int)
  case double(Double)
  case string(String)
  case array([AssistantSettingsJSONValue])
  case object([String: AssistantSettingsJSONValue])

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    if container.decodeNil() {
      self = .null
    } else if let value = try? container.decode(Bool.self) {
      self = .bool(value)
    } else if let value = try? container.decode(Int.self) {
      self = .int(value)
    } else if let value = try? container.decode(Double.self) {
      self = .double(value)
    } else if let value = try? container.decode(String.self) {
      self = .string(value)
    } else if let value = try? container.decode([AssistantSettingsJSONValue].self) {
      self = .array(value)
    } else if let value = try? container.decode([String: AssistantSettingsJSONValue].self) {
      self = .object(value)
    } else {
      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Unsupported assistant settings JSON value")
    }
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    switch self {
    case .null:
      try container.encodeNil()
    case .bool(let value):
      try container.encode(value)
    case .int(let value):
      try container.encode(value)
    case .double(let value):
      try container.encode(value)
    case .string(let value):
      try container.encode(value)
    case .array(let value):
      try container.encode(value)
    case .object(let value):
      try container.encode(value)
    }
  }
}

struct AssistantSettingsResponse: Codable {
  var shared: SharedAssistantSettingsResponse?
  var task: TaskSettingsResponse?
  var insight: InsightSettingsResponse?
  var memory: MemorySettingsResponse?
  var floatingBar: FloatingBarSettingsResponse?
  var updateChannel: String?
  var unknownSections: [String: AssistantSettingsJSONValue]

  enum CodingKeys: String, CodingKey, CaseIterable {
    case shared, task
    case insight = "advice"
    case memory
    case floatingBar = "floating_bar"
    case updateChannel = "update_channel"
  }

  init(
    shared: SharedAssistantSettingsResponse? = nil,
    task: TaskSettingsResponse? = nil,
    insight: InsightSettingsResponse? = nil,
    memory: MemorySettingsResponse? = nil,
    floatingBar: FloatingBarSettingsResponse? = nil,
    updateChannel: String? = nil,
    unknownSections: [String: AssistantSettingsJSONValue] = [:]
  ) {
    self.shared = shared
    self.task = task
    self.insight = insight
    self.memory = memory
    self.floatingBar = floatingBar
    self.updateChannel = updateChannel
    self.unknownSections = unknownSections
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    shared = Self.decodeLossy(SharedAssistantSettingsResponse.self, from: container, forKey: .shared)
    task = Self.decodeLossy(TaskSettingsResponse.self, from: container, forKey: .task)
    insight = Self.decodeLossy(InsightSettingsResponse.self, from: container, forKey: .insight)
    memory = Self.decodeLossy(MemorySettingsResponse.self, from: container, forKey: .memory)
    floatingBar = Self.decodeLossy(
      FloatingBarSettingsResponse.self, from: container, forKey: .floatingBar)
    updateChannel = Self.decodeLossy(String.self, from: container, forKey: .updateChannel)

    let rawContainer = try decoder.container(keyedBy: AssistantSettingsDynamicCodingKey.self)
    let knownKeys = Set(CodingKeys.allCases.map(\.rawValue))
    unknownSections = rawContainer.allKeys.reduce(into: [:]) { result, key in
      guard !knownKeys.contains(key.stringValue),
        let value = try? rawContainer.decode(AssistantSettingsJSONValue.self, forKey: key)
      else { return }
      result[key.stringValue] = value
    }
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encodeIfPresent(shared, forKey: .shared)
    try container.encodeIfPresent(task, forKey: .task)
    try container.encodeIfPresent(insight, forKey: .insight)
    try container.encodeIfPresent(memory, forKey: .memory)
    try container.encodeIfPresent(floatingBar, forKey: .floatingBar)
    try container.encodeIfPresent(updateChannel, forKey: .updateChannel)

    var rawContainer = encoder.container(keyedBy: AssistantSettingsDynamicCodingKey.self)
    let knownKeys = Set(CodingKeys.allCases.map(\.rawValue))
    for (key, value) in unknownSections where !knownKeys.contains(key) {
      try rawContainer.encode(value, forKey: AssistantSettingsDynamicCodingKey(stringValue: key))
    }
  }

  private static func decodeLossy<T: Decodable>(
    _ type: T.Type,
    from container: KeyedDecodingContainer<CodingKeys>,
    forKey key: CodingKeys
  ) -> T? {
    do {
      return try container.decodeIfPresent(type, forKey: key)
    } catch {
      return nil
    }
  }
}

struct AssistantSettingsDynamicCodingKey: CodingKey {
  let stringValue: String
  let intValue: Int?

  init(stringValue: String) {
    self.stringValue = stringValue
    intValue = nil
  }

  init(intValue: Int) {
    stringValue = String(intValue)
    self.intValue = intValue
  }
}

// MARK: - Insight API

extension APIClient {

}
