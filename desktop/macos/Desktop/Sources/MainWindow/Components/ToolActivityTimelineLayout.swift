import OmiTheme
import SwiftUI

/// Shared geometry for the live tool-activity rail. Different SF Symbols have
/// different optical bearings; every glyph is forced into the same centered
/// square so the connector and the row of icons stay on one axis. The header
/// hugs its label so the disclosure sits beside the tool name instead of the
/// trailing edge of the chat column.
enum ToolActivityTimelineLayout {
  static let iconGlyphSize = OmiType.body
  static let iconColumn: CGFloat = 18
  static let connectorWidth: CGFloat = 1
  static let connectorBottomTrim: CGFloat = 6
  static let disclosureSize = OmiType.micro
  static let labelToDisclosureSpacing: CGFloat = 2
  static let rowIconSpacing = OmiSpacing.xxs
  static var headerHeight: CGFloat { iconColumn }
  static var rowMinHeight: CGFloat { iconColumn }
  static var connectorTopInset: CGFloat { iconColumn - 1 }

  /// Left edge of the 1pt connector, centered on the icon column.
  static var connectorOriginX: CGFloat {
    (iconColumn - connectorWidth) / 2
  }

  static var expandedContentLeadingInset: CGFloat {
    iconColumn + rowIconSpacing
  }

  static func iconGlyphFrame(inColumn column: CGFloat = iconColumn) -> CGRect {
    CGRect(
      x: (column - iconGlyphSize) / 2,
      y: (column - iconGlyphSize) / 2,
      width: iconGlyphSize,
      height: iconGlyphSize
    )
  }

  struct HeaderFrames: Equatable {
    var label: CGRect
    var disclosure: CGRect?
    var width: CGFloat
  }

  /// Intrinsic header frames. The production header is an HStack of these
  /// sizes, not a flexible spacer that fills the chat column.
  static func headerFrames(labelWidth: CGFloat, hasDisclosure: Bool) -> HeaderFrames {
    let label = CGRect(x: 0, y: 0, width: labelWidth, height: headerHeight)
    guard hasDisclosure else {
      return HeaderFrames(label: label, disclosure: nil, width: labelWidth)
    }
    let disclosure = CGRect(
      x: labelWidth + labelToDisclosureSpacing,
      y: (headerHeight - disclosureSize) / 2,
      width: disclosureSize,
      height: disclosureSize
    )
    return HeaderFrames(label: label, disclosure: disclosure, width: disclosure.maxX)
  }

  static func symbol(for name: String) -> String {
    let cleanName = String(name.split(separator: "__").last ?? Substring(name)).lowercased()
    let tokens = Set(cleanName.split { !$0.isLetter && !$0.isNumber }.map(String.init))
    if tokens.contains("search") || cleanName.hasPrefix("grep") || cleanName.hasPrefix("glob") {
      return "magnifyingglass"
    }
    if tokens.contains("read") || tokens.contains("fetch") { return "doc.text" }
    if tokens.contains("write") || tokens.contains("edit") { return "pencil" }
    if tokens.contains("bash") || tokens.contains("shell") || tokens.contains("command") {
      return "terminal"
    }
    if cleanName.contains("agent") { return "person.2" }
    if cleanName.contains("calendar") { return "calendar" }
    if cleanName.contains("mail") || cleanName.contains("message") { return "envelope" }
    if cleanName.contains("permission") { return "lock" }
    if cleanName.contains("screen") || cleanName.contains("capture") { return "rectangle.dashed" }
    return "sparkles"
  }
}

struct ToolCallActivityHeadline<Header: View>: View {
  let name: String
  let status: ToolCallStatus
  let header: Header

  init(
    name: String,
    status: ToolCallStatus,
    @ViewBuilder header: () -> Header
  ) {
    self.name = name
    self.status = status
    self.header = header()
  }

  var body: some View {
    HStack(alignment: .center, spacing: ToolActivityTimelineLayout.rowIconSpacing) {
      ToolCallActivityIcon(name: name, status: status)
        .accessibilityHidden(true)
      header
    }
  }
}

struct ToolCallActivityIcon: View {
  let name: String
  let status: ToolCallStatus

  var body: some View {
    Group {
      switch status {
      case .running:
        ProgressView()
          .controlSize(.mini)
      case .slow:
        ProgressView()
          .controlSize(.mini)
          .tint(PageGlass.warning)
      case .stalled:
        alignedSymbol("exclamationmark.triangle.fill", color: PageGlass.warning)
      case .completed:
        alignedSymbol(ToolActivityTimelineLayout.symbol(for: name), color: Ink.secondary)
      case .failed:
        alignedSymbol("xmark.circle", color: Ink.errorRed)
      }
    }
    .frame(
      width: ToolActivityTimelineLayout.iconColumn,
      height: ToolActivityTimelineLayout.iconColumn,
      alignment: .center
    )
    .background(Ink.surface.opacity(0.94), in: Circle())
  }

  private func alignedSymbol(_ systemName: String, color: Color) -> some View {
    Image(systemName: systemName)
      .resizable()
      .scaledToFit()
      .foregroundColor(color)
      .frame(
        width: ToolActivityTimelineLayout.iconGlyphSize,
        height: ToolActivityTimelineLayout.iconGlyphSize,
        alignment: .center
      )
  }
}

struct ToolCallHeaderLabel: View {
  let title: String
  var summary: String? = nil
  let showsDisclosure: Bool
  var isExpanded = false

  var body: some View {
    HStack(alignment: .center, spacing: ToolActivityTimelineLayout.labelToDisclosureSpacing) {
      Text(title)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: true, vertical: false)

      if showsDisclosure {
        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
          .fixedSize()
          .accessibilityHidden(true)
      }

      if let summary, !summary.isEmpty {
        Text(summary)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary.opacity(0.72))
          .lineLimit(1)
          .truncationMode(.middle)
      }
    }
    .frame(minHeight: ToolActivityTimelineLayout.headerHeight, alignment: .leading)
  }
}
