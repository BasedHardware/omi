import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var hasPaidSubscription: Bool {
    guard let subscription = userSubscription?.subscription else { return false }
    if subscription.features.contains("byok") { return false }
    return subscription.plan != .basic && subscription.status == .active
  }

  var shouldShowPlanPurchaseOptions: Bool {
    !subscriptionPlansForDisplay.isEmpty
  }

  var subscriptionPlansForDisplay: [SubscriptionPlanOption] {
    // Operator (mass-market, green) on the left, Architect (premium, purple)
    // on the right. Hide the user's current plan — they already see it above.
    // Neo ($20) | Operator ($49) | Architect ($200) — cheapest to premium
    let order = ["unlimited": 0, "operator": 1, "architect": 2]
    return mergedPlanCatalog
      .filter { !isCurrentSubscriptionPlan($0) }
      .sorted { lhs, rhs in
        let lhsOrder = order[lhs.id, default: Int.max]
        let rhsOrder = order[rhs.id, default: Int.max]
        if lhsOrder != rhsOrder {
          return lhsOrder < rhsOrder
        }
        return lhs.title < rhs.title
      }
  }

  var currentPlanTitle: String {
    guard let subscription = userSubscription?.subscription else {
      return isLoadingSubscription ? "Loading plan..." : "Free"
    }
    // BYOK users: the backend returns plan=unlimited to turn off metering
    // but that's an implementation detail — to the user, they're on the
    // free plan because they pay the providers directly, not Omi.
    if subscription.features.contains("byok") {
      return "Free (BYOK)"
    }
    switch subscription.plan {
    case .basic:
      return "Free"
    case .unlimited:
      // Backend serializes Operator subscribers as plan="unlimited" for
      // backward compat with old mobile builds that don't know the
      // `operator` enum. Distinguish by matching current_price_id against
      // an Operator-titled plan in the catalog.
      if isCurrentSubscriptionOperator() {
        return "Operator"
      }
      return "Neo"
    case .architect, .pro:
      return "Architect"
    case .operator:
      return "Operator"
    }
  }

  /// Returns true when the user's current Stripe price maps to a plan the
  /// backend is calling "Operator". Protects against the wire-level
  /// Operator→Unlimited remapping in `/v1/users/me/subscription`.
  func isCurrentSubscriptionOperator() -> Bool {
    guard let subscription = userSubscription?.subscription,
          let currentPriceId = subscription.currentPriceId
    else { return false }
    for plan in mergedPlanCatalog {
      guard plan.title == "Operator" else { continue }
      if plan.prices.contains(where: { $0.id == currentPriceId }) {
        return true
      }
    }
    return false
  }

  var currentPlanSubtitle: String {
    if isLoadingSubscription {
      return "Fetching subscription details from omi."
    }
    if let detail = currentPlanBillingDetail {
      return detail
    }
    if hasPaidSubscription {
      return "Your paid plan is active."
    }
    return "You are currently on the free tier."
  }

  var currentPlanBillingDetail: String? {
    guard hasPaidSubscription,
      let subscription = userSubscription?.subscription,
      let currentPriceId = subscription.currentPriceId
    else {
      return nil
    }

    for plan in mergedPlanCatalog {
      if let price = plan.prices.first(where: { $0.id == currentPriceId }) {
        return "\(plan.title) \(price.title) • \(price.priceString)"
      }
    }

    return nil
  }

  var currentPlanPeriodText: String? {
    guard let subscription = userSubscription?.subscription else { return nil }
    guard hasPaidSubscription, let periodEnd = subscription.currentPeriodEnd else { return nil }
    let date = Date(timeIntervalSince1970: TimeInterval(periodEnd))
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    let prefix = subscription.cancelAtPeriodEnd ? "Access ends" : "Renews"
    return "\(prefix) on \(formatter.string(from: date))"
  }

  func planSubtitle(for planId: String) -> String? {
    switch planId {
    case "unlimited":
      return "200 questions per month"
    case "operator":
      return "500 questions per month"
    case "architect":
      return "Power-user AI — thousands of chats + agentic automations"
    default:
      return nil
    }
  }

  func planAccentColor(for planId: String) -> Color {
    // Architect is the premium/purple tier; Operator + legacy Unlimited
    // are the mass-market green tier.
    planId == "architect" ? OmiColors.purplePrimary : OmiColors.success
  }

  func planSummaryText(for plan: SubscriptionPlanOption) -> String {
    preferredStartingPrice(for: plan)?.priceString ?? ""
  }

  func preferredStartingPrice(for plan: SubscriptionPlanOption) -> SubscriptionPriceOption?
  {
    let prices = sortedPrices(for: plan)
    if let monthly = prices.first(where: { price in
      let title = price.title.lowercased()
      return title.contains("month")
    }) {
      return monthly
    }
    return prices.first
  }

  func planEyebrow(for planId: String) -> String {
    switch planId {
    case "unlimited":
      return "Starter"
    case "operator":
      return "Most popular"
    case "architect":
      return "Automation + coding"
    default:
      return "Plan"
    }
  }

  func planDescription(for planId: String) -> String {
    switch planId {
    case "unlimited":
      return "100 chat questions per month. Shared with mobile and web."
    case "operator":
      return "500 chat questions per month. Shared with mobile and web."
    case "architect":
      return "Power-user AI for heavy agentic workflows and vibe coding."
    default:
      return ""
    }
  }

  func sortedPrices(for plan: SubscriptionPlanOption) -> [SubscriptionPriceOption] {
    plan.prices.sorted { lhs, rhs in
      let lhsIsMonthly = lhs.title.lowercased().contains("month")
      let rhsIsMonthly = rhs.title.lowercased().contains("month")
      if lhsIsMonthly != rhsIsMonthly {
        return lhsIsMonthly && !rhsIsMonthly
      }
      return lhs.title < rhs.title
    }
  }

  func isCurrentSubscriptionPlan(_ plan: SubscriptionPlanOption) -> Bool {
    guard hasPaidSubscription, let currentPlan = userSubscription?.subscription.plan else {
      return false
    }
    if currentPlan == .operator && plan.id == "unlimited" {
      return true
    }
    if currentPlan == .unlimited && plan.id == "operator" && isCurrentSubscriptionOperator() {
      return true
    }
    return currentPlan.rawValue == plan.id
  }

  var mergedPlanCatalog: [SubscriptionPlanOption] {
    mergePlanCatalog(primary: userSubscription?.availablePlans ?? [], fallback: fallbackPlanCatalog)
  }

  func mergePlanCatalog(
    primary: [SubscriptionPlanOption],
    fallback: [SubscriptionPlanOption]
  ) -> [SubscriptionPlanOption] {
    SubscriptionPlanCatalogMerger.merge(primary: primary, fallback: fallback)
  }

  func fallbackFeatures(for planId: String) -> [String] {
    switch planId {
    case "architect":
      return [
        "Automations and vibe coding",
        "Unlimited listening, memories, and insights",
        "Priority desktop AI features",
        "~$400 of monthly AI compute included (fair-use cap)",
      ]
    case "operator":
      return [
        "500 chat questions per month",
        "Unlimited listening and transcription",
        "Unlimited memories and insights",
        "Shared with mobile and web",
      ]
    case "unlimited":
      return [
        "200 chat questions per month",
        "Unlimited listening and transcription",
        "Unlimited memories and insights",
        "Shared with mobile and web",
      ]
    default:
      return []
    }
  }

  func normalizedPlanId(from title: String) -> String? {
    let normalized = title.lowercased()
    // Match the three plan families by title keyword. Neo is the post-rename
    // display name for the legacy "unlimited" plan and still maps to that id
    // because Stripe/backend PlanType enum is unchanged.
    if normalized.contains("unlimited") || normalized.contains("neo") {
      return "unlimited"
    }
    if normalized.contains("operator") {
      return "operator"
    }
    if normalized.contains("architect") || normalized.contains("pro") {
      return "architect"
    }
    return nil
  }

  func planCatalog(from prices: [AvailablePlanPriceOption]) -> [SubscriptionPlanOption] {
    let groupedPrices = Dictionary(grouping: prices) { price in
      normalizedPlanId(from: price.title) ?? "unknown"
    }

    return groupedPrices.compactMap { planId, options in
      guard planId != "unknown" else { return nil }

      let title: String
      switch planId {
      case "unlimited":
        title = "Neo"
      case "operator":
        title = "Operator"
      case "architect":
        title = "Architect"
      default:
        title = options.first?.title ?? "Plan"
      }

      let mappedPrices = options.map { option in
        SubscriptionPriceOption(
          id: option.id,
          title: option.interval.lowercased().contains("year") ? "Annual" : "Monthly",
          description: option.description,
          priceString: option.priceString
        )
      }

      return SubscriptionPlanOption(
        id: planId,
        title: title,
        features: fallbackFeatures(for: planId),
        prices: mappedPrices
      )
    }
  }

  @ViewBuilder
  func subscriptionPlanCard(_ plan: SubscriptionPlanOption) -> some View {
    let isSelected = selectedPlanIdForCheckout == plan.id
    let accent = planAccentColor(for: plan.id)
    let isCurrentPlan = isCurrentSubscriptionPlan(plan)
    let isArchitectUser =
      userSubscription?.subscription.plan == .architect
      || userSubscription?.subscription.plan == .pro
    let isDowngrade = isArchitectUser && plan.id == "unlimited"
    let canPurchase = !isCurrentPlan && !isDowngrade

    VStack(alignment: .leading, spacing: 16) {
      HStack(alignment: .top, spacing: 12) {
        VStack(alignment: .leading, spacing: 6) {
          Text((plan.eyebrow ?? planEyebrow(for: plan.id)).uppercased())
            .scaledFont(size: 10, weight: .bold)
            .foregroundColor(accent)
            .tracking(0.8)

          Text(plan.title)
            .scaledFont(size: 18, weight: .bold)
            .foregroundColor(OmiColors.textPrimary)

          if let subtitle = plan.subtitle ?? planSubtitle(for: plan.id) {
            Text(subtitle)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)
          }
        }

        Spacer()

        VStack(alignment: .trailing, spacing: 2) {
          Text(planSummaryText(for: plan))
            .scaledFont(size: 17, weight: .bold)
            .foregroundColor(isSelected ? accent : OmiColors.textPrimary)
            .lineLimit(1)
            .minimumScaleFactor(0.72)

          Text("starting price")
            .scaledFont(size: 10, weight: .medium)
            .foregroundColor(isSelected ? accent.opacity(0.8) : OmiColors.textTertiary)
        }
        .fixedSize(horizontal: true, vertical: false)
      }

      Text(plan.description ?? planDescription(for: plan.id))
        .scaledFont(size: 13)
        .foregroundColor(OmiColors.textSecondary)

      VStack(alignment: .leading, spacing: 8) {
        ForEach(plan.features.prefix(4), id: \.self) { feature in
          HStack(spacing: 8) {
            ZStack {
              Circle()
                .fill(accent.opacity(0.16))
                .frame(width: 18, height: 18)
              Image(systemName: "checkmark")
                .scaledFont(size: 9, weight: .bold)
                .foregroundColor(accent)
            }
            Text(feature)
              .scaledFont(size: 13, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
          }
        }
      }

      if isSelected && canPurchase {
        Divider()
          .overlay(OmiColors.backgroundQuaternary)

        VStack(alignment: .leading, spacing: 10) {
          VStack(alignment: .leading, spacing: 6) {
            Button(action: {
              withAnimation(.easeInOut(duration: 0.2)) {
                isPromoCodeExpanded.toggle()
              }
            }) {
              HStack(spacing: 6) {
                Image(systemName: "tag")
                  .scaledFont(size: 12)
                Text("Promo code")
                  .scaledFont(size: 12)
                Image(systemName: isPromoCodeExpanded ? "chevron.up" : "chevron.down")
                  .scaledFont(size: 10)
              }
              .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)

            if isPromoCodeExpanded {
              VStack(alignment: .leading, spacing: 6) {
                TextField("Enter promo code", text: $upgradePromotionCode)
                  .textFieldStyle(.roundedBorder)
                  .scaledFont(size: 13)
                  .disabled(activeCheckoutPriceId != nil)
                  .onChange(of: upgradePromotionCode) {
                    subscriptionError = nil
                  }

                if let error = subscriptionError {
                  HStack(spacing: 4) {
                    Image(systemName: "exclamationmark.circle")
                      .scaledFont(size: 11)
                    Text(error)
                      .scaledFont(size: 11)
                  }
                  .foregroundColor(OmiColors.warning)
                }
              }
              .transition(.opacity.combined(with: .move(edge: .top)))
            }
          }

          Text("Choose billing")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)

          HStack(spacing: 10) {
            ForEach(sortedPrices(for: plan)) { price in
              Button(action: {
                startCheckout(for: price.id)
              }) {
                Group {
                  if activeCheckoutPriceId == price.id {
                    ProgressView()
                      .controlSize(.small)
                      .frame(maxWidth: .infinity)
                  } else {
                    VStack(spacing: 3) {
                      Text(price.title)
                        .scaledFont(size: 12, weight: .bold)
                      Text(price.priceString)
                        .scaledFont(size: 11)
                        .foregroundColor(Color.white.opacity(0.92))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                  }
                }
                .padding(.vertical, 10)
              }
              .buttonStyle(.borderedProminent)
              .tint(accent)
              .disabled(activeCheckoutPriceId != nil)
            }
          }
        }
      } else if isCurrentPlan {
        HStack {
          Text("Current Plan")
            .scaledFont(size: 12, weight: .bold)
          Spacer()
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 12)
        }
        .foregroundColor(accent)
        .padding(.vertical, 10)
      } else {
        Button(action: {
          selectedPlanIdForCheckout = plan.id
        }) {
          HStack {
            Text("Select \(plan.title)")
              .scaledFont(size: 12, weight: .bold)
            Spacer()
            Image(systemName: "arrow.right")
              .scaledFont(size: 11, weight: .bold)
          }
          .padding(.vertical, 10)
        }
        .buttonStyle(.borderedProminent)
        .tint(accent)
      }
    }
    .padding(20)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 18)
        .fill(isSelected ? accent.opacity(0.12) : OmiColors.backgroundPrimary.opacity(0.68))
        .overlay(
          RoundedRectangle(cornerRadius: 18)
            .stroke(
              isSelected ? accent.opacity(0.85) : OmiColors.backgroundQuaternary,
              lineWidth: isSelected ? 1.5 : 1)
        )
    )
    .contentShape(RoundedRectangle(cornerRadius: 18))
    .onTapGesture {
      guard canPurchase else { return }
      selectedPlanIdForCheckout = plan.id
    }
  }

  // MARK: - Language Helpers

  /// Whether the selected language supports auto-detect mode
  var autoDetectSupported: Bool {
    AssistantSettings.supportsAutoDetect(transcriptionLanguage)
  }

  /// Subtitle text for auto-detect toggle
  var autoDetectSubtitle: String {
    if autoDetectSupported {
      return "Automatically detect spoken language"
    } else {
      return "Not available for \(languageName(for: transcriptionLanguage))"
    }
  }

  /// Get display name for a language code
  func languageName(for code: String) -> String {
    AssistantSettings.supportedLanguages.first { $0.code == code }?.name ?? code
  }

  // MARK: - Slider Index Helpers

  var analysisDelaySliderIndex: Int {
    analysisDelayOptions.firstIndex(of: analysisDelay) ?? 0
  }

  var taskIntervalSliderIndex: Int {
    extractionIntervalOptions.firstIndex(of: taskExtractionInterval) ?? 0
  }

  var insightIntervalSliderIndex: Int {
    extractionIntervalOptions.firstIndex(of: insightExtractionInterval) ?? 0
  }

  var memoryIntervalSliderIndex: Int {
    extractionIntervalOptions.firstIndex(of: memoryExtractionInterval) ?? 0
  }

  // MARK: - Helpers

  func toggleMonitoring(enabled: Bool) {
    if enabled && !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
      permissionError = "Screen recording permission required"
      isMonitoring = false
      ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      return
    }

    permissionError = nil
    isToggling = true

    // Track setting change
    AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

    if enabled {
      ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
        DispatchQueue.main.async {
          isToggling = false
          if !success {
            permissionError = error ?? "Failed to start monitoring"
            isMonitoring = false
          }
        }
      }
    } else {
      ProactiveAssistantsPlugin.shared.stopMonitoring()
      isToggling = false
    }

    // Persist the setting
    AssistantSettings.shared.screenAnalysisEnabled = enabled
  }

  func toggleTranscription(enabled: Bool) {
    // Check microphone permission
    if enabled && !appState.hasMicrophonePermission {
      transcriptionError = "Microphone permission required"
      isTranscribing = false
      return
    }

    transcriptionError = nil
    isTogglingTranscription = true

    // Track setting change
    AnalyticsManager.shared.settingToggled(setting: "transcription", enabled: enabled)

    if enabled {
      appState.startTranscription()
      isTogglingTranscription = false
      isTranscribing = true
    } else {
      appState.stopTranscription()
      isTogglingTranscription = false
      isTranscribing = false
    }

    // Persist the setting
    AssistantSettings.shared.transcriptionEnabled = enabled
  }

  func setSystemAudioCaptureMode(_ mode: AssistantSettings.SystemAudioCaptureMode) {
    AnalyticsManager.shared.settingToggled(
      setting: "system_audio_capture_mode_\(mode.rawValue)", enabled: mode != .never)
    // Persisting posts .systemAudioCaptureModeDidChange; AppState re-applies the gate live for
    // any in-progress recording.
    AssistantSettings.shared.systemAudioCaptureMode = mode
  }

  func startGlowPreview() {
    isPreviewRunning = true

    // Show the demo window and get its frame
    let demoWindow = GlowDemoWindow.show()
    let windowFrame = demoWindow.frame

    // Phase 1: Show focused (green) glow after a small delay
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
      GlowDemoWindow.setPhase(.focused)
      OverlayService.shared.showGlow(around: windowFrame, colorMode: .focused, isPreview: true)
    }

    // Phase 2: Show distracted (red) glow
    DispatchQueue.main.asyncAfter(deadline: .now() + 3.3) {
      GlowDemoWindow.setPhase(.distracted)
      OverlayService.shared.showGlow(around: windowFrame, colorMode: .distracted, isPreview: true)
    }

    // End preview and close demo window
    DispatchQueue.main.asyncAfter(deadline: .now() + 7.0) {
      GlowDemoWindow.close()
      isPreviewRunning = false
    }
  }

  func deleteCurrentAIProfile() {
    guard let id = aiProfileId else { return }
    Task {
      let previous = await AIUserProfileService.shared.deleteProfile(id: id)
      await MainActor.run {
        if let previous {
          aiProfileId = previous.id
          aiProfileText = previous.profileText
          aiProfileGeneratedAt = previous.generatedAt
          aiProfileDataSourcesUsed = previous.dataSourcesUsed
        } else {
          aiProfileId = nil
          aiProfileText = nil
          aiProfileGeneratedAt = nil
          aiProfileDataSourcesUsed = 0
        }
      }
    }
  }

  func regenerateAIProfile() {
    isGeneratingAIProfile = true
    Task {
      do {
        let result = try await AIUserProfileService.shared.generateProfile()
        await MainActor.run {
          aiProfileId = result.id
          aiProfileText = result.profileText
          aiProfileGeneratedAt = result.generatedAt
          aiProfileDataSourcesUsed = result.dataSourcesUsed
          isGeneratingAIProfile = false
        }
      } catch {
        log("Settings: AI profile generation failed: \(error.localizedDescription)")
        await MainActor.run {
          isGeneratingAIProfile = false
        }
      }
    }
  }

  func formatMinutes(_ minutes: Int) -> String {
    if minutes == 1 {
      return "1 minute"
    } else if minutes < 60 {
      return "\(minutes) minutes"
    } else {
      return "1 hour"
    }
  }

  func formatAnalysisDelay(_ seconds: Int) -> String {
    if seconds == 0 {
      return "Instant"
    } else if seconds < 60 {
      return "\(seconds) seconds"
    } else if seconds == 60 {
      return "1 minute"
    } else {
      return "\(seconds / 60) minutes"
    }
  }

  func formatExtractionInterval(_ seconds: Double) -> String {
    if seconds < 60 {
      return "\(Int(seconds)) seconds"
    } else if seconds < 3600 {
      let minutes = Int(seconds / 60)
      return minutes == 1 ? "1 minute" : "\(minutes) minutes"
    } else {
      let hours = Int(seconds / 3600)
      return hours == 1 ? "1 hour" : "\(hours) hours"
    }
  }

  func formatHour(_ hour: Int) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "h:00 a"
    var components = DateComponents()
    components.hour = hour
    if let date = Calendar.current.date(from: components) {
      return formatter.string(from: date)
    }
    return "\(hour):00"
  }

  // MARK: - Backend Settings

  func loadBackendSettings() {
    guard !isLoadingSettings else { return }
    isLoadingSettings = true

    // Load local transcription settings first (these are used immediately)
    transcriptionLanguage = AssistantSettings.shared.transcriptionLanguage
    transcriptionAutoDetect = AssistantSettings.shared.transcriptionAutoDetect
    vocabularyList = AssistantSettings.shared.transcriptionVocabulary
    vadGateEnabled = AssistantSettings.shared.vadGateEnabled
    systemAudioCaptureMode = AssistantSettings.shared.systemAudioCaptureMode

    Task {
      do {
        // Load all settings in parallel
        async let dailySummaryTask = APIClient.shared.getDailySummarySettings()
        async let notificationsTask = APIClient.shared.getNotificationSettings()
        async let languageTask = APIClient.shared.getUserLanguage()
        async let recordingTask = APIClient.shared.getRecordingPermission()
        async let cloudSyncTask = APIClient.shared.getPrivateCloudSync()
        async let transcriptionTask = APIClient.shared.getTranscriptionPreferences()

        // Sync assistant settings from server in parallel
        async let assistantSyncTask: () = SettingsSyncManager.shared.syncFromServer()

        let (dailySummary, notifications, language, recording, cloudSync, transcription, _) = try
          await (
            dailySummaryTask,
            notificationsTask,
            languageTask,
            recordingTask,
            cloudSyncTask,
            transcriptionTask,
            assistantSyncTask
          )

        await MainActor.run {
          dailySummaryEnabled = dailySummary.enabled
          dailySummaryHour = dailySummary.hour
          notificationsEnabled = notifications.enabled
          notificationFrequency = notifications.frequency
          // Mirror to UserDefaults so NotificationService can gate/throttle without a backend roundtrip.
          UserDefaults.standard.set(
            notifications.enabled, forKey: NotificationService.masterEnabledDefaultsKey)
          UserDefaults.standard.set(notifications.frequency, forKey: NotificationService.frequencyDefaultsKey)
          userLanguage = language.language
          recordingPermissionEnabled = recording.enabled
          privateCloudSyncEnabled = cloudSync.enabled
          singleLanguageMode = transcription.singleLanguageMode
          vocabularyList = transcription.vocabulary
          // Sync backend vocabulary to local settings
          AssistantSettings.shared.transcriptionVocabulary = transcription.vocabulary

          // Sync backend language to local if different (backend is source of truth for language)
          let normalizedLanguage = AssistantSettings.normalizeTranscriptionLanguageCode(language.language)
          if !language.language.isEmpty && normalizedLanguage != transcriptionLanguage {
            transcriptionLanguage = normalizedLanguage
            AssistantSettings.shared.transcriptionLanguage = normalizedLanguage
          }

          // Sync single language mode from backend (inverted to auto-detect)
          // Only update if we got a valid response and it differs
          let backendAutoDetect =
            !transcription.singleLanguageMode && AssistantSettings.supportsAutoDetect(normalizedLanguage)
          if backendAutoDetect != transcriptionAutoDetect {
            transcriptionAutoDetect = backendAutoDetect
            AssistantSettings.shared.transcriptionAutoDetect = backendAutoDetect
          }

          isLoadingSettings = false
          viewModel.markBackendSettingsLoaded()
        }

      } catch {
        logError("Failed to load backend settings", error: error)
        await MainActor.run {
          isLoadingSettings = false
        }
      }
    }
  }

  func loadSubscriptionInfo() {
    guard !isLoadingSubscription else { return }
    isLoadingSubscription = true
    subscriptionError = nil
    refreshPlanUsageDetails()

    Task {
      do {
        let subscription = try await APIClient.shared.getUserSubscription()
        let availablePlans = try? await APIClient.shared.getAvailablePlans()
        await MainActor.run {
          userSubscription = subscription
          subscriptionError = nil
          fallbackPlanCatalog = availablePlans.map { planCatalog(from: $0.plans) } ?? []
          if let selectedPlanIdForCheckout,
            subscription.subscription.plan.rawValue == selectedPlanIdForCheckout
          {
            self.selectedPlanIdForCheckout = nil
          }
          // Clear the sticky paywall flag whenever the subscription endpoint
          // reports a non-basic active plan. Catches the case where a paid user
          // hit the paywall once (e.g. WS connected before payment cleared
          // the trial cache) — without this they'd stay paywalled until the
          // next app restart even after their Operator/Architect plan is active.
          if subscription.subscription.plan != .basic,
             subscription.subscription.status == .active,
             AppState.current?.isPaywalled == true {
            AppState.current?.isPaywalled = false
            log("Paywall: cleared sticky flag — subscription \(subscription.subscription.plan.rawValue) is active")
          }
          isLoadingSubscription = false
          viewModel.markBillingRefreshed()
        }
      } catch {
        logError("Failed to load subscription", error: error)
        await MainActor.run {
          subscriptionError = "Failed to load plan information."
          isLoadingSubscription = false
        }
      }
    }
  }

  func refreshPlanUsageDetails() {
    planUsageDetailsRequestID += 1
    let requestID = planUsageDetailsRequestID
    isLoadingChatUsage = true
    isLoadingOverage = true
    chatUsageQuota = nil
    overageInfo = nil

    Task {
      async let quota = APIClient.shared.fetchChatUsageQuota()
      async let overageInfo = fetchOverageInfoForPlanUsage()
      let (quotaValue, overageInfoValue) = await (quota, overageInfo)
      applyPlanUsageDetails(
        requestID: requestID,
        quota: quotaValue,
        overageInfo: overageInfoValue
      )
    }
  }

  func fetchOverageInfoForPlanUsage() async -> OverageInfoResponse? {
    do {
      return try await APIClient.shared.getOverageInfo()
    } catch {
      logError("Failed to load overage info", error: error)
      return nil
    }
  }

  @MainActor
  func applyPlanUsageDetails(
    requestID: Int,
    quota: APIClient.ChatUsageQuota?,
    overageInfo: OverageInfoResponse?
  ) {
    guard requestID == planUsageDetailsRequestID else { return }
    chatUsageQuota = quota
    if let quota {
      FloatingBarUsageLimiter.shared.applyQuota(quota)
    }
    self.overageInfo = overageInfo
    isLoadingChatUsage = false
    isLoadingOverage = false
  }

  func applySuccessfulSubscriptionRefresh(_ subscription: UserSubscriptionResponse) {
    userSubscription = subscription
    subscriptionError = nil
    pendingSubscriptionPriceId = nil
    pendingCheckoutSessionId = nil
    selectedPlanIdForCheckout = nil

    FloatingBarUsageLimiter.shared.applyPlan(
      plan: subscription.subscription.plan,
      status: subscription.subscription.status
    )

    if subscription.subscription.plan != .basic,
       subscription.subscription.status == .active,
       AppState.current?.isPaywalled == true {
      AppState.current?.isPaywalled = false
      log("Paywall: cleared sticky flag — subscription \(subscription.subscription.plan.rawValue) is active")
    }

    refreshPlanUsageDetails()
  }

  func startCheckout(for priceId: String) {
    guard activeCheckoutPriceId == nil else { return }
    activeCheckoutPriceId = priceId
    pendingSubscriptionPriceId = priceId
    subscriptionError = nil

    let promotionCode = upgradePromotionCode.trimmingCharacters(in: .whitespacesAndNewlines)
    let promoToSend: String? = promotionCode.isEmpty ? nil : promotionCode

    // If user already has an active paid subscription (not canceled), use upgrade endpoint
    // to schedule the plan change at end of billing period (no double-charging)
    if hasPaidSubscription,
       let subscription = userSubscription?.subscription,
       !subscription.cancelAtPeriodEnd
    {
      Task {
        do {
          _ = try await APIClient.shared.upgradeSubscription(
            priceId: priceId, promotionCode: promoToSend)
          await MainActor.run {
            activeCheckoutPriceId = nil
            pendingSubscriptionPriceId = nil
            subscriptionError = nil
            self.upgradePromotionCode = ""
            loadSubscriptionInfo()
          }
        } catch let apiError as APIError {
          await MainActor.run {
            activeCheckoutPriceId = nil
            pendingSubscriptionPriceId = nil
            subscriptionError = apiError.detail ?? "Failed to schedule plan change."
          }
        } catch {
          logError("Failed to schedule plan change", error: error)
          await MainActor.run {
            activeCheckoutPriceId = nil
            pendingSubscriptionPriceId = nil
            subscriptionError = "Failed to schedule plan change."
          }
        }
      }
      return
    }

    Task {
      do {
        let response = try await APIClient.shared.createCheckoutSession(
          priceId: priceId, promotionCode: promoToSend)
        let apiBaseURL = await APIClient.shared.baseURL
        await MainActor.run {
          activeCheckoutPriceId = nil
          pendingCheckoutSessionId = response.sessionId
        }

        if response.status == "reactivated" {
          await MainActor.run {
            subscriptionError = nil
            pendingSubscriptionPriceId = nil
            pendingCheckoutSessionId = nil
            loadSubscriptionInfo()
          }
        } else if let urlString = response.url, let url = URL(string: urlString) {
          let normalizedBaseURL = apiBaseURL.hasSuffix("/") ? apiBaseURL : apiBaseURL + "/"
          await MainActor.run {
            activeBillingWebFlow = BillingWebFlow(
              title: "Complete Your Upgrade",
              url: url,
              completionURLs: [
                normalizedBaseURL + "v1/payments/success",
                normalizedBaseURL + "v1/payments/cancel",
              ]
            )
          }
        } else {
          await MainActor.run {
            subscriptionError = response.message ?? "Could not start checkout."
          }
        }
      } catch let apiError as APIError {
        logError("Failed to create checkout session", error: apiError)
        await MainActor.run {
          activeCheckoutPriceId = nil
          pendingSubscriptionPriceId = nil
          pendingCheckoutSessionId = nil
          subscriptionError = apiError.detail ?? "Failed to open checkout."
        }
      } catch {
        logError("Failed to create checkout session", error: error)
        await MainActor.run {
          activeCheckoutPriceId = nil
          pendingSubscriptionPriceId = nil
          pendingCheckoutSessionId = nil
          subscriptionError = "Failed to open checkout."
        }
      }
    }
  }

  func openCustomerPortal() {
    guard !isOpeningCustomerPortal else { return }
    isOpeningCustomerPortal = true
    subscriptionError = nil

    Task {
      do {
        let response = try await APIClient.shared.createCustomerPortalSession()
        await MainActor.run {
          isOpeningCustomerPortal = false
        }

        if let url = URL(string: response.url) {
          await MainActor.run {
            openURLInDefaultBrowser(url)
            subscriptionError = "Billing portal opened in your browser."
          }
        } else {
          await MainActor.run {
            subscriptionError = "Could not open billing portal."
          }
        }
      } catch {
        logError("Failed to open customer portal", error: error)
        await MainActor.run {
          isOpeningCustomerPortal = false
          subscriptionError = "Failed to open billing portal."
        }
      }
    }
  }

  func handleBillingFlowCompletion(_ outcome: BillingWebFlowOutcome) {
    switch outcome {
    case .completed:
      Task {
        await completeLocalTestSubscriptionIfNeeded()
        await MainActor.run {
          pollForUpdatedSubscription()
        }
      }
    case .cancelled, .dismissed:
      pendingSubscriptionPriceId = nil
      pendingCheckoutSessionId = nil
      loadSubscriptionInfo()
    }
  }

  func pollForUpdatedSubscription() {
    let expectedPriceId = pendingSubscriptionPriceId

    Task {
      for attempt in 0..<8 {
        do {
          let subscription = try await APIClient.shared.getUserSubscription()
          let matchedPrice =
            expectedPriceId == nil || subscription.subscription.currentPriceId == expectedPriceId
          let hasPaidPlan =
            subscription.subscription.plan != .basic && subscription.subscription.status == .active

          if matchedPrice && hasPaidPlan {
            await MainActor.run {
              applySuccessfulSubscriptionRefresh(subscription)
            }
            return
          }

          if attempt == 7 {
            await MainActor.run {
              userSubscription = subscription
              subscriptionError =
                "Payment completed, but plan refresh is still catching up. Please try reloading this page in a moment."
              pendingSubscriptionPriceId = nil
              pendingCheckoutSessionId = nil
            }
            return
          }

          try await Task.sleep(nanoseconds: 1_000_000_000)
        } catch {
          if attempt == 7 {
            await MainActor.run {
              subscriptionError = "Payment completed, but subscription refresh failed."
              pendingSubscriptionPriceId = nil
              pendingCheckoutSessionId = nil
            }
            return
          }

          try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
      }
    }
  }

  func completeLocalTestSubscriptionIfNeeded() async {
    guard let expectedPriceId = pendingSubscriptionPriceId else { return }
    let checkoutSessionId = pendingCheckoutSessionId
    let pythonBaseURL = await APIClient.shared.baseURL
    let rustBaseURL = await APIClient.shared.rustBackendURL

    if let checkoutSessionId, isLocalURL(pythonBaseURL) {
      guard
        let encodedSessionId = checkoutSessionId.addingPercentEncoding(
          withAllowedCharacters: .urlQueryAllowed),
        let url = URL(string: "\(pythonBaseURL)v1/payments/success?session_id=\(encodedSessionId)")
      else {
        return
      }

      do {
        _ = try await URLSession.shared.data(from: url)
      } catch {
        logError("Failed to complete local python test subscription", error: error)
      }
      return
    }

    guard isLocalURL(rustBaseURL) else { return }

    guard
      let encodedPriceId = expectedPriceId.addingPercentEncoding(
        withAllowedCharacters: .urlQueryAllowed)
    else {
      return
    }

    var urlString = "\(rustBaseURL)test/complete-subscription?price_id=\(encodedPriceId)"
    if let checkoutSessionId,
      let encodedSessionId = checkoutSessionId.addingPercentEncoding(
        withAllowedCharacters: .urlQueryAllowed)
    {
      urlString += "&session_id=\(encodedSessionId)"
    }

    guard let url = URL(string: urlString) else { return }

    do {
      _ = try await URLSession.shared.data(from: url)
    } catch {
      logError("Failed to complete local test subscription", error: error)
    }
  }

  func isLocalURL(_ url: String) -> Bool {
    url.hasPrefix("http://127.0.0.1:") || url.hasPrefix("http://localhost:")
  }

}
