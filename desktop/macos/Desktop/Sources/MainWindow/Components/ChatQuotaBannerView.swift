import OmiTheme
import SwiftUI

/// The chat-quota warning card that sits directly above the composer.
///
/// A sibling of `ChatErrorCard`'s idiom — tinted wash, tinted hairline, an
/// icon badge, one CTA pill — tuned down from an error to a warning: the
/// severity lives in one hue and the meter, not in a raised voice. At 90% the
/// glyph is an outlined triangle; at the allowance it fills, and only on a
/// hard-capped plan, where sends are actually refused, does it borrow the
/// error red. `PageGlass.warning` and not a hand-mixed yellow — this is the
/// palette's "something to do about it, not yet an error" tone.
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

    private var banner: ChatQuotaBanner? {
      ChatQuotaBanner.current(
        quota: usageLimiter.serverQuota,
        optimisticDelta: usageLimiter.optimisticDelta,
        dismissed: dismissals.dismissed)
    }

    var body: some View {
      content
        .onAppear { ChatQuotaBannerPresentation.shared.record(banner) }
        .onChange(of: banner) { _, shown in
          ChatQuotaBannerPresentation.shared.record(shown)
        }
    }

    @ViewBuilder
    private var content: some View {
      if let banner {
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
    HStack(alignment: .center, spacing: OmiSpacing.md) {
      Image(systemName: severityGlyph)
        .scaledFont(size: OmiType.subheading)
        .foregroundColor(severityColor)
        .frame(width: 30, height: 30)
        .background(Circle().fill(severityColor.opacity(0.14)))
        .accessibilityHidden(true)

      // Title, detail and meter read top to bottom as one object: what
      // happened, the numbers, and how far along it is. The text column must
      // stay readable — a warning the user cannot finish reading is not a
      // warning.
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text(banner.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(banner.message)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        meter
      }
      .multilineTextAlignment(.leading)
      .frame(maxWidth: .infinity, alignment: .leading)

      Button(action: onViewPlan) {
        Text("View plan")
      }
      .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      .accessibilityIdentifier("chat-quota-banner-view-plan")

      Button(action: onDismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .frame(width: 22, height: 22)
          .background(Circle().fill(Ink.rowFill))
      }
      .buttonStyle(.plain)
      .help("Dismiss")
      .accessibilityLabel("Dismiss")
      .accessibilityIdentifier("chat-quota-banner-dismiss")
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .background(Ink.rowFill)
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .strokeBorder(severityColor.opacity(0.35), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .accessibilityIdentifier("chat-quota-banner")
  }

  /// A hard-capped plan at its allowance is stopped, not just warned — the
  /// server refuses its sends — so that state alone speaks in the error voice.
  /// Everything else (the 90% approach, an overage plan being billed) warns.
  private var severityColor: Color {
    banner.threshold >= 100 && !banner.isBillingOverage ? Ink.errorRed : PageGlass.warning
  }

  /// One glyph shape throughout, escalated by fill: the outline says "getting
  /// close", the filled triangle says "there".
  private var severityGlyph: String {
    banner.threshold >= 100 ? "exclamationmark.triangle.fill" : "exclamationmark.triangle"
  }

  /// The allowance meter: a hairline track with the used share filled. The
  /// glanceable fact prose cannot be — how close the end is. Decorative to
  /// accessibility, which the message already covers in words.
  private var meter: some View {
    GeometryReader { space in
      ZStack(alignment: .leading) {
        Capsule(style: .continuous).fill(Ink.rowFillHover)
        Capsule(style: .continuous)
          .fill(severityColor)
          .frame(width: fillWidth(in: space.size.width))
      }
    }
    .frame(height: 4)
    .accessibilityHidden(true)
  }

  private func fillWidth(in trackWidth: CGFloat) -> CGFloat {
    guard trackWidth > 0 else { return 0 }
    // A nonzero reading stays a visible nub; a zero one is genuinely empty.
    let fraction = max(banner.percent > 0 ? 0.02 : 0, Double(banner.percent) / 100)
    return trackWidth * CGFloat(fraction)
  }
}
