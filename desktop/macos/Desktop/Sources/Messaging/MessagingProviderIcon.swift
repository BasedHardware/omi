import AppKit
import SwiftUI

struct MessagingProviderIcon: View {
  let provider: any MessagingProvider
  var size: CGFloat = 16

  var body: some View {
    if provider.id == "whatsapp" {
      ConnectorBrandIcon(brand: .whatsapp, size: size, cornerRadius: size * 0.24)
    } else if let image = bundledImage {
      Image(nsImage: image)
        .resizable()
        .interpolation(.high)
        .aspectRatio(contentMode: .fit)
        .frame(width: size, height: size)
    } else {
      Image(systemName: provider.iconSystemName)
        .font(.system(size: size, weight: .semibold))
    }
  }

  private var bundledImage: NSImage? {
    guard let resourceName = provider.brandResourceName,
      let url = Bundle.resourceBundle.url(forResource: resourceName, withExtension: "png"),
      let image = NSImage(contentsOf: url)
    else {
      return nil
    }
    image.isTemplate = false
    return image
  }
}
