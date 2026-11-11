import Foundation

/// Owns purchase observations for one rendering lifetime or authoritative snapshot.
/// Deduplicates telemetry only; no user keys, payment authority, or clocks.
final class PurchaseObservation {
  typealias Sink = (PurchaseEvent, [String: String]) -> Void
  private let sink: Sink
  private var viewed = false
  private var active: Set<String> = []
  init(sink: @escaping Sink) { self.sink = sink }
  func view(_ raw: [String: String]) {
    guard !viewed else { return }
    viewed = true
    sink(.paywallViewed, PurchaseContract.properties(.paywallViewed, raw))
  }
  func allowance(_ reached: Bool, kind: String, surface: String, reason: String, block: Bool = false) {
    let event: PurchaseEvent = block ? .allowanceBlockShown : .allowanceReached
    let raw = PurchaseContract.properties(event, ["allowance_kind": kind, "surface": surface, "reason": reason])
    let key = event.rawValue + (raw["allowance_kind"] ?? "unknown") + (raw["surface"] ?? "unknown")
    if !reached {
      active.remove(key)
      return
    }
    guard active.insert(key).inserted else { return }
    sink(event, raw)
  }
}

struct PurchaseCheckoutContext {
  let plan: String
  let interval: String
  let source: String
  var properties: [String: String] {
    ["plan": plan, "billing_interval": interval, "source": source, "stage": "in_app_checkout"]
  }
}

/// Owns the existing success-navigation boundary, not payment or entitlement.
final class PurchaseCheckoutObservation {
  private let context: PurchaseCheckoutContext
  private let sink: PurchaseObservation.Sink
  private var didOpen = false
  private var terminal = false
  init(context: PurchaseCheckoutContext, sink: @escaping PurchaseObservation.Sink) {
    self.context = context
    self.sink = sink
  }
  static func tapped(context: PurchaseCheckoutContext, sink: PurchaseObservation.Sink) {
    sink(.upgradeTapped, PurchaseContract.properties(.upgradeTapped, context.properties))
  }
  func opened() {
    guard !didOpen, !terminal else { return }
    didOpen = true
    var properties = context.properties
    properties["result"] = "opened"
    sink(.checkoutOpened, PurchaseContract.properties(.checkoutOpened, properties))
  }
  func finish(success: Bool) {
    guard !terminal else { return }
    terminal = true
    guard success else { return }
    var properties = context.properties
    properties["result"] = "client_navigation_completed"
    sink(.checkoutCompleted, PurchaseContract.properties(.checkoutCompleted, properties))
  }
  /// Same completion URL comparison the WKWebView rail already used.
  static func matches(_ url: URL, completionURL: URL) -> Bool {
    url.scheme == completionURL.scheme && url.host == completionURL.host && url.path == completionURL.path
      && (url.query == completionURL.query || completionURL.query == nil)
  }
}
