import Foundation

var events: [(PurchaseEvent, [String: String])] = []
let sink: PurchaseObservation.Sink = { events.append(($0, $1)) }
let observer = PurchaseObservation(sink: sink)
let view = [
  "source": "macos_settings_view", "surface": "settings_plans", "current_plan": "basic",
  "catalog_tier": "not_applicable",
]
observer.view(view)
observer.view(view)
precondition(events.filter { $0.0 == .paywallViewed }.count == 1)
PurchaseObservation(sink: sink).view(view)
precondition(events.filter { $0.0 == .paywallViewed }.count == 2)
observer.allowance(false, kind: "chat", surface: "chat", reason: "chat_quota_exhausted")
observer.allowance(true, kind: "chat", surface: "chat", reason: "chat_quota_exhausted")
observer.allowance(true, kind: "chat", surface: "chat", reason: "chat_quota_exhausted")
precondition(events.filter { $0.0 == .allowanceReached }.count == 1)
precondition(events.filter { $0.0 == .allowanceBlockShown }.isEmpty)
observer.allowance(true, kind: "chat", surface: "chat", reason: "chat_quota_exhausted", block: true)
observer.allowance(true, kind: "chat", surface: "chat", reason: "chat_quota_exhausted", block: true)
precondition(events.filter { $0.0 == .allowanceBlockShown }.count == 1)
observer.allowance(false, kind: "chat", surface: "chat", reason: "chat_quota_exhausted")
observer.allowance(true, kind: "chat", surface: "chat", reason: "chat_quota_exhausted")
precondition(events.filter { $0.0 == .allowanceReached }.count == 2)
let context = PurchaseCheckoutContext(plan: "unlimited_v2", interval: "year", source: "macos_settings_view")
PurchaseCheckoutObservation.tapped(context: context, sink: sink)
precondition(events.filter { $0.0 == .upgradeTapped }.count == 1)
let checkout = PurchaseCheckoutObservation(context: context, sink: sink)
precondition(events.filter { $0.0 == .checkoutOpened || $0.0 == .checkoutCompleted }.isEmpty)
checkout.opened()
checkout.opened()
precondition(events.filter { $0.0 == .checkoutOpened }.count == 1)
precondition(events.filter { $0.0 == .checkoutCompleted }.isEmpty)
checkout.finish(success: true)
checkout.finish(success: true)
precondition(events.filter { $0.0 == .checkoutCompleted }.count == 1)
for _ in ["cancel", "dismiss", "failure"] {
  let failed = PurchaseCheckoutObservation(context: context, sink: sink)
  failed.opened()
  failed.finish(success: false)
  failed.finish(success: true)
}
precondition(events.filter { $0.0 == .checkoutCompleted }.count == 1)
let success = URL(string: "https://fixture.invalid/v1/payments/success")!
precondition(PurchaseCheckoutObservation.matches(success, completionURL: success))
for path in [
  "https://other.invalid/v1/payments/success", "https://fixture.invalid/v1/payments/cancel",
  "https://fixture.invalid/v1/payments/success-other",
] {
  precondition(!PurchaseCheckoutObservation.matches(URL(string: path)!, completionURL: success))
}
for event: PurchaseEvent in [
  .paywallViewed, .upgradeTapped, .checkoutOpened, .checkoutCompleted, .allowanceReached, .allowanceBlockShown,
  .restoreAttempted, .restoreResult,
] {
  let output = PurchaseContract.properties(
    event, ["source": "private", "plan": "private", "url": "private", "uid": "private", "error": "private"])
  precondition(!output.values.contains("private"))
  precondition(output["url"] == nil && output["uid"] == nil && output["error"] == nil)
}
print("PASS: native purchase presentation, allowance, checkout navigation/terminal and privacy boundaries")

// The actual popup's observation mapping counts optimistic UI, not server exhaustion.
var popupEvents: [(PurchaseEvent, [String: String])] = []
let popupSink: PurchaseObservation.Sink = { popupEvents.append(($0, $1)) }
let popup = PurchaseObservation(sink: popupSink)
popup.usageLimitBlock(reason: "floating_bar", chatAuthoritative: false)
popup.usageLimitBlock(reason: "floating_bar", chatAuthoritative: false)
precondition(popupEvents.count == 1 && popupEvents[0].0 == .allowanceBlockShown)
precondition(popupEvents[0].1["reason"] == "unknown" && popupEvents[0].1["allowance_kind"] == "chat")
PurchaseObservation(sink: popupSink).usageLimitBlock(reason: "floating_bar", chatAuthoritative: false)
precondition(popupEvents.count == 2)  // Dismiss/remount gets a fresh presentation lifetime.
PurchaseObservation(sink: popupSink).usageLimitBlock(reason: "chat", chatAuthoritative: true)
precondition(popupEvents.last?.1["reason"] == "chat_quota_exhausted")
precondition(!popupEvents.contains { $0.0 == .allowanceReached })
for raw in [
  "https://fixture.invalid:444/v1/payments/success", "https://user@fixture.invalid/v1/payments/success",
  "https://@fixture.invalid/v1/payments/success", "http://fixture.invalid/v1/payments/success",
  "https://other.invalid/v1/payments/success", "https://fixture.invalid.evil.invalid/v1/payments/success",
  "https://fixture.invalid/v1/payments/success-extra", "https://fixture.invalid/v1/payments/success/",
] {
  precondition(!PurchaseCheckoutObservation.verifiedMatches(URL(string: raw)!, completionURL: success))
}
precondition(
  PurchaseCheckoutObservation.verifiedMatches(
    URL(string: "https://fixture.invalid:443/v1/payments/success?session_id=fixture")!, completionURL: success))
precondition(
  PurchaseCheckoutObservation.verifiedMatches(
    URL(string: "http://fixture.invalid:80/v1/payments/success")!,
    completionURL: URL(string: "http://fixture.invalid/v1/payments/success")!))
print("PASS: popup optimism is visible block only; strict origin/port/path/userinfo observation")

// Actual production transition observer: warning -> optimistic block -> authoritative
// block is one presentation. Recovery/remount rearm; updates cannot create a reach.
var bannerEvents: [(PurchaseEvent, [String: String])] = []
let bannerSink: PurchaseObservation.Sink = { bannerEvents.append(($0, $1)) }
let banner = PurchaseObservation(sink: bannerSink)
banner.chatBlock(shown: false, authoritative: false)
precondition(bannerEvents.isEmpty)
banner.chatBlock(shown: true, authoritative: false)
banner.chatBlock(shown: true, authoritative: false)
banner.chatBlock(shown: true, authoritative: true)
precondition(bannerEvents.count == 1 && bannerEvents[0].1["reason"] == "unknown")
banner.chatBlock(shown: false, authoritative: true)
banner.chatBlock(shown: true, authoritative: true)
precondition(bannerEvents.count == 2 && bannerEvents[1].1["reason"] == "chat_quota_exhausted")
PurchaseObservation(sink: bannerSink).chatBlock(shown: true, authoritative: true)
precondition(bannerEvents.count == 3 && bannerEvents.allSatisfy { $0.0 == .allowanceBlockShown })
print("PASS: mounted warning/block transitions, rebuild dedupe, recovery and remount")

// Empty/filtered asynchronous catalogs must leave the mounted view latch unused.
var gridEvents: [PurchaseEvent] = []
let grid = PurchaseObservation(sink: { event, _ in gridEvents.append(event) })
grid.view(view, enabled: false)
grid.view(view, enabled: false)
precondition(gridEvents.isEmpty)
grid.view(view, enabled: true)
grid.view(view, enabled: true)
grid.view(view, enabled: false)
grid.view(view, enabled: true)
precondition(gridEvents == [.paywallViewed])
print("PASS: native empty-to-options view eligibility and per-mount latch")
