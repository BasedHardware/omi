import AppKit
import SwiftUI

/// An animating GIF from the resource bundle (the permissions walkthrough). Lived inside the retired
/// onboarding wizard's file; the Permissions settings page is its only remaining user.
struct AnimatedGIFView: NSViewRepresentable {
  let gifName: String

  func makeNSView(context: Context) -> NSImageView {
    let imageView = NSImageView()
    imageView.imageScaling = .scaleProportionallyDown
    imageView.animates = true
    imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    imageView.setContentCompressionResistancePriority(.defaultLow, for: .vertical)

    if let url = Bundle.resourceBundle.url(forResource: gifName, withExtension: "gif"),
      let image = NSImage(contentsOf: url)
    {
      imageView.image = image
    }

    return imageView
  }

  func updateNSView(_ nsView: NSImageView, context: Context) {
    nsView.animates = true
  }
}
