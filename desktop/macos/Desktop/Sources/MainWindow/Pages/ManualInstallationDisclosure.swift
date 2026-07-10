import SwiftUI
import OmiTheme

struct ManualInstallationDisclosure<Content: View>: View {
  @Binding private var isExpanded: Bool
  private let fontSize: CGFloat
  private let content: () -> Content

  init(
    isExpanded: Binding<Bool>,
    fontSize: CGFloat,
    @ViewBuilder content: @escaping () -> Content
  ) {
    _isExpanded = isExpanded
    self.fontSize = fontSize
    self.content = content
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: { isExpanded.toggle() }) {
        HStack(spacing: 4) {
          Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
            .scaledFont(size: 9, weight: .semibold)
            .frame(width: 10)

          Text("Manual installation")
            .scaledFont(size: fontSize, weight: .medium)
        }
        .foregroundColor(OmiColors.textTertiary)
        .padding(.vertical, 4)
        .frame(minHeight: 28, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help(isExpanded ? "Hide manual installation" : "Show manual installation")
      .accessibilityLabel("Manual installation")
      .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")

      if isExpanded {
        content()
      }
    }
  }
}
