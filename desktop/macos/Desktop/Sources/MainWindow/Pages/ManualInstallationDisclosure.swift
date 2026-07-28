import OmiTheme
import SwiftUI

struct ManualInstallationDisclosure<Content: View>: View {
  @Binding private var isExpanded: Bool
  private let title: String
  private let fontSize: CGFloat
  private let content: () -> Content

  init(
    isExpanded: Binding<Bool>,
    title: String = "Manual installation",
    fontSize: CGFloat,
    @ViewBuilder content: @escaping () -> Content
  ) {
    _isExpanded = isExpanded
    self.title = title
    self.fontSize = fontSize
    self.content = content
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: { isExpanded.toggle() }) {
        HStack(spacing: OmiSpacing.xxs) {
          Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .frame(width: 10)

          Text(title)
            .scaledFont(size: fontSize, weight: .medium)
        }
        .foregroundColor(OmiColors.textTertiary)
        .padding(.vertical, OmiSpacing.xxs)
        .frame(minHeight: 28, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help(isExpanded ? "Hide \(title.lowercased())" : "Show \(title.lowercased())")
      .accessibilityLabel(title)
      .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")

      if isExpanded {
        content()
      }
    }
  }
}
