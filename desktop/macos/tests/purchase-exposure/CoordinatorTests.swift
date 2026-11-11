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
        if case .completed = outcome {
          precondition(
            coordinator.handleNavigation(
              URL(string: "https://fixture.invalid/v1/payments/success?session_id=fixture")!, isMainFrame: true)
          )
        } else {
          coordinator.finish(outcome)
        }
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
    // Real coordinator navigation entry: legacy port/userinfo aliases still resolve UI, but never telemetry.
    for raw in [
      "https://fixture.invalid:444/v1/payments/success",
      "https://user@fixture.invalid/v1/payments/success",
    ] {
      var completed = 0
      let observation = PurchaseCheckoutObservation(
        context: PurchaseCheckoutContext(plan: "plus", interval: "month", source: "macos_billing"),
        sink: { event, _ in if event == .checkoutCompleted { completed += 1 } })
      observation.opened()
      let flow = BillingWebFlow(
        title: "Fixture", url: URL(string: "https://fixture.invalid/checkout")!,
        completionURLs: ["https://fixture.invalid/v1/payments/success"], purchase: observation)
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        let coordinator = BillingWebView.Coordinator(
          flow: flow,
          onComplete: { outcome in
            guard case .completed = outcome else { preconditionFailure("legacy outcome changed") }
            continuation.resume()
          })
        precondition(coordinator.handleNavigation(URL(string: raw)!, isMainFrame: true))
        coordinator.handleNavigation(URL(string: "https://fixture.invalid/v1/payments/success")!, isMainFrame: true)
      }
      precondition(completed == 0)
    }
    // Otherwise-trusted subframe/missing-target success retains legacy UI, without new completion.
    for isMainFrame: Bool? in [false, nil] {
      var completed = 0
      var callbacks = 0
      let observation = PurchaseCheckoutObservation(
        context: PurchaseCheckoutContext(plan: "plus", interval: "month", source: "macos_billing"),
        sink: { event, _ in if event == .checkoutCompleted { completed += 1 } })
      observation.opened()
      let flow = BillingWebFlow(
        title: "Fixture", url: URL(string: "https://fixture.invalid/checkout")!,
        completionURLs: ["https://fixture.invalid/v1/payments/success"], purchase: observation)
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        let coordinator = BillingWebView.Coordinator(
          flow: flow,
          onComplete: { outcome in
            guard case .completed = outcome else { preconditionFailure("legacy outcome changed") }
            callbacks += 1
            continuation.resume()
          })
        precondition(
          coordinator.handleNavigation(
            URL(string: "https://fixture.invalid/v1/payments/success?session_id=fixture")!, isMainFrame: isMainFrame))
        coordinator.handleNavigation(URL(string: "https://fixture.invalid/v1/payments/success")!, isMainFrame: true)
      }
      precondition(callbacks == 1 && completed == 0)
    }
    // Dismiss/failure terminal state wins over a later trusted navigation.
    for failed in [false, true] {
      var completed = 0
      let observation = PurchaseCheckoutObservation(
        context: PurchaseCheckoutContext(plan: "plus", interval: "month", source: "macos_billing"),
        sink: { event, _ in if event == .checkoutCompleted { completed += 1 } })
      let flow = BillingWebFlow(
        title: "Fixture", url: URL(string: "https://fixture.invalid/checkout")!,
        completionURLs: ["https://fixture.invalid/v1/payments/success"], purchase: observation)
      observation.opened()
      if failed { observation.finish(success: false) }
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        let coordinator = BillingWebView.Coordinator(flow: flow, onComplete: { _ in continuation.resume() })
        if !failed { coordinator.finish(.dismissed) }
        coordinator.handleNavigation(URL(string: "https://fixture.invalid/v1/payments/success")!, isMainFrame: true)
      }
      precondition(completed == 0)
    }
    print(
      "PASS: actual native BillingWebView coordinator success/cancel/dismiss boundaries and SwiftUI modifier compile")
  }
}
