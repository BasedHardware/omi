import OmiTheme
import SwiftUI

/// The chat-quota warning strip that sits directly above the composer.
///
/// Same shape as the task panel's inline error banner (`TaskChatPanel`):
/// warning glyph, one line of prose, dismiss. `PageGlass.warning` and not a
/// hand-mixed yellow — this is the palette's "something to do about it, not yet
/// an error" tone, which is exactly what being near a cap is.
struct ChatQuotaBannerView: View {
  let banner: ChatQuotaBanner
  let onViewPlan: () -> Void
  let onDismiss: () -> Void

  /// Mounted directly above a composer. Both desktop shells show the same
  /// warning on the same surface (INV-NAV-1), so the wiring lives here once
  /// rather than being restated at each mount point.
  struct Slot: View {
    @ObservedObject private var usageLimiter = FloatingBarUsageLimiter.shared
    @ObservedObject private var dismissals = ChatQuotaBannerDismissals.shared

    var body: some View {
      if let banner = ChatQuotaBanner.current(
        quota: usageLimiter.serverQuota,
        optimisticDelta: usageLimiter.optimisticDelta,
        dismissed: dismissals.dismissed)
      {
        ChatQuotaBannerView(
          banner: banner,
          onViewPlan: {
            NotificationCenter.default.post(name: .navigateToPlanSettings, object: nil)
          },
          onDismiss: {
            dismissals.dismiss(threshold: banner.threshold, cycleID: banner.cycleID)
          }
        )
      }
    }
  }

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .foregroundColor(PageGlass.warning)
        .scaledFont(size: OmiType.body)

      // Title and detail read as one sentence, and the whole thing must stay
      // readable: a warning the user cannot finish reading is not a warning.
      VStack(alignment: .leading, spacing: 2) {
        Text(banner.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(banner.message)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .multilineTextAlignment(.leading)
      .frame(maxWidth: .infinity, alignment: .leading)

      Button(action: onViewPlan) {
        Text("View plan")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("chat-quota-banner-view-plan")

      Button(action: onDismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("chat-quota-banner-dismiss")
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .accessibilityIdentifier("chat-quota-banner")
  }
}
