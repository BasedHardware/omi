import AppKit
import SwiftUI

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
