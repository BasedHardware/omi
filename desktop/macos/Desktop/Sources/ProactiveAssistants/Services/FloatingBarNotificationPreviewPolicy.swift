import Foundation

enum FloatingBarNotificationPreviewPolicy {
  static func shouldShowInBarPreview(previewsEnabled: Bool, floatingBarEnabled: Bool) -> Bool {
    previewsEnabled && floatingBarEnabled
  }

  /// The system-banner fallback only fires when the user explicitly muted in-bar
  /// previews (`previewsEnabled == false`) while the Floating Bar is otherwise on —
  /// that's the one case where the user asked to be notified some other way.
  ///
  /// It deliberately does NOT fire just because the Floating Bar itself is
  /// disabled/hidden: `NotificationService` documents that a bare system banner
  /// with no conversation context was previously reported as confusing, which is
  /// why floating-bar-only notifications stay floating-bar-only (i.e. silent)
  /// when the bar is off, matching pre-existing behavior.
  static func shouldDeliverSystemBanner(
    previewsEnabled: Bool, floatingBarEnabled: Bool, deliverSystemBanner: Bool
  ) -> Bool {
    deliverSystemBanner || (!previewsEnabled && floatingBarEnabled)
  }
}
