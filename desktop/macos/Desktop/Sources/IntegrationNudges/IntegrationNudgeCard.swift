import OmiTheme
import SwiftUI

/// The floating-bar card that offers to connect an integration the user has
/// open but has not set up.
///
/// "You just opened Gmail — Omi can read it", plus the three answers that
/// exist: yes, later, never. The brand mark and the data-scope line are not
/// decoration: the user is being asked for access to a tool they are looking
/// at, and a card that names the value without naming the cost is a worse
/// version of the same interruption.
struct IntegrationNudgeCard: View {
  let notification: FloatingBarNotification
  let entry: IntegrationNudgeCatalogEntry
  let triggerID: String

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      ConnectorBrandIcon(brand: entry.brand, size: 34, cornerRadius: 9)

      VStack(alignment: .leading, spacing: 3) {
        Text(notification.title)
          .scaledFont(size: 13, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(1)
          .minimumScaleFactor(0.85)

        // Three lines, not two: the longest pitches are a full sentence, and
        // cutting one mid-clause reads as a bug rather than as brevity.
        Text(entry.pitch)
          .scaledFont(size: 11)
          .foregroundColor(.white.opacity(0.72))
          .lineLimit(3)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)

        Text(entry.dataScope)
          .scaledFont(size: 10)
          .foregroundColor(.white.opacity(0.42))
          .lineLimit(2)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)

        actions
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private var actions: some View {
    HStack(spacing: 7) {
      Button {
        FloatingControlBarManager.shared.openNotificationAsChat(notification)
      } label: {
        Text("Connect")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.black)
          .padding(.horizontal, 11).padding(.vertical, 4)
          .background(Color.white)
          .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
      }
      .buttonStyle(.plain)

      Button {
        IntegrationNudgeCoordinator.shared.snoozePresentedNudge(
          telemetryID: entry.telemetryID, triggerID: triggerID)
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Text("Not now").scaledFont(size: 12).foregroundColor(.white.opacity(0.55))
      }
      .buttonStyle(.plain)

      Button {
        IntegrationNudgeCoordinator.shared.dismissPresentedNudgeForever(
          telemetryID: entry.telemetryID, triggerID: triggerID)
        FloatingControlBarManager.shared.dismissCurrentNotification()
      } label: {
        Text("Never").scaledFont(size: 12).foregroundColor(.white.opacity(0.35))
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Never suggest \(entry.displayName)")
    }
    .padding(.top, 5)
  }
}
