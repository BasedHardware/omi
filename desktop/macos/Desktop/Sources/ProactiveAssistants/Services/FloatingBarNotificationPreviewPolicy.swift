import Foundation

enum FloatingBarNotificationPreviewPolicy {
  /// In-bar card presentation is independent of the persisted Ask Omi enable
  /// toggle. That toggle only controls whether the bar stays on screen; the
  /// Notifications master toggle (and frequency gate) decide whether a
  /// notification is owed at all.
  ///
  /// - Bar enabled + previews on → show the card on the persistent bar.
  /// - Bar enabled + previews muted → skip the card so #6765 can fall back to a
  ///   system banner.
  /// - Bar disabled → still show the card via the existing temp-show path
  ///   (present, then re-hide). Previews-muted does not silence this path:
  ///   only the notification toggle decides, and a muted-preview + disabled-bar
  ///   combination still owes a visible surface.
  /// - Bar disabled + an explicit `deliverSystemBanner` caller → skip the card so the
  ///   banner it asked for is not swallowed. The temp-show path is a card on a bar the
  ///   user turned off: it auto-dismisses after seconds and leaves nothing behind, which
  ///   is not a surface for a functional notice that must reach a user away from the app.
  ///   The screen-recording repair notice is delivered once per broken-capture episode
  ///   (`screenCaptureResetShownKey`, cleared only on recovery), so a missed card is the
  ///   whole notice. With the bar enabled the card stays authoritative and the
  ///   no-duplicate-surface rule is unchanged.
  static func shouldShowInBarPreview(
    previewsEnabled: Bool, floatingBarEnabled: Bool, deliverSystemBanner: Bool
  ) -> Bool {
    if deliverSystemBanner && !floatingBarEnabled { return false }
    return previewsEnabled || !floatingBarEnabled
  }

  /// The system-banner fallback only fires when the user explicitly muted in-bar
  /// previews (`previewsEnabled == false`) while the Floating Bar is otherwise on —
  /// that's the one case where the user asked to be notified some other way.
  ///
  /// Context-director delivery must use this same rule: muting the in-bar preview
  /// cannot silently burn ledger quota with no visible surface.
  ///
  /// Disabling the Floating Bar itself does not force a banner. That path
  /// temp-shows the in-bar card and re-hides afterwards, which keeps conversation
  /// context instead of a contentless system banner.
  static func shouldDeliverSystemBanner(
    previewsEnabled: Bool, floatingBarEnabled: Bool, deliverSystemBanner: Bool
  ) -> Bool {
    deliverSystemBanner || (!previewsEnabled && floatingBarEnabled)
  }

  static func shouldDeliverSystemBannerAfterFloatingBar(
    previewsEnabled: Bool,
    floatingBarEnabled: Bool,
    deliverSystemBanner: Bool,
    floatingBarAccepted: Bool
  ) -> Bool {
    !floatingBarAccepted
      && shouldDeliverSystemBanner(
        previewsEnabled: previewsEnabled,
        floatingBarEnabled: floatingBarEnabled,
        deliverSystemBanner: deliverSystemBanner)
  }
}
