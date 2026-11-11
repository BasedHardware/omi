import Foundation

@main
struct CoordinatorTests {
  @MainActor static func main() async {
    for outcome in [BillingWebFlowOutcome.completed, .cancelled, .dismissed] {
      var events: [PurchaseEvent] = []
      var sources: [String] = []
      let observation = PurchaseCheckoutObservation(
        context: PurchaseCheckoutContext(plan: "unlimited_v2", interval: "year", source: "macos_usage_limit"),
        sink: { event, properties in
          events.append(event)
          sources.append(properties["source"] ?? "unknown")
        })
      let flow = BillingWebFlow(
        title: "Fixture", url: URL(string: "https://fixture.invalid/checkout")!,
        completionURLs: ["https://fixture.invalid/v1/payments/success", "https://fixture.invalid/v1/payments/cancel"],
        purchase: observation)
      observation.opened()
      var callbacks = 0
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        let coordinator = BillingWebView.Coordinator(
          flow: flow,
          onComplete: { _ in
            callbacks += 1
            continuation.resume()
          })
        coordinator.finish(outcome)
        coordinator.finish(.completed)  // A late callback cannot change the terminal observation.
      }
      precondition(callbacks == 1)
      precondition(sources.allSatisfy { $0 == "macos_usage_limit" })
      precondition(events.filter { $0 == .checkoutOpened }.count == 1)
      if case .completed = outcome {
        precondition(events.filter { $0 == .checkoutCompleted }.count == 1)
      } else {
        precondition(!events.contains(.checkoutCompleted))
      }
    }
    print(
      "PASS: actual native BillingWebView coordinator success/cancel/dismiss boundaries and SwiftUI modifier compile")
  }
}
