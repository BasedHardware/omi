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

  @State private var isHovering = false

  var body: some View {
    Button {
      onOpen?()
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
          Text(card.subtitle)
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
        }

        Spacer(minLength: OmiSpacing.xs)

        Image(systemName: onOpen == nil ? "lock" : "chevron.right")
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundColor(Ink.secondary)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .glassCard(cornerRadius: PageGlass.chipRadius, emphasized: isHovering && onOpen != nil)
    }
    .buttonStyle(.plain)
    .disabled(onOpen == nil)
    .onHover { isHovering = $0 }
    .accessibilityIdentifier("rewind-evidence-card-\(card.screenshotID)")
    .accessibilityLabel(card.title)
    .accessibilityHint(
      onOpen == nil ? "This evidence is not available to open here" : "Opens the matching frame in Rewind")
  }
}
