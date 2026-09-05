import OmiTheme
import SwiftUI

/// The chat-quota warning card that sits directly above the composer.
///
/// One quiet line in `ChatErrorCard`'s idiom — tinted wash, tinted hairline,
/// severity glyph, one CTA pill — so the warning costs the composer a single
/// row and never pushes the conversation around. Severity lives in one hue:
/// outline orange at 90%, filled orange at the allowance, and only a
/// hard-capped plan, where sends are actually refused, borrows the error red.
/// `PageGlass.warning` and not a hand-mixed yellow — the palette's "something
/// to do about it, not yet an error" tone.
struct ChatQuotaBannerView: View {
  let banner: ChatQuotaBanner
  let onViewPlan: () -> Void
  let onDismiss: () -> Void

  /// The inline meter's fixed track width. Narrow enough to stay decoration,
  /// wide enough that 90% vs 100% is legible at a glance.
  private let meterWidth: CGFloat = 72

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
    // One line: what happened, the count, the meter inline, and the two
    // actions. The full detail (plan name, reset date, overage copy) stays a
    // glance away on the plan page, where "View plan" lands.
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      Image(systemName: severityGlyph)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(severityColor)
        .accessibilityHidden(true)

      HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.xs) {
        Text(banner.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
        Text(banner.summary)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)
      }
      .layoutPriority(1)

      meter
        .frame(width: meterWidth)

      Spacer(minLength: OmiSpacing.md)

      Button(action: onViewPlan) {
        Text("View plan")
      }
      .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      .accessibilityIdentifier("chat-quota-banner-view-plan")

      Button(action: onDismiss) {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
      .buttonStyle(.plain)
      .help("Dismiss")
      .accessibilityLabel("Dismiss")
      .accessibilityIdentifier("chat-quota-banner-dismiss")
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFill)
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .strokeBorder(severityColor.opacity(0.35), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .accessibilityElement(children: .contain)
    .accessibilityLabel("\(banner.title). \(banner.message)")
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

  /// The allowance meter, inline: a hairline track with the used share filled.
  /// The glanceable fact prose cannot be — how close the end is. Decorative to
  /// accessibility, which the banner label carries in words.
  private var meter: some View {
    Capsule(style: .continuous)
      .fill(Ink.rowFillHover)
      .overlay(alignment: .leading) {
        Capsule(style: .continuous)
          .fill(severityColor)
          // A nonzero reading stays a visible nub; a zero one is empty.
          .frame(width: meterWidth * CGFloat(max(banner.percent > 0 ? 3 : 0, banner.percent)) / 100)
      }
      .frame(height: 4)
      .accessibilityHidden(true)
  }
}
