import OmiTheme
import SwiftUI

/// Shared geometry for expandable timeline cards. Optional link-out actions
/// always retain their slot so status, text, and disclosure anchors never move
/// as agent availability changes.
struct StableChatCardHeader<Identity: View, Content: View>: View {
  let isExpanded: Bool
  let showsDisclosure: Bool
  let horizontalPadding: CGFloat
  let verticalPadding: CGFloat
  let minimumHeight: CGFloat?
  let onToggle: (() -> Void)?
  let onOpen: (() -> Void)?
  let identity: Identity
  let content: Content

  init(
    isExpanded: Bool = false,
    showsDisclosure: Bool,
    horizontalPadding: CGFloat = OmiSpacing.md,
    verticalPadding: CGFloat = OmiSpacing.sm,
    minimumHeight: CGFloat? = nil,
    onToggle: (() -> Void)? = nil,
    onOpen: (() -> Void)? = nil,
    @ViewBuilder identity: @escaping () -> Identity,
    @ViewBuilder content: @escaping () -> Content
  ) {
    self.isExpanded = isExpanded
    self.showsDisclosure = showsDisclosure
    self.horizontalPadding = horizontalPadding
    self.verticalPadding = verticalPadding
    self.minimumHeight = minimumHeight
    self.onToggle = onToggle
    self.onOpen = onOpen
    self.identity = identity()
    self.content = content()
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.xxs) {
      Button(action: { onToggle?() }) {
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          identity
            .frame(width: 18, height: 18, alignment: .center)
          content
            .frame(maxWidth: .infinity, alignment: .leading)
          Group {
            if showsDisclosure {
              Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(Ink.secondary)
            } else {
              Color.clear
            }
          }
          .frame(width: 18, height: 18, alignment: .center)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .allowsHitTesting(onToggle != nil)

      Group {
        if let onOpen {
          Button(action: onOpen) {
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
              .frame(maxWidth: .infinity, maxHeight: .infinity)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .help("Open agent")
        } else {
          Color.clear
        }
      }
      .frame(width: 28, height: 28)
    }
    .padding(.horizontal, horizontalPadding)
    .padding(.vertical, verticalPadding)
    .frame(minHeight: minimumHeight)
    .textSelection(.disabled)
  }
}
