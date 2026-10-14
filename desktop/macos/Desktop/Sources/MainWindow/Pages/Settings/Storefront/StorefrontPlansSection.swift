import OmiTheme
import SwiftUI

/// Loads the plans payload for one surface and renders it. Purchases go back to the
/// settings host, which owns the existing checkout-session / upgrade-subscription rails.
struct StorefrontPlansSection: View {
  let source: String
  var trigger: PlanStorefront.Trigger?
  var initial: PlanStorefront?
  var livePlanId: String?
  var busyPriceId: String?
  var error: String?
  /// Changes whenever the live subscription does, so a completed purchase re-reads the sheet.
  var reloadKey: String = ""
  let onPurchase: (PlanStorefront.Tier, PlanStorefront.Price) -> Void
  let onManage: () -> Void

  @State private var data: PlanStorefront?
  @State private var loading = false
  @State private var failed = false
  @State private var reported = false
  @State private var confirmation: Selection?
  @State private var showsConfirmation = false

  private struct Selection: Identifiable {
    let tier: PlanStorefront.Tier
    let price: PlanStorefront.Price
    var id: String { price.id ?? "" }
  }

  var body: some View {
    StorefrontPlansView(
      data: data ?? initial, loading: loading, failed: failed, busyPriceId: busyPriceId, error: error,
      livePlanId: livePlanId, onRetry: { Task { await load() } },
      onSelect: { tier, price in
        guard let shown = data ?? initial,
          shown.checkoutDecision(tier: tier, price: price, livePlanId: livePlanId) != .refuse
        else { return }
        if price.confirmLines.isEmpty {
          onPurchase(tier, price)
        } else {
          confirmation = Selection(tier: tier, price: price)
          showsConfirmation = true
        }
      },
      onManage: onManage
    )
    .shellConfirmation(
      isPresented: $showsConfirmation,
      title: confirmation?.price.ctaLabel ?? confirmation?.tier.ctaLabel ?? "Plans",
      message: confirmation?.price.confirmLines.joined(separator: "\n") ?? "",
      confirmTitle: confirmation?.price.ctaLabel ?? "Switch to yearly",
      isDestructive: false,
      onCancel: { confirmation = nil },
      onConfirm: {
        guard let selection = confirmation else { return }
        confirmation = nil
        onPurchase(selection.tier, selection.price)
      }
    )
    .task(id: reloadKey) {
      // The first render of a contextual sheet already has its payload.
      if initial != nil && data == nil && !reported {
        report(initial)
        return
      }
      await load()
    }
  }

  @MainActor
  private func load() async {
    loading = data == nil && initial == nil
    failed = false
    do {
      let next = try await APIClient.shared.getStorefront(source: source, trigger: trigger)
      data = next
      report(next)
    } catch {
      if data == nil && initial == nil { failed = true }
    }
    loading = false
  }

  private func report(_ shown: PlanStorefront?) {
    guard !reported, let shown, shown.showSubscriptionUi else { return }
    reported = true
    AnalyticsManager.shared.paywallOpened(source: source, currentPlan: shown.current?.planId ?? "unknown")
  }
}

/// Budget nudge (80%) and exhausted entry (100%). Dark unless both desktop flags are on and
/// the backend reports a ladder usage budget. The sheet opens with `trigger=usage_budget`,
/// the backend's exhausted surface (Pro sees Architect there and nowhere else).
struct StorefrontBudgetEntry: View {
  var livePlanId: String?
  var busyPriceId: String?
  var error: String?
  var reloadKey: String = ""
  let onPurchase: (PlanStorefront.Tier, PlanStorefront.Price) -> Void
  let onManage: () -> Void

  @State private var data: PlanStorefront?
  @State private var showingSheet = false
  @AppStorage("storefront.budgetNudgeDismissedPeriod") private var dismissedPeriod = ""

  var body: some View {
    Group {
      if let data, data.budgetExhausted || (data.showsBudgetNudge && data.usage.periodId != dismissedPeriod) {
        StorefrontBudgetBanner(
          data: data, onOpen: { showingSheet = true },
          onDismiss: { dismissedPeriod = data.usage.periodId ?? "" })
      }
    }
    .task(id: reloadKey) {
      guard PlanStorefrontGate.contextualEnabled else { return }
      data = try? await APIClient.shared.getStorefront(source: "macos_usage_limit", trigger: .usageBudget)
    }
    .sheet(isPresented: $showingSheet) {
      ScrollView {
        StorefrontPlansSection(
          source: "macos_usage_limit", trigger: .usageBudget, initial: data, livePlanId: livePlanId,
          busyPriceId: busyPriceId, error: error, reloadKey: reloadKey,
          onPurchase: { tier, price in
            showingSheet = false
            onPurchase(tier, price)
          },
          onManage: onManage
        )
        .padding(OmiSpacing.xxl)
      }
      .frame(width: 520, height: 640)
      .overlay(alignment: .topTrailing) {
        Button("Close") { showingSheet = false }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
          .keyboardShortcut(.cancelAction)
          .padding(OmiSpacing.md)
      }
    }
  }
}

/// Context entry only where a feature already exists. Server gate/cap + both flags are required.
struct StorefrontFeatureEntry: View {
  let trigger: PlanStorefront.Trigger
  var livePlanId: String?
  let onPurchase: (PlanStorefront.Tier, PlanStorefront.Price) -> Void
  let onManage: () -> Void
  @State private var data: PlanStorefront?
  @State private var showing = false

  private var eligible: Bool {
    guard let data, data.showSubscriptionUi, data.current?.legacy == false else { return false }
    return trigger == .mcpDailyCap ? data.usage.mcpCapReached : data.shouldGate(trigger, livePlanId: livePlanId)
  }
  var body: some View {
    Group {
      if eligible, let data {
        Button(data.header ?? "Plans") { showing = true }
          .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      }
    }
    .task(id: livePlanId) {
      data = nil
      guard PlanStorefrontGate.contextualEnabled else { return }
      data = try? await APIClient.shared.getStorefront(source: "macos_" + trigger.rawValue, trigger: trigger)
    }
    .sheet(isPresented: $showing) {
      ScrollView {
        StorefrontPlansSection(
          source: "macos_" + trigger.rawValue, trigger: trigger, initial: data,
          livePlanId: livePlanId,
          onPurchase: { tier, price in
            showing = false
            onPurchase(tier, price)
          }, onManage: onManage
        )
        .padding(OmiSpacing.xxl)
      }.frame(width: 520, height: 640)
    }
  }
}
