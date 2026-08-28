import OmiTheme
import SwiftUI

// MARK: - Policy

/// Decides when the one-time "rate Omi Desktop" ask is due. Pure so the
/// trigger contract stays unit-testable: the prompt appears once the user has
/// asked their 3rd question (or the server-configured threshold), and never
/// again after a submit or a dismiss.
enum RatingPromptPolicy {
  static let questionThreshold = 3
  /// Remote kill switch (PostHog feature flag, preloaded at analytics init).
  /// Kill-switch polarity: enabling the flag DISABLES the prompt, so an unset
  /// or unreachable flag (dev builds never initialize PostHog) changes nothing.
  static let killSwitchFlag = "desktop-rating-prompt-disabled"

  static func shouldShow(
    questionCount: Int,
    submittedRating: Int,
    dismissed: Bool,
    remotelyDisabled: Bool = false,
    enabled: Bool = true,
    questionThreshold: Int = RatingPromptPolicy.questionThreshold
  ) -> Bool {
    enabled && !remotelyDisabled && questionCount >= questionThreshold && submittedRating == 0 && !dismissed
  }

  /// Pure comment gate: only a low score (≤ commentMaxScore, from the
  /// server config) is asked for an optional comment before completing.
  static func shouldAskForComment(score: Int, commentMaxScore: Int) -> Bool {
    score <= commentMaxScore
  }
}

// MARK: - Manager

/// Owns the rating-prompt lifecycle: counts asked questions (fed by the
/// single `AnalyticsManager.chatMessageSent` funnel every chat surface goes
/// through), decides visibility, and reports the submitted rating to PostHog
/// so admin.omi.me can chart it daily.
@MainActor
final class RatingPromptManager: ObservableObject {
  static let shared = RatingPromptManager()

  /// Server-driven copy/trigger/threshold config. Starts from the last-good
  /// cached value (or hardcoded defaults) so a cold start needs no network;
  /// `startConfigPolling()` refreshes it while signed in.
  @Published private(set) var config: CsatConfig = RatingPromptManager.cachedConfig() ?? .fallback

  /// Set between the star tap and Send/Skip on a low score: the bar stays
  /// up and shows the comment field instead of the stars. Nothing is
  /// persisted while a comment is pending.
  @Published private(set) var commentPendingScore: Int?

  /// Seam for tests and the automation bridge; assigned in init (a default
  /// value cannot reference the MainActor-isolated APIClient).
  var configFetch: () async throws -> CsatConfig
  /// Same cadence as RemotePromptEngine: admin copy edits reach the bar
  /// within one poll (~5 minutes) plus the backend's 60s config cache.
  static let configPollInterval: TimeInterval = 300

  private var configPollTask: Task<Void, Never>?
  private var lastConfigFetchFailed = false
  @Published private(set) var isVisible = false

  private let defaults = UserDefaults.standard
  private var flagObserver: NSObjectProtocol?
  private var flagPollTask: Task<Void, Never>?
  private var migratedOwners = Set<String>()

  /// Injectable for tests; production scopes all prompt state to the signed-in
  /// account so a switch never inherits another account's answers (#9821 class).
  var ownerProvider: () -> String = { RuntimeOwnerIdentity.currentOwnerId() ?? "anonymous" }

  private func scopedKey(_ field: String) -> ScopedDefaultsKey {
    let owner = ownerProvider()
    if !migratedOwners.contains(owner) {
      migratedOwners.insert(owner)
      migrateLegacyGlobalState(to: owner)
    }
    return .ratingPrompt(field, ownerID: owner)
  }

  /// The first shipped build stored this state device-globally; the account
  /// signed in when the scoped build first runs inherits it (correct for the
  /// overwhelmingly common single-account Mac, and prevents re-prompting
  /// users who already answered), then the global keys are removed.
  private func migrateLegacyGlobalState(to owner: String) {
    let legacy: [(DefaultsKey, String)] = [
      (.ratingPromptQuestionCount, "questionCount"),
      (.ratingPromptSubmittedRating, "submittedRating"),
      (.ratingPromptDismissed, "dismissed"),
      (.ratingPromptHistorySeeded, "historySeeded"),
    ]
    for (globalKey, field) in legacy {
      if let value = defaults.object(forKey: globalKey.rawValue) {
        let scoped = ScopedDefaultsKey.ratingPrompt(field, ownerID: owner)
        if defaults.object(forKey: scoped) == nil {
          defaults.set(value, forKey: scoped)
        }
        defaults.removeObject(forKey: globalKey.rawValue)
      }
    }
  }

  /// Injectable for tests; production reads the preloaded PostHog flag.
  var remoteDisableCheck: () -> Bool = {
    PostHogManager.shared.isFeatureEnabled(RatingPromptPolicy.killSwitchFlag)
  }

  private init() {
    historyFetch = { owner in
      try await APIClient.shared.getMessages(
        limit: 100, expectedOwnerId: owner == "anonymous" ? nil : owner)
    }
    configFetch = {
      try await APIClient.shared.getCsatConfig()
    }
    refresh()
    // Sign-out is an owner transition too: hide immediately, not at the next
    // question. Sign-IN transitions arrive via the owner-keyed task in
    // DesktopHomeView calling ownerDidChange().
    NotificationCenter.default.addObserver(
      forName: .userDidSignOut, object: nil, queue: nil
    ) { _ in
      Task { @MainActor in RatingPromptManager.shared.ownerDidChange() }
    }
    // The kill switch must not wait for the next question: recompute whenever
    // PostHog delivers a flag payload (initial preload can finish AFTER this
    // singleton initializes, and reloads deliver mid-session flips).
    flagObserver = NotificationCenter.default.addObserver(
      forName: PostHogManager.featureFlagsDidLoad,
      object: nil, queue: nil
    ) { _ in
      Task { @MainActor in RatingPromptManager.shared.flagsDidUpdate() }
    }
  }

  func flagsDidUpdate() {
    refresh()
  }

  /// The signed-in owner changed (switch, sign-in, sign-out): recompute all
  /// cached state for the NEW owner's keys immediately — cached isVisible /
  /// thank-you from the previous account must never survive a switch.
  func ownerDidChange() {
    thankYouRating = nil
    refresh()
  }

  var questionCount: Int {
    defaults.object(forKey: scopedKey("questionCount")) as? Int ?? 0
  }

  var submittedRating: Int {
    defaults.object(forKey: scopedKey("submittedRating")) as? Int ?? 0
  }

  var isDismissed: Bool {
    defaults.object(forKey: scopedKey("dismissed")) as? Bool ?? false
  }

  func recordQuestionAsked() {
    defaults.set(questionCount + 1, forKey: scopedKey("questionCount"))
    refresh()
    // Remote prompts share the same accepted-question seam: only sends the
    // chat provider accepted reach here, so both counters agree by
    // construction.
    RemotePromptEngine.shared.recordQuestionAsked()
  }

  /// Rating just submitted this session — drives the thank-you state. 4-5
  /// star raters get a refer-a-friend proposal; lower ratings auto-hide.
  @Published private(set) var thankYouRating: Int?

  func submit(rating: Int) {
    let clamped = min(max(rating, 1), 5)
    if RatingPromptPolicy.shouldAskForComment(score: clamped, commentMaxScore: config.commentMaxScore) {
      // Low score: keep the bar up (stars stay replaced by the comment
      // field) and persist nothing until Send or Skip.
      commentPendingScore = clamped
      return
    }
    finalizeSubmission(rating: clamped, comment: "")
  }

  /// Send button: complete the pending low score with the typed comment.
  func submitPendingComment(_ comment: String) {
    guard let score = commentPendingScore else { return }
    finalizeSubmission(rating: score, comment: comment)
  }

  /// Skip button: complete the pending low score with an empty comment.
  func skipPendingComment() {
    guard let score = commentPendingScore else { return }
    finalizeSubmission(rating: score, comment: "")
  }

  private func finalizeSubmission(rating: Int, comment: String) {
    let clamped = min(max(rating, 1), 5)
    commentPendingScore = nil
    defaults.set(clamped, forKey: scopedKey("submittedRating"))
    AnalyticsManager.shared.desktopRatingSubmitted(rating: clamped, revision: config.revision)
    thankYouRating = clamped
    refresh()
    submitToBackend(rating: clamped, comment: comment)
    if clamped < 4 {
      Task { @MainActor in
        try? await Task.sleep(nanoseconds: 6_000_000_000)
        if self.thankYouRating == clamped { self.closeThankYou() }
      }
    }
  }

  /// Best-effort backend persist (`POST /v1/csat/ratings`): the local record
  /// and the PostHog event already happened, so a failure degrades telemetry,
  /// never the thank-you UX. The comment text itself is never logged.
  private func submitToBackend(rating: Int, comment: String) {
    let revision = config.revision
    Task { @MainActor in
      do {
        _ = try await APIClient.shared.submitCsatRating(
          score: rating, comment: comment, revision: revision)
      } catch {
        if case APIError.httpError(let statusCode, _) = error, statusCode == 409 {
          // Already submitted (retry / double-tap): success locally, and the
          // ask must never resurface.
        } else {
          DesktopDiagnosticsManager.shared.recordFallback(
            area: "other",
            from: "remote_config",
            to: "local_defaults",
            reason: "other",
            outcome: .degraded)
          log("RatingPrompt: CSAT submit failed (kept locally): \(error.localizedDescription)")
        }
      }
    }
  }

  func closeThankYou() {
    thankYouRating = nil
    RemotePromptEngine.shared.builtInAskChanged()
  }

  func referFriend() {
    thankYouRating = nil
    NotificationCenter.default.post(name: .openReferralSheet, object: nil)
    RemotePromptEngine.shared.builtInAskChanged()
  }

  func dismiss() {
    // A dismiss during comment entry abandons the pending rating too —
    // the bar must not outlive the X that closed it.
    commentPendingScore = nil
    defaults.set(true, forKey: scopedKey("dismissed"))
    refresh()
  }

  /// Users who already asked 3+ questions before this build ship must see
  /// the ask on their NEXT LAUNCH, not after three more questions: a one-shot
  /// seed of the counter from server chat history. Fetch failure leaves the
  /// marker unset so the next launch retries.
  /// Injectable for tests; production asks the backend for the owner's own
  /// messages, owner-asserted end to end (expectedOwnerId). Assigned in init
  /// (APIClient is actor-isolated, so it cannot be a property default).
  var historyFetch: (String) async throws -> [ChatMessageDB]
  /// Injectable for tests; production reads the real auth state.
  var isSignedInCheck: () -> Bool = { AuthState.shared.isSignedIn }

  func seedFromHistoryIfNeeded() async {
    // Same launch seam: every caller that seeds also starts the config poll.
    startConfigPolling()
    // Owner-fenced: the seed reads and WRITES the account that started it.
    // The fetch carries expectedOwnerId, and if the signed-in owner changed
    // while the request was in flight the result is discarded — account B
    // must never be seeded from account A's history.
    let owner = ownerProvider()
    // The fetched threshold if the config poll has landed, else the default.
    let threshold = config.questionThreshold
    guard !(defaults.object(forKey: scopedKey("historySeeded")) as? Bool ?? false) else { return }
    guard submittedRating == 0, !isDismissed,
      questionCount < threshold
    else {
      defaults.set(true, forKey: scopedKey("historySeeded"))
      return
    }
    // Launch timing: auth/session may not be ready at first .task — retry a
    // few times before deferring to the next launch (marker stays unset).
    var history: [ChatMessageDB] = []
    var fetched = false
    for attempt in 1...5 {
      guard ownerProvider() == owner, !Task.isCancelled else { return }
      if isSignedInCheck(),
        let result = try? await historyFetch(owner)
      {
        history = result
        fetched = true
        break
      }
      log("RatingPrompt: history seed attempt \(attempt) not ready, retrying")
      try? await Task.sleep(nanoseconds: 15_000_000_000)
    }
    guard fetched, ownerProvider() == owner, !Task.isCancelled else { return }
    let asked = history.filter { $0.sender == "human" }.count
    log("RatingPrompt: history seed fetched \(history.count) messages, \(asked) questions")
    if asked >= threshold {
      // Merge, never decrease: questions asked live while the history fetch
      // was in flight already advanced the persisted count past the seed
      // value, and the seed must not roll that back.
      defaults.set(
        max(questionCount, threshold),
        forKey: scopedKey("questionCount"))
    }
    defaults.set(true, forKey: scopedKey("historySeeded"))
    refresh()
  }

  /// Automation/testing hook: rewind the persisted state so the real trigger
  /// path can be exercised repeatedly on a dev bundle.
  func resetForTesting() {
    thankYouRating = nil
    commentPendingScore = nil
    for field in ["historySeeded", "questionCount", "submittedRating", "dismissed"] {
      defaults.removeObject(forKey: scopedKey(field))
    }
    refresh()
    // Allow migration to be exercised again after a test reset.
    migratedOwners.removeAll()
  }

  var isRemotelyDisabled: Bool {
    remoteDisableCheck()
  }

  // MARK: Server config

  /// Fetch the CSAT config now, then every `configPollInterval` while signed
  /// in — same cadence as RemotePromptEngine, called from the same launch
  /// `.task` next to `seedFromHistoryIfNeeded()`.
  func startConfigPolling() {
    guard configPollTask == nil else { return }
    configPollTask = Task { @MainActor [weak self] in
      while !Task.isCancelled {
        if let self, self.isSignedInCheck() {
          await self.refreshConfigFromServer()
        }
        try? await Task.sleep(nanoseconds: UInt64(Self.configPollInterval * 1_000_000_000))
      }
    }
  }

  func refreshConfigFromServer() async {
    do {
      let fetched = try await configFetch()
      config = fetched
      persistConfig(fetched)
      lastConfigFetchFailed = false
      // enabled / threshold may have changed whether the ask is due.
      refresh()
    } catch {
      // Fail-open: keep last-good (or hardcoded defaults). An `enabled=false`
      // only ever applies after a successful fetch; the PostHog kill switch
      // still applies on this branch.
      if !lastConfigFetchFailed {
        // One diagnostics event per outage, not one per 5-minute poll.
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "other",
          from: "remote_config",
          to: "local_defaults",
          reason: "other",
          outcome: .degraded)
      }
      lastConfigFetchFailed = true
      log("RatingPrompt: CSAT config fetch failed, keeping last-good: \(error.localizedDescription)")
    }
  }

  private func persistConfig(_ value: CsatConfig) {
    if let data = try? JSONEncoder().encode(value) {
      defaults.set(data, forKey: DefaultsKey.csatConfigLastGood.rawValue)
    }
  }

  private static func cachedConfig() -> CsatConfig? {
    guard
      let data = UserDefaults.standard.data(forKey: DefaultsKey.csatConfigLastGood.rawValue)
    else { return nil }
    return try? JSONDecoder().decode(CsatConfig.self, from: data)
  }

  private func refresh() {
    isVisible = RatingPromptPolicy.shouldShow(
      questionCount: questionCount,
      submittedRating: submittedRating,
      dismissed: isDismissed,
      remotelyDisabled: isRemotelyDisabled,
      enabled: config.enabled,
      questionThreshold: config.questionThreshold)
    // Deferred: refresh() runs inside this singleton's own `static let`
    // initialization, and RemotePromptEngine.builtInAskChanged() reads
    // RatingPromptManager.shared back — a synchronous call would re-enter the
    // still-initializing static let (startup deadlock). The async hop runs
    // after init completes.
    Task { @MainActor in RemotePromptEngine.shared.builtInAskChanged() }
    // While the prompt is on screen, poll for a remote disable so an active
    // kill switch takes effect within minutes, not at the next app launch.
    if isVisible, flagPollTask == nil {
      flagPollTask = Task { @MainActor [weak self] in
        while let self, self.isVisible, !Task.isCancelled {
          try? await Task.sleep(nanoseconds: 5 * 60 * 1_000_000_000)
          PostHogManager.shared.reloadFeatureFlags()
        }
        self?.flagPollTask = nil
      }
    } else if !isVisible {
      flagPollTask?.cancel()
      flagPollTask = nil
    }
  }
}

// MARK: - View

enum RatingPromptButtonStyle {
  static let referralKind: OmiButtonStyle.Kind = .primary
  static let referralSize: OmiButtonStyle.Size = .compact
}

/// Closable sticky bar pinned to the bottom of the main window asking
/// "How would you rate Omi Desktop?" with 1–5 stars.
struct RatingPromptBar: View {
  @ObservedObject private var manager = RatingPromptManager.shared
  @State private var hoveredStar = 0
  @State private var commentDraft = ""

  var body: some View {
    if let rating = manager.thankYouRating {
      thankYouContent(rating: rating)
    } else if manager.commentPendingScore != nil {
      // Low score awaiting an optional comment: the bar stays up so the
      // built-in ask keeps right of way in RemotePromptEngine.
      commentContent
    } else if manager.isVisible {
      starsContent
    }
  }

  private var starsContent: some View {
    barChrome {
      VStack(alignment: .leading, spacing: 2) {
        Text(manager.config.title)
          .font(.system(size: 13, weight: .medium))
          .foregroundColor(.primary)
        if !manager.config.body.isEmpty {
          Text(manager.config.body)
            .font(.system(size: 12))
            .foregroundColor(.secondary)
        }
      }
      HStack(spacing: OmiSpacing.xs) {
        ForEach(1...5, id: \.self) { star in
          Button {
            manager.submit(rating: star)
          } label: {
            Image(systemName: star <= hoveredStar ? "star.fill" : "star")
              .font(.system(size: 15))
              .foregroundColor(star <= hoveredStar ? .yellow : .secondary)
          }
          .buttonStyle(.plain)
          .onHover { inside in
            if inside {
              hoveredStar = star
            } else if hoveredStar == star {
              hoveredStar = star - 1
            }
          }
          .accessibilityLabel("Rate \(star) star\(star == 1 ? "" : "s")")
        }
      }

      closeButton { manager.dismiss() }
    }
  }

  private func thankYouContent(rating: Int) -> some View {
    barChrome {
      Text(manager.config.thankYouText)
        .font(.system(size: 13, weight: .semibold))
        .foregroundColor(.primary)

      if rating >= 4 {
        Text(manager.config.referCtaText)
          .font(.system(size: 13))
          .foregroundColor(.secondary)
        Button("Refer a friend") {
          manager.referFriend()
        }
        .buttonStyle(
          OmiButtonStyle(
            RatingPromptButtonStyle.referralKind,
            size: RatingPromptButtonStyle.referralSize))
      }

      closeButton { manager.closeThankYou() }
    }
  }

  /// Low-score follow-up: one-line optional comment (≤ 500 chars) plus Send
  /// and Skip — both complete the submission through the manager; the X
  /// still dismisses forever. No rating is persisted while this is showing.
  private var commentContent: some View {
    barChrome {
      Text("Tell us more (optional)")
        .font(.system(size: 13, weight: .medium))
        .foregroundColor(.primary)

      TextField("What can we improve?", text: $commentDraft)
        .textFieldStyle(.plain)
        .font(.system(size: 13))
        .foregroundColor(Ink.primary)
        .padding(.horizontal, OmiSpacing.md)
        .frame(width: 320, alignment: .leading)
        .frame(minHeight: 30)
        // Same quiet field surface as OmiSearchField, at the bar's radius so
        // the row reads as one chrome — no system blue focus ring.
        .glassField(cornerRadius: 10)
        .onSubmit { manager.submitPendingComment(commentDraft) }
        .onChange(of: commentDraft) { _, newValue in
          if newValue.count > 500 {
            commentDraft = String(newValue.prefix(500))
          }
        }
        .accessibilityLabel("Rating comment")

      Button("Send") {
        manager.submitPendingComment(commentDraft)
      }
      .buttonStyle(
        OmiButtonStyle(
          RatingPromptButtonStyle.referralKind,
          size: RatingPromptButtonStyle.referralSize))

      Button("Skip") {
        manager.skipPendingComment()
      }
      .buttonStyle(OmiButtonStyle(.secondary, size: .compact))

      closeButton { manager.dismiss() }
    }
  }

  private func closeButton(_ action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Image(systemName: "xmark")
        .font(.system(size: 11, weight: .semibold))
        .foregroundColor(.secondary)
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Dismiss rating prompt")
  }

  private func barChrome<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
    HStack(spacing: OmiSpacing.lg) {
      content()
    }
    .padding(.horizontal, OmiSpacing.xl)
    .padding(.vertical, OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: 10)
        .fill(.regularMaterial)
        .overlay(
          RoundedRectangle(cornerRadius: 10)
            .stroke(Color.primary.opacity(0.08), lineWidth: 1)
        )
    )
    // Clears the chat composer row pinned to the window's bottom edge —
    // the prompt must never sit on top of the field the user types in.
    .padding(.bottom, 76)
    .transition(.move(edge: .bottom).combined(with: .opacity))
  }
}
