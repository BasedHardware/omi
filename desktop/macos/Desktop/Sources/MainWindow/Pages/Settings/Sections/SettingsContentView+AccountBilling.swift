import Sparkle
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import OmiTheme

extension SettingsContentView {
  var accountSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      settingsCard(settingId: "account.account") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
            Image(systemName: "person.circle.fill")
              .scaledFont(size: OmiType.hero)
              .foregroundColor(OmiColors.textTertiary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(AuthService.shared.displayName.isEmpty ? "User" : AuthService.shared.displayName)
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              if let email = AuthState.shared.userEmail {
                Text(email)
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }

            Spacer()

            Button("Sign Out") {
              appState.stopTranscription()
              ProactiveAssistantsPlugin.shared.stopMonitoring()
              try? AuthService.shared.signOut()
            }
            .buttonStyle(OmiButtonStyle(.primary, size: .compact))
            .disabled(isDeletingAccount)
          }

          Divider()
            .overlay(OmiColors.backgroundQuaternary)

          HStack(alignment: .center, spacing: OmiSpacing.lg) {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Delete Account & Data")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.error)

              Text(
                "Permanently deletes server data, clears local data for this account, resets onboarding, and signs you out."
              )
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            Button(action: {
              AnalyticsManager.shared.deleteAccountClicked()
              showDeleteAccountAlert = true
            }) {
              if isDeletingAccount {
                ProgressView()
                  .controlSize(.small)
              } else {
                Text("Delete")
                  .scaledFont(size: OmiType.body, weight: .semibold)
              }
            }
            .buttonStyle(.borderedProminent)
            .tint(OmiColors.error)
            .disabled(isDeletingAccount)
          }

          if let deleteAccountError {
            Text(deleteAccountError)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.warning)
          }
        }
      }
      .alert("Delete Account and Data?", isPresented: $showDeleteAccountAlert) {
        Button("Cancel", role: .cancel) {
          AnalyticsManager.shared.deleteAccountCancelled()
        }
        Button("Delete Permanently", role: .destructive) {
          deleteAccountAndData()
        }
      } message: {
        Text(
          "This cannot be undone. Your account, chat history, and all server data will be permanently deleted. Local data for this account will be cleared and you'll return to onboarding."
        )
      }

      //            settingsCard {
      //                HStack(spacing: OmiSpacing.lg) {
      //                    Image(systemName: "bolt.fill")
      //                        .scaledFont(size: OmiType.subheading)
      //                        .foregroundColor(.yellow)
      //
      //                    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      //                        Text("Upgrade to Pro")
      //                            .scaledFont(size: OmiType.subheading, weight: .medium)
      //                            .foregroundColor(OmiColors.textPrimary)
      //
      //                        Text("Unlock all features and unlimited usage")
      //                            .scaledFont(size: OmiType.body)
      //                            .foregroundColor(OmiColors.textTertiary)
      //                    }
      //
      //                    Spacer()
      //
      //                    Button("Upgrade") {
      //                        if let url = URL(string: "https://omi.me/pricing") {
      //                            NSWorkspace.shared.open(url)
      //                        }
      //                    }
      //                    .buttonStyle(.borderedProminent)
      //                    .tint(OmiColors.accent)
      //                }
      //            }
    }
  }

  // MARK: - Trial Countdown Card

  @ViewBuilder
  var trialCountdownCard: some View {
    if let trial = appState.trialMetadata, trial.trialStartedAt != nil, !trial.trialExpired {
      settingsCard(settingId: "planusage.trial") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
            Image(systemName: "clock.fill")
              .scaledFont(size: OmiType.title)
              .foregroundColor(trialTimeColor(remaining: trial.trialRemainingSeconds))

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Premium Trial Active")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(trialCountdownText(remaining: trial.trialRemainingSeconds))
                .scaledFont(size: OmiType.body)
                .foregroundColor(trialTimeColor(remaining: trial.trialRemainingSeconds))
            }

            Spacer()

            // Progress ring
            ZStack {
              Circle()
                .stroke(OmiColors.backgroundQuaternary, lineWidth: 3)
              Circle()
                .trim(from: 0, to: trialProgress(trial))
                .stroke(trialTimeColor(remaining: trial.trialRemainingSeconds), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .rotationEffect(.degrees(-90))
            }
            .frame(width: 32, height: 32)
          }

          Divider().overlay(OmiColors.backgroundQuaternary)

          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Included in your trial")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(OmiColors.textTertiary)

            trialFeatureRow(text: "Unlimited listening & transcription")
            trialFeatureRow(text: "Unlimited memories & insights")
            trialFeatureRow(text: "Chat questions")
          }
        }
      }
    } else if let trial = appState.trialMetadata,
      trial.trialExpired
    {
      settingsCard(settingId: "planusage.trial-expired") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
            Image(systemName: "exclamationmark.circle.fill")
              .scaledFont(size: OmiType.title)
              .foregroundColor(OmiColors.warning)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Trial Ended")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text("Upgrade to keep unlimited access")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textSecondary)
            }

            Spacer()
          }

          Divider().overlay(OmiColors.backgroundQuaternary)

          Button(action: {
            selectedPlanIdForCheckout = "operator"
          }) {
            Text("View Plans")
              .scaledFont(size: OmiType.body, weight: .semibold)
          }
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        }
      }
    }
  }

  func trialFeatureRow(text: String) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      ZStack {
        Circle()
          .fill(OmiColors.backgroundTertiary)
          .frame(width: 18, height: 18)
        Image(systemName: "checkmark")
          .scaledFont(size: OmiType.micro, weight: .bold)
          .foregroundColor(OmiColors.textSecondary)
      }
      Text(text)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
    }
  }

  func trialCountdownText(remaining: Int) -> String {
    if remaining <= 0 { return "Expired" }
    let hours = remaining / 3600
    let minutes = (remaining % 3600) / 60
    if hours >= 24 {
      let days = hours / 24
      let leftoverHours = hours % 24
      return "\(days)d \(leftoverHours)h remaining"
    }
    if hours > 0 {
      return "\(hours)h \(minutes)m remaining"
    }
    return "\(minutes)m remaining"
  }

  func trialTimeColor(remaining: Int) -> Color {
    if remaining <= 3600 { return OmiColors.warning }      // < 1 hour: warning orange
    if remaining <= 24 * 3600 { return .yellow }           // < 24 hours: yellow
    return OmiColors.success                                // plenty of time: green
  }

  func trialProgress(_ trial: TrialMetadataResponse) -> CGFloat {
    guard trial.trialDurationSeconds > 0 else { return 0 }
    return CGFloat(trial.trialRemainingSeconds) / CGFloat(trial.trialDurationSeconds)
  }

  // MARK: - Plan and Usage Section

  var planUsageSection: some View {
    VStack(spacing: OmiSpacing.xl) {
      trialCountdownCard

      settingsCard(settingId: "planusage.current") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack(spacing: OmiSpacing.lg) {
            Image(systemName: "creditcard.fill")
              .scaledFont(size: OmiType.title)
              .foregroundColor(OmiColors.textSecondary)

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(currentPlanTitle)
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(currentPlanSubtitle)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if isLoadingSubscription {
              ProgressView()
                .controlSize(.small)
            } else if hasPaidSubscription {
              Button(action: openCustomerPortal) {
                if isOpeningCustomerPortal {
                  ProgressView()
                    .controlSize(.small)
                } else {
                  Text("Manage")
                    .scaledFont(size: OmiType.body, weight: .semibold)
                }
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              .disabled(isOpeningCustomerPortal)
            } else {
              Button("Refresh") {
                loadSubscriptionInfo()
              }
              .buttonStyle(OmiButtonStyle(.primary, size: .compact))
              .disabled(isLoadingSubscription)
            }
          }

          if let periodText = currentPlanPeriodText {
            Divider()
              .overlay(OmiColors.backgroundQuaternary)

            Text(periodText)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textSecondary)
          }

          if let error = subscriptionError {
            Text(error)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.warning)
          }
        }
      }

      if let subscription = userSubscription?.subscription,
        subscription.deprecated == true
      {
        settingsCard(settingId: "planusage.deprecation") {
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(OmiColors.warning)
                .scaledFont(size: OmiType.subheading)
              Text("Plan Retiring")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
            }

            Text(
              subscription.deprecationMessage
                ?? "Your Unlimited plan is being retired. Try the new Operator plan — same great features at $49/mo."
            )
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)

            Button(action: {
              selectedPlanIdForCheckout = "operator"
            }) {
              Text("Try Operator")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .padding(.horizontal, OmiSpacing.lg)
                .padding(.vertical, OmiSpacing.sm)
            }
            .buttonStyle(.borderedProminent)
            .tint(OmiColors.success)
          }
        }
      }

      if shouldShowPlanPurchaseOptions {
        settingsCard(settingId: "planusage.purchase") {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text("Choose a plan")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text("Pick one plan first. Billing options appear only after the card is selected.")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }

            // All plan cards share the row width — no horizontal scrolling.
            HStack(alignment: .top, spacing: OmiSpacing.lg) {
              ForEach(subscriptionPlansForDisplay) { plan in
                subscriptionPlanCard(plan)
                  .frame(maxWidth: .infinity, alignment: .topLeading)
              }
            }
          }
        }
      }

      chatUsageQuotaCard

      overageCard

      byokPromoCard
    }
    .sheet(isPresented: $showOverageExplainer) {
      overageExplainerSheet
    }
  }

  @ViewBuilder
  var overageCard: some View {
    if let info = overageInfo, info.isOveragePlan {
      settingsCard(settingId: "planusage.overage") {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          HStack(spacing: OmiSpacing.sm) {
            Image(systemName: info.excessQuestions > 0
              ? "dollarsign.circle.fill"
              : "checkmark.circle.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(info.excessQuestions > 0
                ? OmiColors.warning
                : OmiColors.success)
            Text(info.excessQuestions > 0
              ? "Usage-based overage"
              : "No overage yet this cycle")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Spacer()
            if info.excessQuestions > 0 {
              Text(String(format: "$%.2f", info.overageUsd))
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.warning)
                .monospacedDigit()
            }
          }

          if info.excessQuestions > 0 {
            Text(
              "You've gone \(info.excessQuestions) question\(info.excessQuestions == 1 ? "" : "s") past your plan's \(info.includedQuestions ?? 0) included. We'll bill the overage at end of your cycle."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
          } else {
            Text(
              "Go over your \(info.includedQuestions ?? 0) included questions and we'll charge real provider cost + \(Int(info.markupPercent))%. No hard cutoff."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
          }

          Button(action: { showOverageExplainer = true }) {
            HStack(spacing: OmiSpacing.xxs) {
              Text(info.explainerTitle)
                .scaledFont(size: OmiType.caption, weight: .medium)
              Image(systemName: "info.circle")
                .scaledFont(size: OmiType.caption)
            }
            .foregroundColor(OmiColors.accent)
          }
          .buttonStyle(.plain)
        }
      }
    } else if isLoadingOverage && overageInfo == nil {
      // silent while loading — nothing to show
      EmptyView()
    }
  }

  var overageExplainerSheet: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.lg) {
        HStack {
          Text(overageInfo?.explainerTitle ?? "How overage billing works")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
          Spacer()
          Button(action: { showOverageExplainer = false }) {
            Image(systemName: "xmark.circle.fill")
              .scaledFont(size: OmiType.heading)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
        }

        Text(overageInfo?.explainerBody ?? "")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .fixedSize(horizontal: false, vertical: true)

        if let info = overageInfo, info.isOveragePlan {
          Divider().overlay(OmiColors.backgroundQuaternary)
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Your current cycle")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            overageExplainerRow("Questions used", value: "\(info.usedQuestions)")
            overageExplainerRow("Included in plan", value: "\(info.includedQuestions ?? 0)")
            overageExplainerRow("Over the limit", value: "\(info.excessQuestions)")
            overageExplainerRow(
              "Real provider cost",
              value: String(format: "$%.2f", info.realCostUsd)
            )
            overageExplainerRow(
              "Markup",
              value: String(format: "%.0f%%", info.markupPercent)
            )
            overageExplainerRow(
              "Overage to bill",
              value: String(format: "$%.2f", info.overageUsd),
              emphasized: true
            )
          }
        }
      }
      .padding(OmiSpacing.xxl)
    }
    .frame(minWidth: 440, minHeight: 360)
  }

  func overageExplainerRow(_ label: String, value: String, emphasized: Bool = false) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textTertiary)
      Spacer()
      Text(value)
        .scaledFont(size: OmiType.caption, weight: emphasized ? .semibold : .regular)
        .foregroundColor(emphasized ? OmiColors.warning : OmiColors.textSecondary)
        .monospacedDigit()
    }
  }

  @ViewBuilder
  var byokPromoCard: some View {
    settingsCard(settingId: "planusage.byok") {
      VStack(alignment: .leading, spacing: OmiSpacing.md) {
        HStack(spacing: OmiSpacing.md) {
          Image(systemName: "key.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(OmiColors.textSecondary)
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(APIKeyService.isByokActive ? "Free plan active" : "Use Omi free forever")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Text(
              APIKeyService.isByokActive
                ? "You're using your own OpenAI, Anthropic, Gemini, and Deepgram keys. No subscription."
                : "Provide your own OpenAI, Anthropic, Gemini, and Deepgram keys to skip the subscription entirely."
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
          }
          Spacer()
        }

        Button(action: openBYOKSettings) {
          Text(APIKeyService.isByokActive ? "Manage your keys" : "Switch to your own keys")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
      }
    }
  }

  func openBYOKSettings() {
    selectedSection = .advanced
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
      highlightedSettingId = "advanced.devkeys.info"
    }
  }

  // MARK: - Chat Usage Quota Card

  @ViewBuilder
  var chatUsageQuotaCard: some View {
    if let quota = chatUsageQuota {
      settingsCard(settingId: "planusage.current") {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          HStack {
            Text("Usage this month")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)
            Spacer()
            Text(chatUsageQuotaValueText(quota))
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(chatUsageBarColor(quota))
              .monospacedDigit()
          }

          ProgressView(value: min(quota.percent / 100.0, 1.0))
            .progressViewStyle(LinearProgressViewStyle(tint: chatUsageBarColor(quota)))
            .frame(height: 6)

          HStack {
            Text(chatUsageQuotaDescription(quota))
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
            Spacer()
            if let resetText = chatUsageQuotaResetText(quota) {
              Text(resetText)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            }
          }

          if !quota.allowed {
            // Neo / overage-enabled plans keep working past the cap (extra
            // usage accrues as overage). Show a softer message on those plans;
            // only show the hard "upgrade" copy on Free and other hard-capped
            // plans.
            if let info = overageInfo, info.isOveragePlan {
              Text("You're past your included limit — extra usage is billed as overage at end of cycle.")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.warning)
            } else {
              Text("You've reached this month's limit. Upgrade your plan or wait until the next reset.")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.warning)
            }
          } else if quota.percent >= 80.0 {
            Text("You're close to your monthly limit.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.warning)
          }
        }
      }
    } else if isLoadingChatUsage {
      settingsCard(settingId: "planusage.current") {
        HStack {
          ProgressView().controlSize(.small)
          Text("Loading usage…")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
        }
      }
    }
  }

  func chatUsageQuotaValueText(_ q: APIClient.ChatUsageQuota) -> String {
    if q.unit == "cost_usd" {
      let limit = q.limit.map { String(format: "$%.0f", $0) } ?? "—"
      return String(format: "$%.2f / %@", q.used, limit)
    }
    let used = Int(q.used)
    let limit = q.limit.map { "\(Int($0))" } ?? "∞"
    return "\(used) / \(limit)"
  }

  func chatUsageQuotaDescription(_ q: APIClient.ChatUsageQuota) -> String {
    if q.unit == "cost_usd" {
      return "Chat spend on \(q.plan) plan"
    }
    return "Chat questions on \(q.plan) plan"
  }

  func chatUsageQuotaResetText(_ q: APIClient.ChatUsageQuota) -> String? {
    guard let resetAt = q.resetAt else { return nil }
    let resetDate = Date(timeIntervalSince1970: TimeInterval(resetAt))
    let now = Date()
    let days = max(0, Int(resetDate.timeIntervalSince(now) / 86400))
    if days <= 0 {
      return "Resets today"
    }
    if days == 1 {
      return "Resets tomorrow"
    }
    return "Resets in \(days) days"
  }

  func chatUsageBarColor(_ q: APIClient.ChatUsageQuota) -> Color {
    if !q.allowed || q.percent >= 100.0 { return OmiColors.warning }
    if q.percent >= 80.0 { return OmiColors.warning }
    return OmiColors.accent
  }

  // MARK: - AI Chat Section

}
