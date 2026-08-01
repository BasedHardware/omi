import Foundation

enum FloatingBarNotificationPreviewPolicy {
  static func shouldShowInBarPreview(previewsEnabled: Bool, floatingBarEnabled: Bool) -> Bool {
    previewsEnabled && floatingBarEnabled
  }

  static func shouldDeliverSystemBanner(
    previewsEnabled: Bool, floatingBarEnabled: Bool, deliverSystemBanner: Bool
  ) -> Bool {
    deliverSystemBanner
      || !shouldShowInBarPreview(previewsEnabled: previewsEnabled, floatingBarEnabled: floatingBarEnabled)
  }
}
