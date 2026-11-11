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
    guard enabled else { return }
    observation.view([
      "source": source, "current_plan": currentPlan, "surface": surface,
      "catalog_tier": "not_applicable",
    ])
  }
  func body(content: Content) -> some View {
    content.onAppear { record() }.onChange(of: enabled) { _, _ in record() }
  }

}

extension View {
  func purchaseExposure(source: String, currentPlan: String = "unknown", surface: String, enabled: Bool = true)
    -> some View
  {
    modifier(PurchaseExposureModifier(source: source, currentPlan: currentPlan, surface: surface, enabled: enabled))
  }
}
