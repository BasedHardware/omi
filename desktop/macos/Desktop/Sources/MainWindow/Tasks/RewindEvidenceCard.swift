import OmiTheme
import SwiftUI

/// The small, metadata-only card shown for a task/workstream reference that can be resolved to a
/// frame in this Mac's local Rewind database. A card is intentionally stricter than the backend
/// evidence enum: an opaque or future reference must stay text-only rather than becoming a
/// plausible-looking link to another owner's SQLite row.
struct RewindEvidenceCardModel: Equatable, Identifiable, Sendable {
  let screenshotID: Int64

  var id: String { "rewind-evidence-\(screenshotID)" }
  var title: String { "Screen evidence" }
  var subtitle: String { "Open Rewind · frame \(screenshotID)" }
}

struct RewindEvidenceCardLease: Equatable, Sendable {
  let screenshotID: Int64
  let owner: RewindCaptureOwnerSnapshot
}

enum RewindEvidenceCardAvailability: Equatable, Sendable {
  case checking
  case available
  case unavailable
}

enum RewindEvidenceCardPresentationPolicy {
  static func isOpenable(
    availability: RewindEvidenceCardAvailability,
    hasOpenHandler: Bool
  ) -> Bool {
    availability == .available && hasOpenHandler
  }

  static func subtitle(
    for card: RewindEvidenceCardModel,
    availability: RewindEvidenceCardAvailability
  ) -> String {
    switch availability {
    case .checking: return "Checking local Rewind · frame \(card.screenshotID)"
    case .available: return card.subtitle
    case .unavailable: return "Unavailable locally · frame \(card.screenshotID)"
    }
  }

  static func accessibilityHint(
    availability: RewindEvidenceCardAvailability,
    hasOpenHandler: Bool
  ) -> String {
    guard hasOpenHandler else { return "This evidence is not available to open here" }
    switch availability {
    case .checking: return "Checking whether this frame is still available locally"
    case .available: return "Opens the matching frame in Rewind"
    case .unavailable: return "This frame is unavailable locally, possibly because it was pruned"
    }
  }
}

enum RewindEvidenceCardResolutionPolicy {
  static func availability(
    localRowExists: Bool,
    ownerStillCurrent: Bool
  ) -> RewindEvidenceCardAvailability {
    guard localRowExists, ownerStillCurrent else { return .unavailable }
    return .available
  }

  static func leaseIsCurrent(
    _ lease: RewindEvidenceCardLease,
    screenshotID: Int64,
    currentOwner: RewindCaptureOwnerSnapshot?
  ) -> Bool {
    lease.screenshotID == screenshotID
      && currentOwner == lease.owner
      && lease.owner.isCurrent()
  }
}

enum RewindEvidenceCardPolicy {
  /// Only this explicit version identifies an exact local Rewind frame. The older `capture.v2`
  /// contract may carry a staged-task id when no screenshot row exists, so it must stay text-only.
  static let supportedVersion = "rewind_frame.v1"

  /// Return a card only when this exact reference identifies a frame owned by this installation.
  /// The caller supplies the device identity so this policy remains deterministic in tests and
  /// cannot silently accept a server or another Mac's row id.
  static func card(
    for evidence: OmiAPI.EvidenceRef,
    currentDeviceID: String
  ) -> RewindEvidenceCardModel? {
    guard evidence.kind == .local_screen,
      evidence.scope == .device_local,
      let expectedDeviceID = normalized(currentDeviceID),
      let evidenceDeviceID = normalized(evidence.deviceId),
      evidenceDeviceID == expectedDeviceID,
      evidence.version == supportedVersion,
      let screenshotID = parseScreenshotID(evidence.id)
    else { return nil }

    return RewindEvidenceCardModel(screenshotID: screenshotID)
  }

  /// Local evidence IDs are producer-shaped, not arbitrary database queries. Requiring the
  /// canonical `screen-<positive decimal>` form avoids accepting a conversation, an external URL,
  /// a future opaque identity, or a row id from another namespace.
  static func parseScreenshotID(_ evidenceID: String) -> Int64? {
    let normalizedID = evidenceID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard normalizedID.hasPrefix("screen-") else { return nil }
    let suffix = String(normalizedID.dropFirst("screen-".count))
    guard !suffix.isEmpty, suffix.allSatisfy({ $0.isNumber }), let id = Int64(suffix), id > 0,
      String(id) == suffix
    else { return nil }
    return id
  }

  static func openHandler(
    for screenshotID: Int64,
    onOpen: ((Int64) -> Void)?
  ) -> ((RewindEvidenceCardLease) -> Void)? {
    guard let onOpen else { return nil }
    return { lease in
      guard lease.screenshotID == screenshotID else { return }
      onOpen(screenshotID)
    }
  }

  private static func normalized(_ value: String?) -> String? {
    guard let value else { return nil }
    let result = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return result.isEmpty ? nil : result
  }
}

/// A metadata-only Rewind source card. Pixels remain in the local Rewind store and are loaded by
/// Rewind after the navigation handoff; task/thread rendering never fetches or embeds an image.
struct RewindEvidenceCardView: View {
  let card: RewindEvidenceCardModel
  let onOpen: ((RewindEvidenceCardLease) -> Void)?
  let localScreenshotExists: @Sendable (Int64) async -> Bool

  @State private var isHovering = false
  @State private var availability: RewindEvidenceCardAvailability = .checking
  @State private var presentationLease: RewindEvidenceCardLease?
  @State private var availabilityEpoch = 0

  init(
    card: RewindEvidenceCardModel,
    onOpen: ((RewindEvidenceCardLease) -> Void)?,
    localScreenshotExists: @escaping @Sendable (Int64) async -> Bool = { screenshotID in
      (try? RewindDatabase.shared.getScreenshot(id: screenshotID)) != nil
    }
  ) {
    self.card = card
    self.onOpen = onOpen
    self.localScreenshotExists = localScreenshotExists
  }

  var body: some View {
    Button {
      validateAndOpen()
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "clock.arrow.circlepath")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .frame(width: 20)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(card.title)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.primary)
            .lineLimit(1)
          Text(subtitle)
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
        }

        Spacer(minLength: OmiSpacing.xs)

        Image(systemName: trailingIcon)
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundColor(Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .glassCard(cornerRadius: PageGlass.chipRadius, emphasized: isHovering && onOpen != nil)
    }
    .buttonStyle(.plain)
    .disabled(!isOpenable)
    .onHover { isHovering = $0 }
    .accessibilityIdentifier("rewind-evidence-card-\(card.screenshotID)")
    .accessibilityLabel(card.title)
    .accessibilityValue(subtitle)
    .accessibilityHint(accessibilityHint)
    .task(id: "\(card.screenshotID)-\(availabilityEpoch)") {
      await refreshAvailability()
    }
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      presentationLease = nil
      availability = .checking
      availabilityEpoch &+= 1
    }
  }

  private var isOpenable: Bool {
    RewindEvidenceCardPresentationPolicy.isOpenable(
      availability: availability,
      hasOpenHandler: onOpen != nil
    )
  }

  private var subtitle: String {
    RewindEvidenceCardPresentationPolicy.subtitle(for: card, availability: availability)
  }

  private var trailingIcon: String {
    guard onOpen != nil else { return "lock" }
    switch availability {
    case .checking: return "hourglass"
    case .available: return "chevron.right"
    case .unavailable: return "exclamationmark.triangle"
    }
  }

  private var accessibilityHint: String {
    RewindEvidenceCardPresentationPolicy.accessibilityHint(
      availability: availability,
      hasOpenHandler: onOpen != nil
    )
  }

  @MainActor
  private func refreshAvailability() async {
    let attempts = 8
    for attempt in 0..<attempts {
      guard !Task.isCancelled else { return }
      guard let ownerAtStart = RewindCaptureOwnerSnapshot.capture() else {
        if await retryOwnerResolution(after: attempt, attempts: attempts) { continue }
        presentationLease = nil
        availability = .unavailable
        return
      }

      let localRowExists = await localScreenshotExists(card.screenshotID)
      guard !Task.isCancelled else { return }
      let ownerIsStable = RewindEvidenceCardResolutionPolicy.leaseIsCurrent(
        RewindEvidenceCardLease(screenshotID: card.screenshotID, owner: ownerAtStart),
        screenshotID: card.screenshotID,
        currentOwner: RewindCaptureOwnerSnapshot.capture()
      )
      guard ownerIsStable else {
        if await retryOwnerResolution(after: attempt, attempts: attempts) { continue }
        presentationLease = nil
        availability = .unavailable
        return
      }

      presentationLease = RewindEvidenceCardLease(
        screenshotID: card.screenshotID,
        owner: ownerAtStart
      )
      availability = RewindEvidenceCardResolutionPolicy.availability(
        localRowExists: localRowExists,
        ownerStillCurrent: true
      )
      if availability != .available { presentationLease = nil }
      return
    }
  }

  @MainActor
  private func validateAndOpen() {
    guard isOpenable, let onOpen, let lease = presentationLease else { return }
    guard
      RewindEvidenceCardResolutionPolicy.leaseIsCurrent(
        lease,
        screenshotID: card.screenshotID,
        currentOwner: RewindCaptureOwnerSnapshot.capture()
      )
    else {
      presentationLease = nil
      availability = .unavailable
      return
    }
    Task { @MainActor in
      let localRowExists = await localScreenshotExists(card.screenshotID)
      guard !Task.isCancelled else { return }
      guard
        RewindEvidenceCardResolutionPolicy.leaseIsCurrent(
          lease,
          screenshotID: card.screenshotID,
          currentOwner: RewindCaptureOwnerSnapshot.capture()
        )
      else {
        presentationLease = nil
        availability = .unavailable
        return
      }
      let resolvedAvailability = RewindEvidenceCardResolutionPolicy.availability(
        localRowExists: localRowExists,
        ownerStillCurrent: true
      )
      guard resolvedAvailability == .available else {
        presentationLease = nil
        availability = .unavailable
        return
      }
      onOpen(lease)
    }
  }

  @MainActor
  private func retryOwnerResolution(after attempt: Int, attempts: Int) async -> Bool {
    guard attempt + 1 < attempts else { return false }
    try? await Task.sleep(for: .milliseconds(25))
    return !Task.isCancelled
  }
}
