import AppKit
import SwiftUI

enum ChatResourceOrigin: Equatable {
  case userAttachment
  case generatedArtifact
}

/// Surface-neutral resource shown in chat. User attachments and agent artifacts
/// keep different lifecycles upstream, but render through this shared shape.
struct ChatResource: Identifiable, Equatable {
  enum State: Equatable {
    case uploading
    case ready
    case failed(String)
    case retained
    case opened
    case dismissed
  }

  let id: String
  let origin: ChatResourceOrigin
  let title: String
  let subtitle: String?
  let mimeType: String?
  let thumbnailURL: String?
  let imageData: Data?
  let uri: String?
  let artifactId: String?
  let omiSessionId: String?
  let runId: String?
  let state: State

  var isImage: Bool {
    if let mimeType {
      return mimeType.hasPrefix("image/")
    }
    return false
  }

  var fileURL: URL? {
    guard let uri, let url = URL(string: uri), url.isFileURL else { return nil }
    return url
  }

  var canOpen: Bool {
    fileURL != nil
  }

  var canRevealInFinder: Bool {
    fileURL != nil
  }

  static func attachment(_ attachment: ChatAttachment) -> ChatResource {
    let state: State
    switch attachment.state {
    case .uploading:
      state = .uploading
    case .uploaded, .localOnly:
      state = .ready
    case .failed(let message):
      state = attachment.localFileURL == nil ? .failed(message) : .ready
    }
    return ChatResource(
      id: "attachment:\(attachment.serverId ?? attachment.id)",
      origin: .userAttachment,
      title: attachment.fileName,
      subtitle: attachment.mimeType,
      mimeType: attachment.mimeType,
      thumbnailURL: attachment.thumbnailURL,
      imageData: attachment.data,
      uri: attachment.localFileURL?.absoluteString,
      artifactId: nil,
      omiSessionId: nil,
      runId: nil,
      state: state
    )
  }

  static func artifact(_ artifact: AgentArtifactProjection) -> ChatResource {
    ChatResource(
      id: "artifact:\(artifact.artifactId)",
      origin: .generatedArtifact,
      title: artifact.title,
      subtitle: artifact.subtitle,
      mimeType: artifact.mimeType,
      thumbnailURL: nil,
      imageData: nil,
      uri: artifact.uri,
      artifactId: artifact.artifactId,
      omiSessionId: artifact.omiSessionId,
      runId: artifact.runId,
      state: State(artifactLifecycleState: artifact.lifecycleState)
    )
  }
}

extension ChatResource.State {
  init(artifactLifecycleState: String) {
    switch artifactLifecycleState {
    case "opened":
      self = .opened
    case "dismissed":
      self = .dismissed
    case "retained":
      self = .retained
    default:
      self = .ready
    }
  }
}

private extension AgentArtifactProjection {
  var subtitle: String? {
    var parts: [String] = []
    if let mimeType, !mimeType.isEmpty {
      parts.append(mimeType)
    } else if !kind.isEmpty {
      parts.append(kind)
    }
    if let sizeBytes {
      parts.append(ByteCountFormatter.string(fromByteCount: Int64(sizeBytes), countStyle: .file))
    }
    return parts.isEmpty ? nil : parts.joined(separator: " • ")
  }
}

struct ChatResourceStrip: View {
  enum Density {
    case full
    case compact
  }

  let resources: [ChatResource]
  var density: Density = .full
  var alignment: HorizontalAlignment = .leading
  var onOpen: ((ChatResource) -> Void)? = nil
  var onReveal: ((ChatResource) -> Void)? = nil

  var body: some View {
    if !resources.isEmpty {
      // Always stack vertically: a single full-width column keeps file names
      // and metadata readable. Side-by-side cards squeezed titles down to
      // "d...ml" / "te...KB", which looked broken with 2+ artifacts.
      VStack(alignment: alignment, spacing: 6) {
        ForEach(resources) { resource in
          ChatResourceCard(
            resource: resource,
            density: density,
            onOpen: onOpen ?? ChatResourceActions.open,
            onReveal: onReveal ?? ChatResourceActions.revealInFinder
          )
        }
      }
      .frame(maxWidth: maxWidth, alignment: frameAlignment)
    }
  }

  private var maxWidth: CGFloat {
    density == .compact ? 320 : 360
  }

  private var frameAlignment: Alignment {
    alignment == .trailing ? .trailing : .leading
  }
}

private struct ChatResourceCard: View {
  let resource: ChatResource
  let density: ChatResourceStrip.Density
  let onOpen: (ChatResource) -> Void
  let onReveal: (ChatResource) -> Void

  @State private var isHovering = false
  @State private var didCopyPath = false

  private var isCompact: Bool { density == .compact }
  private var cornerRadius: CGFloat { isCompact ? 12 : 14 }

  var body: some View {
    Group {
      if resource.isImage && density == .full {
        imageTile
      } else {
        documentTile
      }
    }
    .clipShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        .strokeBorder(borderColor, lineWidth: 1)
    )
    .contentShape(RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
    .onTapGesture { if resource.canOpen { onOpen(resource) } }
    .onHover { hovering in
      isHovering = hovering
      if resource.canOpen {
        if hovering { NSCursor.pointingHand.set() } else { NSCursor.arrow.set() }
      }
    }
    .contextMenu { actionMenu }
    .help(resource.canOpen ? "Open \(resource.title)" : resource.title)
  }

  // MARK: Document tile

  private var documentTile: some View {
    HStack(spacing: 10) {
      iconBadge

      VStack(alignment: .leading, spacing: 1) {
        Text(resource.title)
          .scaledFont(size: isCompact ? 12 : 13, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
          .truncationMode(.middle)
        if let subtitle = resource.subtitle, !subtitle.isEmpty {
          Text(subtitle)
            .scaledFont(size: isCompact ? 10 : 11)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.middle)
        }
      }

      Spacer(minLength: 6)

      trailingAccessory
    }
    .padding(.horizontal, isCompact ? 8 : 10)
    .padding(.vertical, isCompact ? 8 : 9)
    .background(fillColor)
  }

  private var iconBadge: some View {
    ZStack {
      RoundedRectangle(cornerRadius: isCompact ? 8 : 9, style: .continuous)
        .fill(iconBadgeFill)
      Image(systemName: iconName)
        .scaledFont(size: isCompact ? 14 : 16, weight: .medium)
        .foregroundColor(iconTint)
    }
    .frame(width: isCompact ? 30 : 36, height: isCompact ? 30 : 36)
  }

  /// Generated artifacts get a slightly brighter, warmer badge so "the agent
  /// made this" reads differently from a file the user attached, without any
  /// off-brand accent color.
  private var iconBadgeFill: Color {
    let boost: Double = resource.origin == .generatedArtifact ? 0.05 : 0
    return Color.white.opacity((isHovering ? 0.14 : 0.08) + boost)
  }

  private var iconTint: Color {
    resource.origin == .generatedArtifact ? OmiColors.textPrimary : OmiColors.textSecondary
  }

  @ViewBuilder
  private var trailingAccessory: some View {
    switch resource.state {
    case .uploading:
      ProgressView().controlSize(.small)
    case .failed:
      Image(systemName: "exclamationmark.triangle.fill")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.warning)
    default:
      if resource.canOpen {
        HStack(spacing: 2) {
          copyPathButton
          openIndicator
        }
      }
    }
  }

  /// Always-visible, low-key affordance signalling the whole card opens the
  /// file on click; brightens on hover. Keeps click-to-open discoverable
  /// beyond the cursor change.
  private var openIndicator: some View {
    Image(systemName: "arrow.up.right")
      .scaledFont(size: isCompact ? 10 : 11, weight: .semibold)
      .foregroundColor(isHovering ? OmiColors.textSecondary : OmiColors.textQuaternary)
      .frame(width: 18, height: 26)
      .animation(.easeInOut(duration: 0.12), value: isHovering)
  }

  private var copyPathButton: some View {
    Button {
      copyPath()
    } label: {
      Image(systemName: didCopyPath ? "checkmark" : "doc.on.clipboard")
        .scaledFont(size: isCompact ? 12 : 13, weight: .medium)
        .foregroundColor(didCopyPath ? OmiColors.success : OmiColors.textTertiary)
        .frame(width: 26, height: 26)
        .background(
          RoundedRectangle(cornerRadius: 7, style: .continuous)
            .fill(Color.white.opacity(isHovering ? 0.08 : 0))
        )
        .contentShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
    }
    .buttonStyle(.plain)
    .help(didCopyPath ? "Copied path" : "Copy path")
    .opacity(isHovering || didCopyPath ? 1 : 0)
    .animation(.easeInOut(duration: 0.12), value: isHovering)
    .animation(.easeInOut(duration: 0.15), value: didCopyPath)
  }

  private func copyPath() {
    ChatResourceActions.copyPath(resource)
    didCopyPath = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
      didCopyPath = false
    }
  }

  // MARK: Image tile

  @ViewBuilder
  private var imageTile: some View {
    ZStack(alignment: .bottomLeading) {
      resourceImage

      LinearGradient(
        colors: [Color.black.opacity(0), Color.black.opacity(0.55)],
        startPoint: .center,
        endPoint: .bottom
      )

      HStack(spacing: 6) {
        Image(systemName: iconName)
          .scaledFont(size: 11, weight: .semibold)
        Text(resource.title)
          .scaledFont(size: 11, weight: .semibold)
          .lineLimit(1)
          .truncationMode(.middle)
        Spacer(minLength: 0)
        if resource.canOpen {
          Image(systemName: "arrow.up.right")
            .scaledFont(size: 10, weight: .semibold)
            .foregroundColor(.white.opacity(isHovering ? 0.95 : 0.7))
        }
      }
      .foregroundColor(.white)
      .padding(.horizontal, 10)
      .padding(.vertical, 8)

      if resource.canOpen {
        Image(systemName: didCopyPath ? "checkmark" : "doc.on.clipboard")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white)
          .frame(width: 28, height: 28)
          .background(Circle().fill(Color.black.opacity(0.42)))
          .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
          .padding(8)
          .opacity(isHovering || didCopyPath ? 1 : 0)
          .animation(.easeInOut(duration: 0.12), value: isHovering)
          .onTapGesture { copyPath() }
      }
    }
    .frame(height: 140)
    .background(fillColor)
  }

  @ViewBuilder
  private var resourceImage: some View {
    if let data = resource.imageData, let img = NSImage(data: data) {
      Image(nsImage: img).resizable().scaledToFill()
    } else if let urlString = resource.thumbnailURL, let url = URL(string: urlString) {
      AsyncImage(url: url) { phase in
        switch phase {
        case .success(let image):
          image.resizable().scaledToFill()
        case .failure:
          fallbackPlaceholder
        default:
          ProgressView()
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(OmiColors.backgroundTertiary.opacity(0.5))
        }
      }
    } else {
      fallbackPlaceholder
    }
  }

  private var fallbackPlaceholder: some View {
    ZStack {
      OmiColors.backgroundTertiary.opacity(0.6)
      Image(systemName: iconName)
        .scaledFont(size: 26)
        .foregroundColor(OmiColors.textTertiary)
    }
  }

  // MARK: Styling

  private var fillColor: Color {
    let base = OmiColors.backgroundTertiary.opacity(isCompact ? 0.72 : 0.9)
    return isHovering && resource.canOpen
      ? OmiColors.backgroundQuaternary.opacity(0.85)
      : base
  }

  private var borderColor: Color {
    isHovering && resource.canOpen
      ? Color.white.opacity(0.14)
      : Color.white.opacity(0.05)
  }

  // MARK: Menu

  @ViewBuilder
  private var actionMenu: some View {
    if resource.canOpen {
      Button("Open") { onOpen(resource) }
    }
    if resource.canRevealInFinder {
      Button("Reveal in Finder") { onReveal(resource) }
    }
    if let uri = resource.uri, !uri.isEmpty {
      Button("Copy Path") { ChatResourceActions.copyPath(resource) }
    }
  }

  private var iconName: String {
    if resource.isImage { return "photo" }
    if resource.mimeType == "application/pdf" { return "doc.richtext" }
    if resource.mimeType?.contains("json") == true { return "curlybraces.square" }
    if resource.mimeType == "text/html" || resource.mimeType == "text/markdown" { return "chevron.left.forwardslash.chevron.right" }
    if resource.mimeType?.contains("spreadsheet") == true || resource.mimeType?.contains("csv") == true {
      return "tablecells"
    }
    if resource.origin == .generatedArtifact { return "sparkles" }
    return "doc"
  }
}

enum ChatResourceActions {
  static func open(_ resource: ChatResource) {
    guard let url = resource.fileURL else { return }
    NSWorkspace.shared.open(url)
  }

  static func revealInFinder(_ resource: ChatResource) {
    guard let url = resource.fileURL else { return }
    NSWorkspace.shared.activateFileViewerSelecting([url])
  }

  static func copyPath(_ resource: ChatResource) {
    guard let uri = resource.uri, !uri.isEmpty else { return }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(resource.fileURL?.path ?? uri, forType: .string)
  }
}
