import SwiftUI

struct MessagingProviderIcon: View {
  let provider: any MessagingProvider
  var size: CGFloat = 16

  var body: some View {
    if let brand = provider.connectorBrand {
      ConnectorBrandIcon(brand: brand, size: size, cornerRadius: size * 0.24)
    } else {
      Image(systemName: provider.iconSystemName)
        .font(.system(size: size, weight: .semibold))
    }
  }
}
