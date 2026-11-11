import SwiftUI

private struct PurchaseExposureModifier: ViewModifier {
  let source: String
  let currentPlan: String
  let surface: String
  let enabled: Bool
  @State private var observation = PurchaseObservation(sink: { event, properties in
    AnalyticsManager.shared.purchaseEvent(event, properties)
  })
  private func record() {
    observation.view(
      [
        "source": source, "current_plan": currentPlan, "surface": surface,
        "catalog_tier": "not_applicable",
      ], enabled: enabled)
  }
  func body(content: Content) -> some View {
    content.onAppear { record() }.onChange(of: enabled) { _, _ in record() }
  }

}

private struct PurchaseAllowanceBlockModifier: ViewModifier {
  let shown: Bool
  let authoritative: Bool
  @State private var observation = PurchaseObservation(sink: { event, properties in
    AnalyticsManager.shared.purchaseEvent(event, properties)
  })
  private func record() {
    observation.chatBlock(shown: shown, authoritative: authoritative)
  }
  func body(content: Content) -> some View {
    content.onAppear { record() }.onChange(of: shown) { _, _ in record() }
  }
}

extension View {
  func purchaseChatAllowanceBlock(shown: Bool, authoritative: Bool) -> some View {
    modifier(
      PurchaseAllowanceBlockModifier(
        shown: shown, authoritative: authoritative))
  }

  func purchaseExposure(source: String, currentPlan: String = "unknown", surface: String, enabled: Bool = true)
    -> some View
  {
    modifier(PurchaseExposureModifier(source: source, currentPlan: currentPlan, surface: surface, enabled: enabled))
  }
}
