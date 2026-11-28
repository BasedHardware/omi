import OmiTheme
import SwiftUI

extension SettingsContentView {
  /// Ladder-v1 plans section, behind `desktop-plan-storefront` (default off). Replaces the
  /// local plan card and plan grid; every plan string comes from the backend payload.
  var storefrontPlanSection: some View {
    let subscription = userSubscription?.subscription
    let reloadKey = [
      subscription?.plan.rawValue ?? "", subscription?.currentPriceId ?? "",
      subscription?.cancelAtPeriodEnd == true ? "cancel" : "",
    ].joined(separator: "|")
    return VStack(spacing: OmiSpacing.lg) {
      StorefrontBudgetEntry(
        livePlanId: subscription?.plan.rawValue, busyPriceId: activeCheckoutPriceId, error: nil,
        reloadKey: reloadKey, onPurchase: { startStorefrontCheckout($0, $1, source: $2) }, onManage: openCustomerPortal)
      settingsGroup(settingId: "planusage.purchase") {
        StorefrontPlansSection(
          source: "macos_settings_view", livePlanId: subscription?.plan.rawValue,
          busyPriceId: activeCheckoutPriceId, error: subscriptionError, reloadKey: reloadKey,
          onPurchase: { startStorefrontCheckout($0, $1) }, onManage: openCustomerPortal)
      }
    }
  }

  func storefrontFeatureEntry(_ trigger: PlanStorefront.Trigger) -> some View {
    StorefrontFeatureEntry(
      trigger: trigger, livePlanId: userSubscription?.subscription.plan.rawValue,
      onPurchase: { startStorefrontCheckout($0, $1, source: $2) }, onManage: openCustomerPortal)
  }

  func startStorefrontCheckout(
    _ tier: PlanStorefront.Tier, _ price: PlanStorefront.Price, source: String = "macos_settings_view"
  ) {
    guard let priceId = price.id else { return }
    selectedPlanIdForCheckout = tier.planId
    startCheckout(for: priceId, selection: (tier.planId, price.interval.rawValue), analyticsSource: source)
  }
}
