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

    context.coordinator.loadedGifName = gifName
    if let image = AnimatedGIFView.loadGif(named: gifName) {
      imageView.image = image
    }

    return imageView
  }

  func updateNSView(_ nsView: NSImageView, context: Context) {
    nsView.animates = true
    // A reused representable would otherwise keep showing the previous GIF
    // when only `gifName` changes (identity is not part of the diff).
    guard context.coordinator.loadedGifName != gifName else { return }
    context.coordinator.loadedGifName = gifName
    nsView.image = AnimatedGIFView.loadGif(named: gifName)
  }

  func makeCoordinator() -> Coordinator {
    Coordinator()
  }

  private static func loadGif(named gifName: String) -> NSImage? {
    guard
      let url = Bundle.resourceBundle.url(forResource: gifName, withExtension: "gif")
    else { return nil }
    return NSImage(contentsOf: url)
  }

  final class Coordinator {
    var loadedGifName: String?
  }
}
