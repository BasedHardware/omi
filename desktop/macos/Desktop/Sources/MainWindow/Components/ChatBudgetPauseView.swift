import OmiTheme
import SwiftUI

struct ChatBudgetPauseView: View {
  let state: APIClient.ChatAtCap
  let onUpgrade: () -> Void
  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Text(state.title).scaledFont(size: OmiType.body, weight: .semibold).foregroundColor(Ink.primary)
      Text(state.body).scaledFont(size: OmiType.caption).foregroundColor(Ink.secondary)
      Text(state.resetLine).scaledFont(size: OmiType.caption).foregroundColor(Ink.primary)
      if let label = state.upgradeLabel {
        Button(label, action: onUpgrade).buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(OmiSpacing.md)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius))
    .accessibilityIdentifier("chat-budget-pause")
  }

  struct Slot: View {
    @ObservedObject private var limiter = FloatingBarUsageLimiter.shared
    @State private var showingSheet = false
    @State private var busy: String?
    @State private var error: String?
    var body: some View {
      Group {
        if PlanStorefrontGate.contextualEnabled, let state = limiter.serverQuota?.chatAtCap, state.active {
          ChatBudgetPauseView(state: state, onUpgrade: { showingSheet = true })
        }
      }
      .task {
        guard PlanStorefrontGate.contextualEnabled else { return }
        while !Task.isCancelled {
          await limiter.syncQuota()
          do { try await Task.sleep(for: .seconds(30)) } catch { return }
        }
      }
      .sheet(isPresented: $showingSheet, onDismiss: { Task { await limiter.syncQuota() } }) {
        VStack(alignment: .trailing) {
          DismissButton(action: { showingSheet = false }, accessibilityLabel: "Dismiss", size: .compact)
            .padding(OmiSpacing.md)
          ScrollView {
            StorefrontPlansSection(
              source: "macos_chat", trigger: .usageBudget,
              livePlanId: limiter.serverQuota?.planType, busyPriceId: busy, error: error,
              onPurchase: { tier, price in
                guard let id = price.id, busy == nil else { return }
                busy = id
                error = nil
                AnalyticsManager.shared.upgradePlanSelected(
                  plan: tier.planId, billingInterval: price.interval.rawValue, source: "macos_chat")
                Task { @MainActor in
                  defer { busy = nil }
                  do {
                    let subscription = try await APIClient.shared.getUserSubscription().subscription
                    if subscription.plan.hasPaidCapability && subscription.status == .active
                      && !subscription.cancelAtPeriodEnd
                    {
                      _ = try await APIClient.shared.upgradeSubscription(priceId: id)
                    } else {
                      let result = try await APIClient.shared.createCheckoutSession(priceId: id)
                      if let address = result.url, let url = URL(string: address) { NSWorkspace.shared.open(url) }
                    }
                    await limiter.fetchPlan()
                    showingSheet = false
                  } catch { self.error = error.localizedDescription }
                }
              },
              onManage: {
                NotificationCenter.default.post(name: .navigateToPlanSettings, object: nil)
                showingSheet = false
              }
            )
            .padding(OmiSpacing.xxl)
          }
        }.frame(width: 640, height: 640)
          .onEscapeKey(priority: .modal) {
            showingSheet = false
            return true
          }
      }
    }
  }
}
