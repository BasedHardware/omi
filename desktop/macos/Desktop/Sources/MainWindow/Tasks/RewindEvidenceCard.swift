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

enum RewindEvidenceCardAvailability: Equatable, Sendable {
  case checking
  case available
  case unavailable
}

enum RewindEvidenceCardResolutionPolicy {
  static func availability(
    localRowExists: Bool,
    ownerStillCurrent: Bool
  ) -> RewindEvidenceCardAvailability {
    guard localRowExists, ownerStillCurrent else { return .unavailable }
    return .available
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
  ) -> (() -> Void)? {
    guard let onOpen else { return nil }
    return { onOpen(screenshotID) }
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
  let onOpen: (() -> Void)?
  let localScreenshotExists: @Sendable (Int64) async -> Bool

  @State private var isHovering = false
  @State private var availability: RewindEvidenceCardAvailability = .checking

  init(
    card: RewindEvidenceCardModel,
    onOpen: (() -> Void)?,
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
    .task(id: card.screenshotID) {
      await refreshAvailability()
    }
  }

  private var isOpenable: Bool {
    availability == .available && onOpen != nil
  }

  private var subtitle: String {
    switch availability {
    case .checking: return "Checking local Rewind · frame \(card.screenshotID)"
    case .available: return card.subtitle
    case .unavailable: return "Unavailable locally · frame \(card.screenshotID)"
    }
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
    guard onOpen != nil else { return "This evidence is not available to open here" }
    switch availability {
    case .checking: return "Checking whether this frame is still available locally"
    case .available: return "Opens the matching frame in Rewind"
    case .unavailable: return "This frame is unavailable locally, possibly because it was pruned"
    }
  }

  @MainActor
  private func refreshAvailability() async {
    guard let ownerAtStart = RewindCaptureOwnerSnapshot.capture() else {
      availability = .unavailable
      return
    }
    let localRowExists = await localScreenshotExists(card.screenshotID)
    guard !Task.isCancelled else { return }
    availability = RewindEvidenceCardResolutionPolicy.availability(
      localRowExists: localRowExists,
      ownerStillCurrent: ownerAtStart.isCurrent()
    )
  }

  @MainActor
  private func validateAndOpen() {
    guard isOpenable, let onOpen else { return }
    Task { @MainActor in
      guard let ownerAtStart = RewindCaptureOwnerSnapshot.capture() else {
        availability = .unavailable
        return
      }
      let localRowExists = await localScreenshotExists(card.screenshotID)
      guard !Task.isCancelled else { return }
      let resolvedAvailability = RewindEvidenceCardResolutionPolicy.availability(
        localRowExists: localRowExists,
        ownerStillCurrent: ownerAtStart.isCurrent()
      )
      guard resolvedAvailability == .available else {
        availability = .unavailable
        return
      }
      onOpen()
    }
  }
}
