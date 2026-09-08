import AppKit
import OmiTheme
import SwiftUI

enum ChatResourceOrigin: String, Equatable {
  case userAttachment
  case generatedArtifact
  case conversationReference
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
  let sessionId: String?
  let runId: String?
  let state: State
  /// Typed source metadata for a conversation attached to a user turn. This
  /// stays distinct from file URIs and generated-artifact identifiers while
  /// sharing the journal resource lifecycle and transcript rendering path.
  let conversationReference: ChatComposerReference?

  init(
    id: String,
    origin: ChatResourceOrigin,
    title: String,
    subtitle: String?,
    mimeType: String?,
    thumbnailURL: String?,
    imageData: Data?,
    uri: String?,
    artifactId: String?,
    sessionId: String?,
    runId: String?,
    state: State,
    conversationReference: ChatComposerReference? = nil
  ) {
    self.id = id
    self.origin = origin
    self.title = title
    self.subtitle = subtitle
    self.mimeType = mimeType
    self.thumbnailURL = thumbnailURL
    self.imageData = imageData
    self.uri = uri
    self.artifactId = artifactId
    self.sessionId = sessionId
    self.runId = runId
    self.state = state
    self.conversationReference = conversationReference
  }

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
    if let conversationReference {
      return !conversationReference.sourceID.isEmpty
    }
    guard let fileURL else { return false }
    return FileManager.default.fileExists(atPath: fileURL.path)
  }

  var canRevealInFinder: Bool {
    guard let fileURL else { return false }
    return FileManager.default.fileExists(atPath: fileURL.path)
  }

  static func localGeneratedFile(
    id: String,
    title: String,
    subtitle: String?,
    mimeType: String?,
    uri: String
  ) -> ChatResource {
    ChatResource(
      id: id,
      origin: .generatedArtifact,
      title: title,
      subtitle: subtitle,
      mimeType: mimeType,
      thumbnailURL: nil,
      imageData: nil,
      uri: uri,
      artifactId: nil,
      sessionId: nil,
      runId: nil,
      state: .ready
    )
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
      sessionId: nil,
      runId: nil,
      state: state
    )
  }

  static func conversation(_ reference: ChatComposerReference) -> ChatResource {
    ChatResource(
      id: "reference:\(reference.id)",
      origin: .conversationReference,
      title: reference.displayTitle,
      subtitle: reference.displaySubtitle,
      mimeType: nil,
      thumbnailURL: nil,
      imageData: nil,
      uri: nil,
      artifactId: nil,
      sessionId: nil,
      runId: nil,
      state: .ready,
      conversationReference: reference
    )
  }

  static func userMessageResources(
    attachments: [ChatAttachment],
    references: [ChatComposerReference]
  ) -> [ChatResource] {
    attachments.map(ChatResource.attachment) + references.map(ChatResource.conversation)
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
      sessionId: artifact.sessionId,
      runId: artifact.runId,
      state: State(artifactLifecycleState: artifact.lifecycleState)
    )
  }

  /// Key inside chat message `metadata` JSON for persisted resource cards.
  static let messageMetadataResourcesKey = "resources"

  /// User-visible label when a persisted file path no longer resolves on disk.
  static let unavailableOnDiskMessage = "Deleted or moved"

  static func encodeResourcesForPersistence(_ resources: [ChatResource]) -> String? {
    guard !resources.isEmpty else { return nil }
    let encoded = resources.map(persistenceDictionary(for:))
    guard let data = try? JSONSerialization.data(withJSONObject: encoded),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    return json
  }

  static func decodeResourcesFromPersistence(_ json: String) -> [ChatResource] {
    guard let data = json.data(using: .utf8),
      let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return [] }
    return decodeResources(fromJSONArray: array)
  }

  /// Decode resource cards from a chat message's persisted `metadata` JSON blob.
  static func decodeResourcesFromMessageMetadata(_ metadataJSON: String?) -> [ChatResource] {
    guard let metadataJSON,
      let data = metadataJSON.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let array = root[messageMetadataResourcesKey] as? [[String: Any]]
    else { return [] }
    return hydrateFileStates(decodeResources(fromJSONArray: array))
  }

  /// Merge resource cards into an existing metadata JSON object (attachments, tool_calls, etc.).
  static func mergeResourcesIntoMessageMetadata(
    _ metadataJSON: String?,
    resources: [ChatResource]
  ) -> String? {
    guard !resources.isEmpty else { return metadataJSON }
    var root = parseMessageMetadataRoot(metadataJSON)
    root[messageMetadataResourcesKey] = resources.map(persistenceDictionary(for:))
    guard let data = try? JSONSerialization.data(withJSONObject: root),
      let json = String(data: data, encoding: .utf8)
    else { return metadataJSON }
    return json
  }

  /// Re-check local file paths after restart and surface missing artifacts in the UI.
  static func hydrateFileStates(_ resources: [ChatResource]) -> [ChatResource] {
    resources.map { resource in
      guard resource.origin == .generatedArtifact || resource.fileURL != nil else {
        return resource
      }
      guard let fileURL = resource.fileURL else {
        return resource.markingUnavailableOnDisk()
      }
      if FileManager.default.fileExists(atPath: fileURL.path) {
        return resource
      }
      return resource.markingUnavailableOnDisk()
    }
  }

  func refreshedFromKernelArtifact(_ artifact: AgentArtifactProjection) -> ChatResource {
    let refreshed = ChatResource.artifact(artifact)
    guard let fileURL = refreshed.fileURL else {
      return markingUnavailableOnDisk()
    }
    if FileManager.default.fileExists(atPath: fileURL.path) {
      return refreshed
    }
    return markingUnavailableOnDisk()
  }

  func markingUnavailableOnDisk() -> ChatResource {
    ChatResource(
      id: id,
      origin: origin,
      title: title,
      subtitle: Self.unavailableOnDiskMessage,
      mimeType: mimeType,
      thumbnailURL: thumbnailURL,
      imageData: imageData,
      uri: uri,
      artifactId: artifactId,
      sessionId: sessionId,
      runId: runId,
      state: .failed(Self.unavailableOnDiskMessage),
      conversationReference: conversationReference
    )
  }

  private static func parseMessageMetadataRoot(_ metadataJSON: String?) -> [String: Any] {
    guard let metadataJSON,
      let data = metadataJSON.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return [:] }
    return root
  }

  private static func decodeResources(fromJSONArray array: [[String: Any]]) -> [ChatResource] {
    array.compactMap { dict in
      guard let id = dict["id"] as? String,
        let title = dict["title"] as? String
      else { return nil }
      let origin =
        (dict["origin"] as? String).flatMap(ChatResourceOrigin.init(rawValue:))
        ?? .userAttachment
      let conversationReference: ChatComposerReference?
      if origin == .conversationReference,
        let rawKind = dict["referenceKind"] as? String,
        let kind = ChatComposerReference.Kind(rawValue: rawKind),
        let sourceID = dict["sourceID"] as? String
      {
        conversationReference = ChatComposerReference(
          kind: kind,
          sourceID: sourceID,
          title: title,
          preview: dict["preview"] as? String ?? "",
          momentTimestampMs: dict["momentTimestampMs"] as? Int
        )
      } else {
        conversationReference = nil
      }
      return ChatResource(
        id: id,
        origin: origin,
        title: title,
        subtitle: dict["subtitle"] as? String,
        mimeType: dict["mimeType"] as? String,
        thumbnailURL: dict["thumbnailURL"] as? String,
        imageData: nil,
        uri: dict["uri"] as? String,
        artifactId: dict["artifactId"] as? String,
        sessionId: dict["sessionId"] as? String,
        runId: dict["runId"] as? String,
        state: persistenceState(from: dict["state"] as? String),
        conversationReference: conversationReference
      )
    }
  }

  private static func persistenceDictionary(for resource: ChatResource) -> [String: Any] {
    var dict: [String: Any] = [
      "id": resource.id,
      "origin": resource.origin.rawValue,
      "title": resource.title,
      "state": persistenceStateString(resource.state),
    ]
    if let subtitle = resource.subtitle, subtitle != unavailableOnDiskMessage {
      dict["subtitle"] = subtitle
    }
    if let mimeType = resource.mimeType { dict["mimeType"] = mimeType }
    if let thumbnailURL = resource.thumbnailURL { dict["thumbnailURL"] = thumbnailURL }
    if let uri = resource.uri { dict["uri"] = uri }
    if let artifactId = resource.artifactId { dict["artifactId"] = artifactId }
    if let sessionId = resource.sessionId { dict["sessionId"] = sessionId }
    if let runId = resource.runId { dict["runId"] = runId }
    if let reference = resource.conversationReference {
      dict["referenceKind"] = reference.kind.rawValue
      dict["sourceID"] = reference.sourceID
      dict["preview"] = reference.preview
      if let momentTimestampMs = reference.momentTimestampMs {
        dict["momentTimestampMs"] = momentTimestampMs
      }
    }
    return dict
  }

  private static func persistenceStateString(_ state: State) -> String {
    switch state {
    case .uploading: return "uploading"
    case .ready: return "ready"
    case .failed(let message) where message == unavailableOnDiskMessage:
      return "ready"
    case .failed(let message): return "failed:\(message)"
    case .retained: return "retained"
    case .opened: return "opened"
    case .dismissed: return "dismissed"
    }
  }

  private static func persistenceState(from raw: String?) -> State {
    guard let raw else { return .ready }
    switch raw {
    case "uploading": return .uploading
    case "retained": return .retained
    case "opened": return .opened
    case "dismissed": return .dismissed
    default:
      if raw.hasPrefix("failed:") {
        return .failed(String(raw.dropFirst("failed:".count)))
      }
      return .ready
    }
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

extension AgentArtifactProjection {
  fileprivate var subtitle: String? {
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
      VStack(alignment: alignment, spacing: OmiSpacing.xs) {
        ForEach(resources) { resource in
          if let reference = resource.conversationReference {
            ChatConversationReferencePill(
              reference: reference,
              onOpen: { (onOpen ?? ChatResourceActions.open)(resource) }
            )
          } else {
            ChatResourceCard(
              resource: resource,
              density: density,
              onOpen: onOpen ?? ChatResourceActions.open,
              onReveal: onReveal ?? ChatResourceActions.revealInFinder
            )
          }
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
  private var cornerRadius: CGFloat { isCompact ? OmiChrome.smallControlRadius : OmiChrome.chipRadius }

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
    HStack(spacing: OmiSpacing.sm) {
      iconBadge

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(resource.title)
          .scaledFont(size: isCompact ? OmiType.caption : OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
          .truncationMode(.middle)
        if let subtitle = resource.subtitle, !subtitle.isEmpty {
          Text(subtitle)
            .scaledFont(size: isCompact ? OmiType.micro : OmiType.caption)
            .foregroundColor(subtitleColor)
            .lineLimit(1)
            .truncationMode(.middle)
        }
      }

      Spacer(minLength: 6)

      trailingAccessory
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.sm)
    .background(fillColor)
  }

  private var iconBadge: some View {
    ZStack {
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .fill(iconBadgeFill)
      Image(systemName: iconName)
        .scaledFont(size: isCompact ? OmiType.body : OmiType.subheading, weight: .medium)
        .foregroundColor(iconTint)
    }
    .frame(width: isCompact ? 30 : 36, height: isCompact ? 30 : 36)
  }

  /// Generated artifacts get a slightly stronger badge so "the agent made this" reads differently
  /// from a file the user attached, without reaching for a hue.
  ///
  /// These were white washes, which is what made the badge disappear on the light panel: white at
  /// 8% over glass is glass. The two glass row washes carry the same one-step difference and
  /// composite correctly on any ground.
  private var iconBadgeFill: Color {
    let isEmphasized = isHovering || resource.origin == .generatedArtifact
    return isEmphasized ? Ink.rowFillHover : Ink.rowFill
  }

  private var iconTint: Color {
    resource.origin == .generatedArtifact ? Ink.primary : Ink.secondary
  }

  private var subtitleColor: Color {
    if case .failed = resource.state {
      return PageGlass.warning
    }
    return Ink.secondary
  }

  @ViewBuilder
  private var trailingAccessory: some View {
    switch resource.state {
    case .uploading:
      ProgressView().controlSize(.small)
    case .failed:
      Image(systemName: "exclamationmark.triangle.fill")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(PageGlass.warning)
        .help(resource.subtitle ?? "Unavailable")
    default:
      if resource.canOpen {
        HStack(spacing: OmiSpacing.hairline) {
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
      .scaledFont(size: isCompact ? OmiType.micro : OmiType.caption, weight: .semibold)
      .foregroundColor(isHovering ? Ink.primary : Ink.secondary)
      .frame(width: 18, height: 26)
      .omiAnimation(.easeInOut(duration: 0.12), value: isHovering)
  }

  private var copyPathButton: some View {
    Button {
      copyPath()
    } label: {
      Image(systemName: didCopyPath ? "checkmark" : "doc.on.clipboard")
        .scaledFont(size: isCompact ? OmiType.caption : OmiType.body, weight: .medium)
        .foregroundColor(didCopyPath ? Ink.listeningGreen : Ink.secondary)
        .frame(width: 26, height: 26)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.badgeRadius, style: .continuous)
            .fill(isHovering ? Ink.rowFill : Color.clear)
        )
        .contentShape(RoundedRectangle(cornerRadius: OmiChrome.badgeRadius, style: .continuous))
    }
    .buttonStyle(.plain)
    .help(didCopyPath ? "Copied path" : "Copy path")
    .opacity(isHovering || didCopyPath ? 1 : 0)
    .omiAnimation(.easeInOut(duration: 0.12), value: isHovering)
    .omiAnimation(.easeInOut(duration: 0.15), value: didCopyPath)
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

      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: iconName)
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(resource.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .lineLimit(1)
          .truncationMode(.middle)
        Spacer(minLength: 0)
        if resource.canOpen {
          Image(systemName: "arrow.up.right")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundColor(.white.opacity(isHovering ? 0.95 : 0.7))
        }
      }
      .foregroundColor(.white)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.sm)

      if resource.canOpen {
        Image(systemName: didCopyPath ? "checkmark" : "doc.on.clipboard")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(.white)
          .frame(width: 28, height: 28)
          .background(Circle().fill(Color.black.opacity(0.42)))
          .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
          .padding(OmiSpacing.sm)
          .opacity(isHovering || didCopyPath ? 1 : 0)
          .omiAnimation(.easeInOut(duration: 0.12), value: isHovering)
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
    } else if let fileURL = resource.fileURL, let image = NSImage(contentsOf: fileURL) {
      Image(nsImage: image).resizable().scaledToFill()
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
            .background(Ink.rowFill)
        }
      }
    } else {
      fallbackPlaceholder
    }
  }

  private var fallbackPlaceholder: some View {
    ZStack {
      Ink.rowFill
      Image(systemName: iconName)
        .scaledFont(size: 26)
        .foregroundColor(Ink.secondary)
    }
  }

  // MARK: Styling

  /// The card itself, as a row on the glass rather than an opaque tile over it.
  ///
  /// `PageGlass.rowFill` is the shared answer for exactly this state pair, so a resource card and a
  /// task row are visibly the same object. Only the hoverable card lifts: a card that cannot be
  /// opened has nothing to promise.
  private var fillColor: Color {
    PageGlass.rowFill(isHovering && resource.canOpen ? .hover : .rest)
  }

  /// Was a white hairline at 14% / 5% — a white line on white glass, i.e. no border at all.
  private var borderColor: Color {
    isHovering && resource.canOpen ? Ink.hairline : Ink.separator
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
    if resource.mimeType == "text/html" || resource.mimeType == "text/markdown" {
      return "chevron.left.forwardslash.chevron.right"
    }
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
