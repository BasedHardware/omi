import AppKit
import Cocoa
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

/// Reusable chat input field with send button, extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
///
/// When `isSending` is true:
///   - Input stays enabled so the user can draft the next message
///   - The action button remains Stop until the current response ends
///
/// Attachment support is opt-in: pass `attachments`, `onAttachmentsAdded`, and
/// `onAttachmentRemoved` to enable the paperclip button, the staged-files row,
/// and drag-drop. When omitted (e.g. task-sidebar chat) the input behaves as
/// before.
enum ChatComposerLayout {
  /// The visible margin around every edge of a composer shell.
  static let shellInset: CGFloat = OmiSpacing.sm
  /// Shared page margin for the regular chat composer.
  static let pageMargin: CGFloat = OmiSpacing.lg
  /// Maximum width shared by the readable chat/composer lane and shell chrome.
  /// Keep navigation and the Home chat column on the same vertical edges.
  static let contentLaneMaxWidth: CGFloat = 900
  /// The transcript uses the same visible edge as the composer shell.
  static let transcriptEdgeInset: CGFloat = pageMargin
  /// The height over which transcript content fades into the composer.
  /// Keep this transition tight: a large translucent raster reads as a
  /// pixelated glow around the input on non-Retina displays.
  static let fadeHeight: CGFloat = OmiSpacing.md
  static let shellRadius: CGFloat = 18
}

/// Intentionally transparent: transcript content must not be obscured by a
/// decorative composer glow.
struct ChatComposerFade: View {
  var body: some View {
    Color.clear
      .frame(height: ChatComposerLayout.fadeHeight)
      .allowsHitTesting(false)
      .accessibilityHidden(true)
  }
}

extension View {
  /// Lightweight composer chrome shared by regular and Notch chat.
  /// Keeping the inset equal on every edge avoids the heavy bezel effect.
  ///
  /// The stroke is `Ink.separator` — a *dynamic* system colour, which is what lets one modifier
  /// serve two grounds. The main window's composer sits on the light-pinned glass and the Notch's
  /// sits on `NotchGlass.fill` in a `.vibrantDark` view, and a separator resolves correctly in each.
  /// The fixed hairline it replaced only ever suited the dark one.
  func chatComposerShell(fill: Color = Ink.rowFill) -> some View {
    padding(ChatComposerLayout.shellInset)
      .background(
        RoundedRectangle(cornerRadius: ChatComposerLayout.shellRadius, style: .continuous)
          .fill(fill)
      )
      .overlay {
        RoundedRectangle(cornerRadius: ChatComposerLayout.shellRadius, style: .continuous)
          .stroke(Ink.separator, lineWidth: 1)
      }
  }
}

struct ChatInputView: View {
  let onSend: (String) -> Void
  var onStop: (() -> Void)? = nil
  let isSending: Bool
  var isStopping: Bool = false
  var placeholder: String = "Type a message..."
  @Binding var mode: ChatMode
  /// Optional text to pre-fill the input (e.g. task context). Consumed on change.
  var pendingText: Binding<String>?
  @Binding var inputText: String

  /// Currently staged attachments. When nil, the attach button + drag-drop are hidden.
  var attachments: Binding<[ChatAttachment]>? = nil
  /// Called when the user picks files via the paperclip or drags them onto the input.
  var onAttachmentsAdded: (([URL]) -> Void)? = nil
  /// Called when the user removes a staged attachment chip.
  var onAttachmentRemoved: ((String) -> Void)? = nil
  /// Sources staged by a page action. They are shown above the editor and are
  /// intentionally independent from file uploads.
  var references: [ChatComposerReference] = []
  var onReferenceRemoved: ((String) -> Void)? = nil
  /// Shows the push-to-talk mic button. Clicking it drives the same
  /// `PushToTalkManager` turn the keyboard shortcut does.
  var showsPushToTalk: Bool = true

  @AppStorage("askModeEnabled") private var askModeEnabled = false
  @Environment(\.fontScale) private var fontScale
  @State private var isDropTargeted = false
  @State private var hasMarkedText = false

  private var hasText: Bool {
    !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  private var attachmentsEnabled: Bool { attachments != nil }
  private var currentAttachments: [ChatAttachment] { attachments?.wrappedValue ?? [] }

  /// Padding used for both the NSTextView (via textContainerInset) and the
  /// placeholder overlay — guaranteeing the cursor and placeholder align.
  private let inputPaddingH: CGFloat = 12
  private let inputPaddingV: CGFloat = 12

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      if !references.isEmpty {
        ChatComposerReferenceRow(
          references: references,
          onRemove: { id in onReferenceRemoved?(id) }
        )
        .accessibilityIdentifier("chat-composer-references")
      }

      if attachmentsEnabled && !currentAttachments.isEmpty {
        AttachmentPreviewRow(
          attachments: currentAttachments,
          onRemove: { id in onAttachmentRemoved?(id) }
        )
      }

      HStack(alignment: .center, spacing: OmiSpacing.sm) {
        if attachmentsEnabled {
          Button(action: pickFiles) {
            Image(systemName: "paperclip")
              .scaledFont(size: OmiType.heading, weight: .medium)
              .foregroundColor(Ink.secondary)
              .frame(width: 32, height: 32)
          }
          .buttonStyle(.plain)
          .help("Attach files")
          .disabled(currentAttachments.count >= kMaxChatAttachments)
        }

        if showsPushToTalk {
          PushToTalkMicButton()
        }

        // Input field with floating toggle
        ZStack(alignment: .topTrailing) {
          // Hidden Text drives the SwiftUI height; OmiTextEditor overlays it exactly.
          // This lets SwiftUI measure height from text content without fighting AppKit's
          // scroll view layout — the onHeightChange pattern caused layout loops inside
          // the TaskChatPanel VStack with frame(maxHeight: .infinity).
          Text(inputText.isEmpty ? " " : inputText + " ")
            .scaledFont(size: OmiType.body)
            .padding(.horizontal, inputPaddingH)
            .padding(.vertical, inputPaddingV)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .opacity(0)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
            .overlay(alignment: .topLeading) {
              // Placeholder text — padding matches textContainerInset exactly
              if inputText.isEmpty && !hasMarkedText {
                Text(placeholder)
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                  .padding(.horizontal, inputPaddingH)
                  .padding(.vertical, inputPaddingV)
                  .allowsHitTesting(false)
              }
            }
            .overlay {
              OmiTextEditor(
                text: $inputText,
                fontSize: round(14 * fontScale),
                textColor: Ink.nsPrimaryOnGlass,
                textContainerInset: NSSize(width: inputPaddingH, height: inputPaddingV),
                onSubmit: handleSubmit,
                onMarkedTextChange: { hasMarkedText = $0 }
              )
            }
            .frame(maxHeight: 200)
            .clipped()
            // The well is one step up from the shell it sits in, so the two stay distinguishable
            // without either painting an opaque ground over the glass.
            .background(Ink.rowFillHover)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))

          // Floating Ask/Act toggle (top-right, inside the input area)
          if askModeEnabled {
            ChatModeToggle(mode: $mode)
              .padding(.top, OmiSpacing.sm)
              .padding(.trailing, OmiSpacing.sm)
          }
        }

        // Send/Stop button — inline to the right of the input
        if isSending {
          if isStopping {
            ProgressView()
              .controlSize(.small)
              .frame(width: 24, height: 24)
          } else {
            Button(action: { onStop?() }) {
              Image(systemName: "stop.circle.fill")
                .scaledFont(size: 24)
                .foregroundColor(.red.opacity(0.8))
            }
            .buttonStyle(.plain)
          }
        } else {
          Button(action: handleSubmit) {
            Image(systemName: "arrow.up.circle.fill")
              .scaledFont(size: 24)
              .foregroundColor(canSend ? Ink.accent : Ink.secondary)
          }
          .buttonStyle(.plain)
          .disabled(!canSend)
        }
      }
    }
    .chatComposerShell(fill: isDropTargeted ? Ink.rowFillHover : Ink.rowFill)
    .overlay {
      RoundedRectangle(cornerRadius: ChatComposerLayout.shellRadius, style: .continuous)
        .stroke(dropStrokeColor, lineWidth: isDropTargeted ? 1.5 : 0)
    }
    .fixedSize(horizontal: false, vertical: true)
    .if(attachmentsEnabled) { view in
      view.onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
    }
    .onAppear {
      // When ask mode is disabled, ensure we're always in act mode
      if !askModeEnabled {
        mode = .act
      }
      if let pending = pendingText?.wrappedValue, !pending.isEmpty {
        inputText = pending
        pendingText?.wrappedValue = ""
      }
    }
    .onChange(of: pendingText?.wrappedValue ?? "") { _, newValue in
      if !newValue.isEmpty {
        inputText = newValue
        pendingText?.wrappedValue = ""
      }
    }
    .onChange(of: askModeEnabled) { _, enabled in
      if !enabled {
        mode = .act
      }
    }
  }

  /// Send is enabled when there's text OR (when supported) any attachment ready
  /// to ship — Flutter allows sending attachments without text.
  private var canSend: Bool {
    guard !hasMarkedText else { return false }
    if hasText { return true }
    if attachmentsEnabled && !currentAttachments.isEmpty { return true }
    return false
  }

  private var dropStrokeColor: Color {
    isDropTargeted ? Ink.accent.opacity(0.6) : Ink.separator
  }

  private func handleSubmit() {
    guard canSend else { return }
    guard !isSending else { return }
    let text = inputText
    onSend(text)
  }

  private func pickFiles() {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = true
    panel.allowedContentTypes = [
      .image, .jpeg, .png, .gif, .heic, .heif, .webP, .tiff, .bmp,
      .pdf, .plainText, .json, .commaSeparatedText, .html,
      .text, .content,
    ]
    if panel.runModal() == .OK {
      let remaining = max(0, kMaxChatAttachments - currentAttachments.count)
      let urls = Array(panel.urls.prefix(remaining))
      if !urls.isEmpty {
        onAttachmentsAdded?(urls)
      }
    }
  }

  private func handleDrop(providers: [NSItemProvider]) -> Bool {
    ChatAttachmentDropHandler.collectURLs(from: providers) { [currentAttachments] urls in
      guard !urls.isEmpty else { return }
      let remaining = max(0, kMaxChatAttachments - currentAttachments.count)
      let allowed = Array(urls.prefix(remaining))
      if !allowed.isEmpty {
        onAttachmentsAdded?(allowed)
      }
    }
  }
}

// MARK: - File Drop Helper

enum ChatAttachmentDropHandler {
  /// Thread-safe accumulator for URLs gathered from concurrent
  /// `NSItemProvider.loadItem` completions. `@unchecked Sendable` because all
  /// mutation is serialized through `lock`; the captured `let` reference is
  /// therefore safe to share across the @Sendable completion closures.
  private final class URLBuffer: @unchecked Sendable {
    private var urls: [URL] = []
    private let lock = NSLock()

    func append(_ url: URL) {
      lock.lock()
      urls.append(url)
      lock.unlock()
    }

    func snapshot() -> [URL] {
      lock.lock()
      let copy = urls
      lock.unlock()
      return copy
    }
  }

  static func collectURLs(from providers: [NSItemProvider], onComplete: @escaping ([URL]) -> Void) -> Bool {
    let buffer = URLBuffer()
    let group = DispatchGroup()
    for provider in providers {
      guard provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) else { continue }
      group.enter()
      provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
        defer { group.leave() }
        let loadedURL: URL?
        if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
          loadedURL = url
        } else if let url = item as? URL {
          loadedURL = url
        } else {
          loadedURL = nil
        }
        if let loadedURL {
          buffer.append(loadedURL)
        }
      }
    }
    group.notify(queue: .main) { onComplete(buffer.snapshot()) }
    return !providers.isEmpty
  }
}

// MARK: - Attachment Preview Row

/// Horizontal row of chip-like previews shown above the input while files are
/// staged for the next send. Images show their thumbnail; other files show a
/// document icon + filename. A small "x" removes the chip.
struct AttachmentPreviewRow: View {
  let attachments: [ChatAttachment]
  let onRemove: (String) -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(attachments) { attachment in
          AttachmentChip(attachment: attachment, onRemove: { onRemove(attachment.id) })
        }
      }
      .padding(.horizontal, OmiSpacing.hairline)
      .padding(.vertical, OmiSpacing.hairline)
    }
    .frame(maxHeight: 80)
  }
}

/// Removable source chips staged by a page action. This intentionally shares
/// the attachment row's placement above the text editor, but keeps references
/// separate from file uploads so a source selection never enters the upload
/// pipeline or submits an empty message.
struct ChatComposerReferenceRow: View {
  let references: [ChatComposerReference]
  let onRemove: (String) -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: OmiSpacing.sm) {
        ForEach(references) { reference in
          ChatConversationReferencePill(
            reference: reference,
            onRemove: { onRemove(reference.id) })
        }
      }
      .padding(.horizontal, OmiSpacing.hairline)
      .padding(.vertical, OmiSpacing.hairline)
    }
    .frame(maxHeight: 42)
  }
}

private struct AttachmentChip: View {
  let attachment: ChatAttachment
  let onRemove: () -> Void
  @State private var hovering = false

  var body: some View {
    ZStack(alignment: .topTrailing) {
      HStack(spacing: OmiSpacing.sm) {
        thumbnail
        if !attachment.isImage {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(attachment.fileName)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.primary)
              .lineLimit(1)
              .truncationMode(.middle)
            Text(attachment.mimeType)
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
              .lineLimit(1)
          }
          .frame(maxWidth: 160, alignment: .leading)
        }
      }
      .padding(.horizontal, attachment.isImage ? 0 : OmiSpacing.sm)
      .padding(.vertical, attachment.isImage ? 0 : OmiSpacing.xs)
      .background(attachment.isImage ? Color.clear : Ink.rowFillHover)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
      .overlay(alignment: .bottom) {
        if case .failed = attachment.state {
          Text("Failed")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.xxs)
            .padding(.vertical, OmiSpacing.hairline)
            .background(Color.red.opacity(0.85))
            .clipShape(Capsule())
            .padding(OmiSpacing.hairline)
        } else if case .uploading = attachment.state {
          ProgressView()
            .controlSize(.mini)
            .padding(OmiSpacing.hairline)
        }
      }

      Button(action: onRemove) {
        Image(systemName: "xmark.circle.fill")
          .scaledFont(size: OmiType.body)
          .symbolRenderingMode(.palette)
          .foregroundStyle(.white, Color.black.opacity(0.75))
      }
      .buttonStyle(.plain)
      .offset(x: 4, y: -4)
      .opacity(hovering ? 1.0 : 0.85)
    }
    .onHover { hovering = $0 }
  }

  @ViewBuilder
  private var thumbnail: some View {
    if attachment.isImage, let data = attachment.data, let nsImage = NSImage(data: data) {
      Image(nsImage: nsImage)
        .resizable()
        .scaledToFill()
        .frame(width: 60, height: 60)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
    } else if attachment.isImage, let urlString = attachment.thumbnailURL,
      let url = URL(string: urlString)
    {
      AsyncImage(url: url) { phase in
        switch phase {
        case .success(let image):
          image.resizable().scaledToFill()
        default:
          Color.gray.opacity(0.2)
        }
      }
      .frame(width: 60, height: 60)
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
    } else {
      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .fill(Ink.rowFillHover)
        Image(systemName: documentIcon)
          .scaledFont(size: OmiType.heading)
          .foregroundColor(Ink.secondary)
      }
      .frame(width: 44, height: 44)
    }
  }

  private var documentIcon: String {
    switch attachment.mimeType {
    case "application/pdf": return "doc.richtext"
    case let m where m.hasPrefix("text/"): return "doc.text"
    case "application/json": return "curlybraces"
    case let m where m.contains("spreadsheet") || m.contains("excel"): return "tablecells"
    case let m where m.contains("word"): return "doc"
    case "application/zip": return "doc.zipper"
    default: return "doc"
    }
  }
}

// MARK: - View helpers

extension View {
  /// Conditionally apply a view modifier. Keeps drag-drop opt-in so callers
  /// without an `attachments` binding don't accidentally accept files.
  @ViewBuilder
  fileprivate func `if`<Content: View>(
    _ condition: Bool, transform: (Self) -> Content
  ) -> some View {
    if condition {
      transform(self)
    } else {
      self
    }
  }
}

// MARK: - Ask/Act Mode Toggle

struct ChatModeToggle: View {
  @Binding var mode: ChatMode

  var body: some View {
    HStack(spacing: 0) {
      modeButton(for: .ask, label: "Ask")
      modeButton(for: .act, label: "Act")
    }
    // A track with a raised pill on it, the way a real segmented control reads. The dark version
    // inverted that — a near-black pill under white type — which on glass was a slab.
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous))
  }

  private func modeButton(for targetMode: ChatMode, label: String) -> some View {
    let isSelected = mode == targetMode
    return Button(action: { mode = targetMode }) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        // `surface` and not another wash: the selected segment has to lift off the track, and
        // stacking a third wash on two others is a difference nobody can see.
        .background(isSelected ? Ink.surface : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
    }
    .buttonStyle(.plain)
  }
}
