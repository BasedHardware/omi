import AppKit
import OmiTheme
import SwiftUI

/// Renders the latest Omen: one grounded image and imperative interpreted from recent context.
struct ProjectionPage: View {
  @StateObject private var viewModel: ProjectionViewModel

  private let contentMaxWidth: CGFloat = 520
  private let imageMaxHeight: CGFloat = 420

  init(refreshesOnActivation: Bool = true) {
    _viewModel = StateObject(
      wrappedValue: ProjectionViewModel(
        refreshesOnActivation: refreshesOnActivation))
  }

  var body: some View {
    ScrollView {
      VStack(spacing: 20) {
        content
        if AppBuild.allowsLocalAutomation {
          Button(action: { Task { await viewModel.generate() } }) {
            Text(viewModel.isGenerating ? "Generating…" : "Generate omen")
          }
          .disabled(viewModel.isGenerating)
        }
      }
      .frame(maxWidth: contentMaxWidth)
      .frame(maxWidth: .infinity)
      .padding(.horizontal, 28)
      .padding(.vertical, 32)
    }
    .background(OmiColors.backgroundPrimary)
    .task {
      viewModel.registerAutomationActions()
      await viewModel.load()
    }
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      viewModel.ownerDidChange()
      Task { await viewModel.load() }
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) {
      _ in
      Task { await viewModel.refreshOnActivation() }
    }
  }

  @ViewBuilder
  private var content: some View {
    if let projection = viewModel.projection {
      VStack(alignment: .leading, spacing: 16) {
        projectionImage
        Text(projection.imperative)
          .font(.system(size: 20, weight: .semibold))
          .fixedSize(horizontal: false, vertical: true)
        if let whyThis = projection.whyThis {
          whyThisDisclosure(whyThis)
        }
        feedbackControls
      }
    } else if viewModel.isLoading {
      ProgressView()
        .frame(maxWidth: .infinity, minHeight: 240)
    } else {
      Text(viewModel.errorMessage ?? "No omen yet.")
        .frame(maxWidth: .infinity, minHeight: 240)
    }
  }

  private func whyThisDisclosure(_ receipt: ProjectionWhyThis) -> some View {
    DisclosureGroup("Why this") {
      VStack(alignment: .leading, spacing: 10) {
        ForEach(receipt.evidence) { evidence in
          Label {
            Text(evidence.label)
          } icon: {
            Image(systemName: evidence.source == "action_item" ? "checklist" : "quote.bubble")
          }
        }
        ForEach(receipt.uncertainty, id: \.self) { note in
          Text(note)
            .foregroundStyle(.secondary)
        }
      }
      .font(.system(size: 13))
      .padding(.top, 8)
    }
  }

  private var feedbackControls: some View {
    HStack(spacing: 12) {
      feedbackButton(.up, systemName: "hand.thumbsup")
      feedbackButton(.down, systemName: "hand.thumbsdown")
      if viewModel.isSubmittingFeedback {
        ProgressView().controlSize(.small)
      }
      if let error = viewModel.feedbackError {
        Text(error)
          .font(.caption)
          .foregroundStyle(.secondary)
      }
    }
  }

  private func feedbackButton(
    _ rating: ProjectionFeedbackRating,
    systemName: String
  ) -> some View {
    Button {
      Task { await viewModel.submitFeedback(rating) }
    } label: {
      Image(
        systemName: viewModel.feedbackRating == rating
          ? "\(systemName).fill"
          : systemName)
    }
    .buttonStyle(.plain)
    .disabled(viewModel.isSubmittingFeedback)
    .accessibilityLabel(rating == .up ? "Helpful omen" : "Unhelpful omen")
  }

  @ViewBuilder
  private var projectionImage: some View {
    if let image = viewModel.image {
      // Bounded so the imperative stays on screen: the generated image is 1024x1536,
      // and unbounded it pushes the line it exists to deliver below the fold.
      Image(nsImage: image)
        .resizable()
        .scaledToFit()
        .frame(maxHeight: imageMaxHeight)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    } else if viewModel.isImageLoading {
      ProgressView()
        .frame(maxWidth: .infinity, minHeight: 240)
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    } else {
      placeholder(systemName: viewModel.imageLoadFailed ? "exclamationmark.triangle" : "photo")
    }
  }

  private func placeholder(systemName: String) -> some View {
    ZStack {
      OmiColors.backgroundTertiary.opacity(0.6)
      Image(systemName: systemName)
    }
    .frame(maxWidth: .infinity, minHeight: 240)
    .clipShape(RoundedRectangle(cornerRadius: 12))
  }
}

protocol ProjectionClient: Sendable {
  func getProjections(
    limit: Int,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> [Projection]

  func generateProjection(
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> Projection?

  func getProjectionImage(
    projectionID: String,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Data

  func recordProjectionFeedback(
    projectionID: String,
    rating: ProjectionFeedbackRating,
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ProjectionFeedbackRating
}

extension APIClient: ProjectionClient {}

@MainActor
final class ProjectionViewModel: ObservableObject {
  @Published private(set) var projection: Projection?
  @Published private(set) var image: NSImage?
  @Published private(set) var isLoading = false
  @Published private(set) var isGenerating = false
  @Published private(set) var isImageLoading = false
  @Published private(set) var imageLoadFailed = false
  @Published private(set) var errorMessage: String?
  @Published private(set) var feedbackRating: ProjectionFeedbackRating?
  @Published private(set) var isSubmittingFeedback = false
  @Published private(set) var feedbackError: String?

  private let client: any ProjectionClient
  private let captureAuthorization: () -> RuntimeOwnerAuthorizationSnapshot?
  private let authorizationIsCurrent: (RuntimeOwnerAuthorizationSnapshot) -> Bool
  private let refreshesOnActivation: Bool
  private var requestGeneration: UInt64 = 0
  private var feedbackRequestGeneration: UInt64 = 0
  private var lastRefreshAt = Date.distantPast
  private var didRegisterAutomationActions = false

  init(
    client: any ProjectionClient = APIClient.shared,
    refreshesOnActivation: Bool = true,
    captureAuthorization: @escaping () -> RuntimeOwnerAuthorizationSnapshot? = {
      RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    },
    authorizationIsCurrent: @escaping (RuntimeOwnerAuthorizationSnapshot) -> Bool = {
      RuntimeOwnerIdentity.isAuthorizationCurrent($0)
    }
  ) {
    self.client = client
    self.refreshesOnActivation = refreshesOnActivation
    self.captureAuthorization = captureAuthorization
    self.authorizationIsCurrent = authorizationIsCurrent
  }

  func load(now: Date = Date()) async {
    guard let authorization = captureAuthorization() else {
      clearOwnerState()
      return
    }
    lastRefreshAt = now
    let request = beginRequest()
    isLoading = true
    defer {
      if requestGeneration == request { isLoading = false }
    }
    do {
      let nextProjection = try await client.getProjections(
        limit: 1,
        expectedOwnerId: authorization.ownerID,
        authorizationSnapshot: authorization
      ).first
      guard canApply(request, authorization: authorization) else { return }
      await apply(nextProjection, request: request, authorization: authorization)
      guard canApply(request, authorization: authorization) else { return }
      errorMessage = nil
    } catch {
      guard canApply(request, authorization: authorization) else { return }
      projection = nil
      image = nil
      feedbackRating = nil
      errorMessage = "Could not load omens: \(error.localizedDescription)"
    }
  }

  func refreshOnActivation(now: Date = Date()) async {
    guard refreshesOnActivation else { return }
    guard
      PollingConfig.shouldAllowActivationRefresh(
        now: now,
        lastRefresh: lastRefreshAt)
    else { return }
    await load(now: now)
  }

  func generate() async {
    guard let authorization = captureAuthorization() else {
      clearOwnerState()
      return
    }
    let request = beginRequest()
    isGenerating = true
    defer {
      if requestGeneration == request { isGenerating = false }
    }
    do {
      let nextProjection = try await client.generateProjection(
        expectedOwnerId: authorization.ownerID,
        authorizationSnapshot: authorization)
      guard canApply(request, authorization: authorization) else { return }
      await apply(nextProjection, request: request, authorization: authorization)
      guard canApply(request, authorization: authorization) else { return }
      errorMessage = nil
    } catch {
      guard canApply(request, authorization: authorization) else { return }
      projection = nil
      image = nil
      feedbackRating = nil
      errorMessage = "Could not generate an omen: \(error.localizedDescription)"
    }
  }

  func ownerDidChange() {
    clearOwnerState()
  }

  func submitFeedback(_ rating: ProjectionFeedbackRating) async {
    guard let projection, let authorization = captureAuthorization() else { return }
    feedbackRequestGeneration &+= 1
    let feedbackRequest = feedbackRequestGeneration
    isSubmittingFeedback = true
    feedbackError = nil
    defer {
      if feedbackRequestGeneration == feedbackRequest {
        isSubmittingFeedback = false
      }
    }
    do {
      let recorded = try await client.recordProjectionFeedback(
        projectionID: projection.id,
        rating: rating,
        expectedOwnerId: authorization.ownerID,
        authorizationSnapshot: authorization)
      guard
        feedbackRequestGeneration == feedbackRequest,
        authorizationIsCurrent(authorization),
        self.projection?.id == projection.id
      else { return }
      feedbackRating = recorded
    } catch {
      guard
        feedbackRequestGeneration == feedbackRequest,
        authorizationIsCurrent(authorization),
        self.projection?.id == projection.id
      else { return }
      feedbackError = "Feedback could not be saved."
    }
  }

  /// Registers deterministic, local-UI-only states for the typed desktop harness.
  ///
  /// The real list, generate, image, and feedback transports are verified through
  /// `ProjectionClient` and `APIClient` tests. The bridge action deliberately does
  /// not contact a provider or write a projection: it lets a named non-production
  /// bundle prove every customer-facing presentation without relying on account data.
  func registerAutomationActions() {
    guard DesktopAutomationLaunchOptions.isEnabled, !didRegisterAutomationActions else { return }
    didRegisterAutomationActions = true
    let registry = DesktopAutomationActionRegistry.shared
    registry.register(
      name: "projection_harness_state",
      summary: "Present a deterministic loading, loaded, generated, empty, or main-error Omens state",
      params: ["mode"],
      category: "projections",
      surfaces: ["projections"],
      safety: "local_ui_state",
      sideEffects: ["Changes only the current non-production Omens page state"]
    ) { [weak self] params in
      guard let self else { return ["error": "projection view model deallocated"] }
      return self.applyAutomationState(params["mode"] ?? "")
    }
    registry.register(
      name: "projection_snapshot",
      summary: "Read the current Omens page presentation state",
      category: "projections",
      surfaces: ["projections"],
      safety: "read_only"
    ) { [weak self] _ in
      guard let self else { return ["error": "projection view model deallocated"] }
      return self.automationSnapshot()
    }
  }

  private func apply(
    _ nextProjection: Projection?,
    request: UInt64,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async {
    guard let nextProjection else {
      projection = nil
      image = nil
      imageLoadFailed = false
      feedbackRating = nil
      return
    }
    guard nextProjection.imageURL != nil else {
      projection = nextProjection
      image = nil
      imageLoadFailed = true
      feedbackRating = nextProjection.feedback
      return
    }

    isImageLoading = true
    defer {
      if requestGeneration == request { isImageLoading = false }
    }
    do {
      let data = try await client.getProjectionImage(
        projectionID: nextProjection.id,
        expectedOwnerId: authorization.ownerID,
        authorizationSnapshot: authorization)
      guard canApply(request, authorization: authorization) else { return }
      guard let loadedImage = NSImage(data: data) else {
        projection = nextProjection
        image = nil
        imageLoadFailed = true
        feedbackRating = nextProjection.feedback
        return
      }
      projection = nextProjection
      image = loadedImage
      imageLoadFailed = false
      feedbackRating = nextProjection.feedback
    } catch {
      guard canApply(request, authorization: authorization) else { return }
      projection = nextProjection
      image = nil
      imageLoadFailed = true
      feedbackRating = nextProjection.feedback
    }
  }

  private func beginRequest() -> UInt64 {
    requestGeneration &+= 1
    return requestGeneration
  }

  private func canApply(
    _ request: UInt64,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) -> Bool {
    requestGeneration == request && authorizationIsCurrent(authorization)
  }

  private func applyAutomationState(_ rawMode: String) -> [String: String] {
    guard DesktopAutomationLaunchOptions.isEnabled else {
      return ["error": "projection harness states are disabled"]
    }
    requestGeneration &+= 1
    feedbackRequestGeneration &+= 1
    isLoading = false
    isGenerating = false
    isImageLoading = false
    isSubmittingFeedback = false
    feedbackError = nil
    image = nil
    feedbackRating = nil

    let mode = rawMode.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    switch mode {
    case "loading":
      projection = nil
      imageLoadFailed = false
      errorMessage = nil
      isLoading = true
    case "loaded", "generated":
      let imperative =
        mode == "loaded"
        ? "Name the choice you have been postponing."
        : "Make one small move toward the work that keeps returning."
      projection = Projection(
        id: "automation-\(mode)",
        imperative: imperative,
        imageURL: URL(string: "https://fixture.invalid/v1/projection-images/automation-\(mode).png"),
        whyThis: ProjectionWhyThis(
          evidence: [
            ProjectionEvidenceReceipt(
              reference: "action_item:automation",
              source: "action_item",
              label: "A recurring decision in recent context",
              occurredAt: nil)
          ],
          evidenceTier: "grounded",
          selectionRank: 1,
          uncertainty: ["Based on the evidence currently available."]))
      image = automationFixtureImage()
      imageLoadFailed = false
      errorMessage = nil
    case "empty":
      projection = nil
      imageLoadFailed = false
      errorMessage = nil
    case "error":
      projection = nil
      imageLoadFailed = false
      errorMessage = "Could not load omens: harness backend unavailable."
    default:
      return ["error": "mode must be loading, loaded, generated, empty, or error"]
    }
    return automationSnapshot().merging(["requested_mode": mode]) { current, _ in current }
  }

  private func automationSnapshot() -> [String: String] {
    let state: String
    if isLoading {
      state = "loading"
    } else if projection?.id == "automation-generated" {
      state = "generated"
    } else if projection != nil {
      state = "loaded"
    } else if errorMessage != nil {
      state = "error"
    } else {
      state = "empty"
    }
    let displayMessage = projection?.imperative ?? errorMessage ?? "No omen yet."
    return [
      "state": state,
      "projection_id": projection?.id ?? "",
      "imperative": projection?.imperative ?? "",
      "display_message": displayMessage,
      "evidence_count": "\(projection?.whyThis?.evidence.count ?? 0)",
      "error_message": errorMessage ?? "",
      "generate_visible": AppBuild.isNonProduction ? "true" : "false",
      "image_visible": image == nil ? "false" : "true",
      "why_this_visible": projection?.whyThis == nil ? "false" : "true",
      "feedback_visible": projection == nil ? "false" : "true",
    ]
  }

  private func automationFixtureImage() -> NSImage {
    NSImage(size: NSSize(width: 640, height: 400), flipped: false) { bounds in
      NSColor(calibratedRed: 0.06, green: 0.13, blue: 0.22, alpha: 1).setFill()
      bounds.fill()

      let card = NSBezierPath(
        roundedRect: bounds.insetBy(dx: 48, dy: 42),
        xRadius: 28,
        yRadius: 28)
      NSColor(calibratedRed: 0.10, green: 0.24, blue: 0.34, alpha: 1).setFill()
      card.fill()

      let titleAttributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 28, weight: .bold),
        .foregroundColor: NSColor.white,
      ]
      let subtitleAttributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 15, weight: .medium),
        .foregroundColor: NSColor(calibratedRed: 0.58, green: 0.88, blue: 0.88, alpha: 1),
      ]
      let itemAttributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: 19, weight: .semibold),
        .foregroundColor: NSColor.white,
      ]

      "A QUIET THRESHOLD".draw(
        at: NSPoint(x: 86, y: 300),
        withAttributes: titleAttributes)
      "One grounded omen".draw(
        at: NSPoint(x: 88, y: 270),
        withAttributes: subtitleAttributes)

      let items = [
        "Recent context",
        "One open commitment",
        "A next step worth naming",
      ]
      for (index, item) in items.enumerated() {
        let y = CGFloat(210 - (index * 62))
        let markerBounds = NSRect(x: 88, y: y - 2, width: 30, height: 30)
        NSColor(calibratedRed: 0.20, green: 0.78, blue: 0.58, alpha: 1).setFill()
        NSBezierPath(ovalIn: markerBounds).fill()
        "✓".draw(
          at: NSPoint(x: 94, y: y),
          withAttributes: [
            .font: NSFont.systemFont(ofSize: 19, weight: .bold),
            .foregroundColor: NSColor.white,
          ])
        item.draw(
          at: NSPoint(x: 138, y: y + 2),
          withAttributes: itemAttributes)
      }
      return true
    }
  }

  private func clearOwnerState() {
    requestGeneration &+= 1
    feedbackRequestGeneration &+= 1
    projection = nil
    image = nil
    isLoading = false
    isGenerating = false
    isImageLoading = false
    imageLoadFailed = false
    errorMessage = nil
    feedbackRating = nil
    isSubmittingFeedback = false
    feedbackError = nil
    lastRefreshAt = .distantPast
  }
}
