import Foundation

/// Owns purchase observations for one rendering lifetime or authoritative snapshot.
/// Deduplicates telemetry only; no user keys, payment authority, or clocks.
final class PurchaseObservation {
  typealias Sink = (PurchaseEvent, [String: String]) -> Void
  private let sink: Sink
  private var viewed = false
  private var active: Set<String> = []
  init(sink: @escaping Sink) { self.sink = sink }
  func view(_ raw: [String: String], enabled: Bool = true) {
    guard enabled, !viewed else { return }
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
  /// Rendered hard block, including a warning that becomes blocked while mounted.
  /// Optimistic refusal is presentation evidence only, with an unknown server cause.
  func chatBlock(shown: Bool, authoritative: Bool) {
    allowance(
      shown, kind: "chat", surface: "chat",
      reason: authoritative ? "chat_quota_exhausted" : "unknown", block: true)
  }
  /// Called only by a mounted usage-limit popup. Presentation is independent of server reach.
  func usageLimitBlock(reason: String, chatAuthoritative: Bool) {
    let candidate = reason == "trial_expired" ? "trial" : reason == "floating_bar" ? "chat" : reason
    let kind = ["transcription", "trial", "chat"].contains(candidate) ? candidate : "unknown"
    let authoritative = kind != "unknown" && (kind != "chat" || chatAuthoritative)
    let cause =
      !authoritative
      ? "unknown"
      : kind == "trial" ? "trial_expired" : kind == "chat" ? "chat_quota_exhausted" : "plan_allowance_exhausted"
    allowance(true, kind: kind, surface: kind == "transcription" ? "capture" : "chat", reason: cause, block: true)
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
  /// Strict observation only. The legacy matcher below still owns product resolution.
  static func verifiedMatches(_ url: URL, completionURL: URL) -> Bool {
    guard let actual = URLComponents(url: url, resolvingAgainstBaseURL: false),
      let expected = URLComponents(url: completionURL, resolvingAgainstBaseURL: false),
      let scheme = expected.scheme?.lowercased(), ["http", "https"].contains(scheme),
      actual.user == nil, actual.password == nil, expected.user == nil, expected.password == nil
    else { return false }
    let defaultPort = scheme == "https" ? 443 : 80
    return actual.scheme?.lowercased() == scheme && actual.host?.lowercased() == expected.host?.lowercased()
      && expected.host != nil && (actual.port ?? defaultPort) == (expected.port ?? defaultPort)
      && actual.percentEncodedPath == expected.percentEncodedPath
  }
  /// Same completion URL comparison the WKWebView rail already used.
  static func matches(_ url: URL, completionURL: URL) -> Bool {
    url.scheme == completionURL.scheme && url.host == completionURL.host && url.path == completionURL.path
      && (url.query == completionURL.query || completionURL.query == nil)
  }
}
