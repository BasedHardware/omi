import OmiTheme
import SwiftUI

/// Analytics and endpoint seams for the cancel flow.
/// Keeps the sheet's state machine testable without PostHog or the network.
struct CancelFlowAnalytics {
  var started: () -> Void
  var reasonSelected: (String?) -> Void
  var confirmed: (String?, Bool) -> Void
  var keptPlan: (Int, String?) -> Void
  var abandoned: (Int, String?) -> Void

  @MainActor static var live: CancelFlowAnalytics {
    CancelFlowAnalytics(
      started: { AnalyticsManager.shared.subscriptionCancelFlowStarted() },
      reasonSelected: { AnalyticsManager.shared.subscriptionCancelReasonSelected(reason: $0) },
      confirmed: { AnalyticsManager.shared.subscriptionCancelConfirmed(reason: $0, hasDetails: $1) },
      keptPlan: { AnalyticsManager.shared.subscriptionCancelKeptPlan(step: $0, reason: $1) },
      abandoned: { AnalyticsManager.shared.subscriptionCancelAbandoned(step: $0, reason: $1) })
  }

  static var silent: CancelFlowAnalytics {
    CancelFlowAnalytics(
      started: {}, reasonSelected: { _ in }, confirmed: { _, _ in },
      keptPlan: { _, _ in }, abandoned: { _, _ in })
  }
}

enum CancelFlowStep: Int {
  case reason = 1
  case feedback = 2
  case confirm = 3
  case done = 4
}

/// The mobile cancel flow's state machine (SCA-2171): reason, optional feedback,
/// the consequences step with the existing retention offer, then the
/// destructive confirm. Endpoints are the existing mobile ones.
@MainActor
final class CancelFlowController: ObservableObject {
  @Published private(set) var step: CancelFlowStep = .reason
  @Published var reason: String?
  @Published var details = ""
  @Published private(set) var offer: RetentionOfferResponse?
  @Published private(set) var isLoadingOffer = false
  @Published private(set) var isCancelling = false
  @Published private(set) var isAcceptingOffer = false
  @Published private(set) var errorMessage: String?
  @Published private(set) var appliedPercent: Int?
  @Published private(set) var finished = false

  let periodEnd: Int?
  private let loadOffer: () async -> RetentionOfferResponse?
  private let acceptOffer: () async throws -> RetentionOfferResponse
  private let cancelSubscription: (String, String?) async throws -> Void
  /// Set to `.live` by the production view; the controller starts silent so
  /// tests and render harnesses cannot emit events.
  var analytics: CancelFlowAnalytics?

  var busy: Bool { isCancelling || isAcceptingOffer }

  init(
    periodEnd: Int?,
    loadOffer: (() async -> RetentionOfferResponse?)? = nil,
    acceptOffer: (() async throws -> RetentionOfferResponse)? = nil,
    cancelSubscription: ((String, String?) async throws -> Void)? = nil
  ) {
    self.periodEnd = periodEnd
    self.loadOffer = loadOffer ?? { try? await APIClient.shared.getRetentionOffer() }
    self.acceptOffer = acceptOffer ?? { try await APIClient.shared.acceptRetentionOffer() }
    self.cancelSubscription =
      cancelSubscription ?? { reason, details in
        try await APIClient.shared.cancelSubscription(reason: reason, reasonDetails: details)
      }
  }

  func start() {
    analytics?.started()
  }

  func advanceFromReason() {
    guard let reason else { return }
    analytics?.reasonSelected(reason)
    step = .feedback
  }

  func advanceFromFeedback() {
    step = .confirm
  }

  func loadOfferIfNeeded() async {
    guard step == .confirm, !finished else { return }
    isLoadingOffer = true
    let loaded = await loadOffer()
    if let loaded, loaded.eligible, loaded.discountedAmount != nil {
      offer = loaded
    } else {
      offer = nil
    }
    isLoadingOffer = false
  }

  func confirmCancel() async {
    guard let reason, !busy else { return }
    errorMessage = nil
    isCancelling = true
    let trimmed = details.trimmingCharacters(in: .whitespacesAndNewlines)
    let detailsValue = trimmed.isEmpty ? nil : trimmed
    analytics?.confirmed(reason, detailsValue != nil)
    do {
      try await cancelSubscription(reason, detailsValue)
      finished = true
      step = .done
    } catch {
      // Cancellation stays reachable after a failure: same screen, enabled
      // destructive button, inline error.
      errorMessage = "Failed to cancel subscription. Please try again."
    }
    isCancelling = false
  }

  func applyOffer() async {
    guard !busy else { return }
    errorMessage = nil
    isAcceptingOffer = true
    do {
      let result = try await acceptOffer()
      finished = true
      appliedPercent = result.percentOff
      offer = result
      step = .done
    } catch {
      errorMessage = "Could not apply the offer. You can still cancel below."
    }
    isAcceptingOffer = false
  }

  func keepPlan() {
    finished = true
    analytics?.keptPlan(3, reason)
  }

  func abandon() {
    guard !finished else { return }
    finished = true
    analytics?.abandoned(step.rawValue, reason)
  }

  /// Test/render seam: jump straight to a captured state.
  func preview(step: CancelFlowStep, reason: String?, details: String = "", offer: RetentionOfferResponse?) {
    self.step = step
    self.reason = reason
    self.details = details
    self.offer = offer
    isLoadingOffer = false
    appliedPercent = step == .done ? 50 : nil
    finished = step == .done
  }
}

/// The mobile cancel flow on macOS (SCA-2171). Copy is the shipped mobile
/// English copy, string for string, so web, macOS and mobile match word for
/// word. Manage (Stripe portal) is unchanged.
struct CancelSubscriptionFlowSheet: View {
  /// `CANCEL_FLOW_PARITY_ENABLED`; the Omi flag store answers, and any missing
  /// answer keeps today's Manage-only path. The flag never gates cancellation.
  static let featureFlagKey = "cancel_flow_parity"

  /// Read from a plain (non-view-body) accessor, so it hops to the main actor
  /// rather than relying on the caller's isolation.
  nonisolated static var isEnabled: Bool {
    MainActor.assumeIsolated { PostHogManager.shared.isFeatureEnabled(featureFlagKey) }
  }

  @StateObject private var controller: CancelFlowController
  private let onClose: () -> Void
  private let onSubscriptionChanged: () -> Void
  private let analytics: CancelFlowAnalytics?
  private let previewStep: CancelFlowStep?
  private let previewReason: String?
  private let previewOffer: RetentionOfferResponse?
  private let previewDetails: String

  init(
    periodEnd: Int?,
    onClose: @escaping () -> Void,
    onSubscriptionChanged: @escaping () -> Void,
    loadOffer: (() async -> RetentionOfferResponse?)? = nil,
    acceptOffer: (() async throws -> RetentionOfferResponse)? = nil,
    cancelSubscription: ((String, String?) async throws -> Void)? = nil,
    analytics: CancelFlowAnalytics? = nil,
    previewStep: CancelFlowStep? = nil,
    previewReason: String? = nil,
    previewDetails: String = "",
    previewOffer: RetentionOfferResponse? = nil
  ) {
    _controller = StateObject(
      wrappedValue: CancelFlowController(
        periodEnd: periodEnd,
        loadOffer: loadOffer,
        acceptOffer: acceptOffer,
        cancelSubscription: cancelSubscription))
    self.onClose = onClose
    self.analytics = analytics
    self.onSubscriptionChanged = onSubscriptionChanged
    self.previewStep = previewStep
    self.previewReason = previewReason
    self.previewOffer = previewOffer
    self.previewDetails = previewDetails
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack {
        Text("Step \(min(controller.step.rawValue, 3)) of 3")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.tertiary)
        Spacer()
        DismissButton(action: close)
          .disabled(controller.busy)
      }

      switch controller.step {
      case .reason: reasonStep
      case .feedback: feedbackStep
      case .confirm: confirmStep
      case .done: doneStep
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(minWidth: 460, minHeight: 560)
    .background(Ink.surface)
    .onAppear {
      if let previewStep {
        controller.preview(
          step: previewStep, reason: previewReason, details: previewDetails, offer: previewOffer)
      } else {
        controller.analytics = analytics ?? .live
        controller.start()
      }
    }
    .task(id: controller.step) {
      await controller.loadOfferIfNeeded()
    }
  }

  // MARK: - Steps

  private var reasonStep: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Why are you canceling?")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("Can you tell us why you're leaving?")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      VStack(spacing: OmiSpacing.xs) {
        ForEach(CancelFlowReason.all) { option in
          reasonTile(option)
        }
      }
      .padding(.top, OmiSpacing.xs)

      Button("Continue") { controller.advanceFromReason() }
        .buttonStyle(OmiButtonStyle(.primary))
        .disabled(controller.reason == nil)
        .accessibilityIdentifier("cancel-flow-continue")
    }
  }

  private var feedbackStep: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text(CancelFlowCopy.feedbackTitle(controller.reason))
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text(CancelFlowCopy.feedbackSubtitle(controller.reason))
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      TextEditor(text: $controller.details)
        .scaledFont(size: OmiType.body)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.sm)
        .frame(minHeight: 120)
        .background(RoundedRectangle(cornerRadius: 10).fill(Ink.rowFill))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Ink.hairline, lineWidth: 1))
        .onChange(of: controller.details) { _, value in
          if value.count > 300 { controller.details = String(value.prefix(300)) }
        }
        .accessibilityIdentifier("cancel-flow-details")

      Button("Continue") { controller.advanceFromFeedback() }
        .buttonStyle(OmiButtonStyle(.primary))
      Button("Skip for Now") { controller.advanceFromFeedback() }
        .buttonStyle(OmiButtonStyle(.secondary))
    }
  }

  private var confirmStep: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Just a moment, please")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text("We highly recommend exploring your other options instead of canceling.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      if controller.isLoadingOffer {
        HStack(spacing: OmiSpacing.xs) {
          ProgressView().controlSize(.small)
          Text("Checking for an offer…")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }

      if let offer = controller.offer {
        notice(icon: "tag.fill", text: CancelFlowCopy.offerBody(offer), tint: Ink.listeningGreen)
      }

      if let date = CancelFlowCopy.periodEnd(controller.periodEnd) {
        notice(
          icon: "info.circle.fill",
          text:
            "Your plan will remain active until \(date). After that, you'll be moved to the free version with limited features.",
          tint: SettingsInk.notice)
      }

      Text("If you cancel:")
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.primary)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        ForEach(CancelFlowCopy.consequences, id: \.self) { line in
          HStack(alignment: .top, spacing: OmiSpacing.xs) {
            Text("•").foregroundColor(Ink.tertiary)
            Text(line)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }

      if let error = controller.errorMessage {
        Text(error)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.errorRed)
          .fixedSize(horizontal: false, vertical: true)
      }

      if let offer = controller.offer {
        Button("Stay for \(offer.percentOff)% off") {
          Task {
            await controller.applyOffer()
            if controller.finished { onSubscriptionChanged() }
          }
        }
        .buttonStyle(OmiButtonStyle(.primary))
        .disabled(controller.busy)
        .accessibilityIdentifier("cancel-flow-stay")
      } else {
        Button("Keep Subscription") {
          controller.keepPlan()
          onClose()
        }
        .buttonStyle(OmiButtonStyle(.primary))
        .disabled(controller.isCancelling)
        .accessibilityIdentifier("cancel-flow-keep")
      }

      Button("Cancel Subscription") {
        Task {
          await controller.confirmCancel()
          if controller.finished { onSubscriptionChanged() }
        }
      }
      .buttonStyle(OmiButtonStyle(.destructive))
      .disabled(controller.isAcceptingOffer)
      .accessibilityIdentifier("cancel-flow-confirm")
    }
  }

  private var doneStep: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: OmiType.title)
        .foregroundColor(Ink.listeningGreen)
      Text(controller.appliedPercent == nil ? "Subscription cancelled" : "Offer applied")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)
      Text(
        controller.appliedPercent.map { "Done. \($0)% off your next \(controller.offer?.durationMonths ?? 3) months." }
          ?? "Your subscription is set to cancel at the end of the period."
      )
      .scaledFont(size: OmiType.body)
      .foregroundColor(Ink.secondary)
      .multilineTextAlignment(.center)
      Button("Done") { close() }
        .buttonStyle(OmiButtonStyle(.primary))
    }
    .frame(maxWidth: .infinity)
    .padding(.top, OmiSpacing.xxl)
  }

  // MARK: - Pieces

  private func reasonTile(_ option: CancelFlowReason) -> some View {
    let selected = controller.reason == option.key
    return Button {
      controller.reason = option.key
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: option.symbol)
          .frame(width: 18)
          .foregroundColor(selected ? Ink.primary : Ink.secondary)
        Text(option.label)
          .scaledFont(size: OmiType.body)
          .foregroundColor(selected ? Ink.primary : Ink.secondary)
        Spacer()
        if selected {
          Image(systemName: "checkmark").foregroundColor(Ink.primary)
        }
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(selected ? Ink.rowFillHover : Ink.rowFill)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .stroke(selected ? Ink.hairline : Color.clear, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("cancel-flow-reason-\(option.key)")
  }

  private func notice(icon: String, text: String, tint: Color) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.xs) {
      Image(systemName: icon).foregroundColor(tint)
      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: 10).fill(tint.opacity(0.12)))
  }

  // MARK: - Close

  private func close() {
    controller.abandon()
    onClose()
  }
}

struct CancelFlowReason: Identifiable {
  let key: String
  let label: String
  let symbol: String
  var id: String { key }

  static let all: [CancelFlowReason] = [
    CancelFlowReason(key: "too_expensive", label: "Too expensive", symbol: "wallet.pass"),
    CancelFlowReason(key: "not_using_enough", label: "Not using it enough", symbol: "clock"),
    CancelFlowReason(key: "missing_features", label: "Missing features", symbol: "puzzlepiece.extension"),
    CancelFlowReason(key: "audio_quality", label: "Audio/transcription quality", symbol: "mic"),
    CancelFlowReason(key: "battery_drain", label: "Battery drain concerns", symbol: "battery.25"),
    CancelFlowReason(key: "found_alternative", label: "Found an alternative", symbol: "arrow.left.arrow.right"),
    CancelFlowReason(key: "other", label: "Other", symbol: "ellipsis"),
  ]
}

enum CancelFlowCopy {
  static let consequences = [
    "No longer have unlimited access at the end of your billing period.",
    "7x more battery usage (on-device processing)",
    "30% lower transcription quality (on-device models)",
    "5-7 second processing delay (on-device models)",
    "Cannot identify speakers.",
    "No real-time phone call transcription",
  ]

  static func feedbackTitle(_ reason: String?) -> String {
    switch reason {
    case "too_expensive": return "What price would work for you?"
    case "not_using_enough": return "What would make you use Omi more?"
    case "missing_features": return "What features are you missing?"
    case "audio_quality": return "What issues did you experience?"
    case "battery_drain": return "Tell us about the battery issues"
    case "found_alternative": return "What are you switching to?"
    default: return "Tell us more (optional)"
    }
  }

  static func feedbackSubtitle(_ reason: String?) -> String {
    switch reason {
    case "too_expensive": return "Your feedback helps us find the right balance."
    case "not_using_enough": return "We want to make Omi more useful for you."
    case "missing_features": return "We're always building — this helps us prioritize."
    case "audio_quality": return "We'd love to understand what went wrong."
    case "battery_drain": return "This helps our hardware team improve."
    case "found_alternative": return "We'd love to learn what caught your eye."
    default: return "We appreciate any feedback…"
    }
  }

  static func offerBody(_ offer: RetentionOfferResponse) -> String {
    "Stay and pay \(price(offer.discountedAmount ?? 0, offer.currency)) a month for the next \(offer.durationMonths) months."
  }

  static func periodEnd(_ seconds: Int?) -> String? {
    guard let seconds else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US")
    formatter.dateFormat = "MMMM d, yyyy"
    return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(seconds)))
  }

  private static let zeroDecimal: Set<String> = [
    "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "VND", "VUV", "XAF", "XOF", "XPF",
  ]
  private static let threeDecimal: Set<String> = ["BHD", "JOD", "KWD", "OMR", "TND"]

  /// Stripe minor units with the same presentation mobile uses.
  static func price(_ amountMinor: Int, _ currency: String?) -> String {
    let code = (currency ?? "usd").trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    let digits = zeroDecimal.contains(code) ? 0 : (threeDecimal.contains(code) ? 3 : 2)
    let symbol = code == "USD" ? "US$" : (code == "JPY" ? "¥" : "\(code) ")
    let value = Double(amountMinor) / pow(10, Double(digits))
    return symbol + String(format: "%.\(digits)f", value)
  }
}
