//
//  ScreenFrameLightbox.swift — one captured frame, big enough to actually read.
//
//  Every surface that draws Rewind frames draws them as tiles: the Activity spine's strip, the
//  search grid, a meeting note's carousel. A tile is ~118pt wide, which is enough to recognise a
//  moment and nowhere near enough to read one — so "click it and see it properly" is the same
//  need everywhere, and this is the one place it is implemented.
//
//  Deliberately built on `dismissableSheet` rather than a bespoke overlay: click-outside-to-dismiss
//  and the shell-bounded scrim already exist and already behave correctly inside a glass panel.
//
//  A frame here has two possible sources, and the item carries which one it is:
//
//  - **Local** — a Rewind `Screenshot`, decoded on-device. It loads the full-resolution frame,
//    not the thumbnail: `RewindThumbnailLoader` decodes downsampled on purpose, and showing that
//    enlarged is a blurry picture of the thing the user just asked to look at. The tile's cached
//    thumbnail is shown immediately as a placeholder so the sheet never opens empty, then
//    replaced when the real decode lands. A frame with no recoverable pixels is a normal state,
//    not an error — retention removes video chunks and an abandoned chunk is zero bytes on disk —
//    and it says so plainly instead of presenting a broken-image glyph.
//  - **Remote** — a persisted `ConversationScreenFrame`. Its pixels are a signed URL good for
//    `url_expires_at` (60 minutes), not local storage; `AsyncImage` loads it directly, and a load
//    failure hands back to `onContentUnavailable` so the caller can re-fetch the set rather than
//    leave the broken image up.
//
//  Only a remote item carries `deletable`: deleting a local Activity-spine frame is not a
//  concept the app has, but deleting a persisted meeting screenshot is (contract §9), and the
//  confirm-and-call-the-server flow lives here because this is the one place the full-size frame
//  is already on screen.
//

import OmiTheme
import SwiftUI

#if canImport(AppKit)
  import AppKit
#endif

/// One frame, plus the words a surface wants shown under it.
///
/// `Identifiable` on a string id so `dismissableSheet(item:)` drives presentation directly: the
/// selection *is* the presentation state, and there is no separate `isPresented` to keep in sync
/// with it. Local items key off the Rewind row id; remote items key off the server's frame id —
/// the two id spaces never collide because the two sources are never mixed in one lightbox.
struct ScreenFrameLightboxItem: Identifiable, Equatable {
  enum Source: Equatable {
    case local(Screenshot)
    case remote(contentURL: URL)
  }

  /// Identifies a persisted server frame well enough to delete it.
  struct Deletable: Equatable {
    let conversationID: String
    let frameID: String
  }

  let id: String
  let source: Source
  let caption: String?
  let subtitle: String
  let deletable: Deletable?

  init(screenshot: Screenshot, caption: String? = nil) {
    self.id = String(screenshot.id ?? 0)
    self.source = .local(screenshot)
    self.caption = caption
    self.subtitle = Self.localSubtitle(
      appName: screenshot.appName, windowTitle: screenshot.windowTitle, timestamp: screenshot.timestamp)
    self.deletable = nil
  }

  /// `nil` when the server's `content_url` does not even parse as a URL — nothing sane to open,
  /// so the caller should skip this frame rather than present a lightbox that opens empty.
  init?(frame: ConversationScreenFrame, conversationID: String) {
    guard let url = URL(string: frame.contentURL) else { return nil }
    self.id = frame.id
    self.source = .remote(contentURL: url)
    self.caption = frame.caption.isEmpty ? nil : frame.caption
    self.subtitle = frame.capturedAt.formatted(date: .abbreviated, time: .shortened)
    self.deletable = Deletable(conversationID: conversationID, frameID: frame.id)
  }

  private static func localSubtitle(appName: String, windowTitle: String?, timestamp: Date) -> String {
    let time = timestamp.formatted(date: .abbreviated, time: .shortened)
    guard let windowTitle, !windowTitle.isEmpty, windowTitle != appName else {
      return "\(appName) · \(time)"
    }
    return "\(appName) · \(windowTitle) · \(time)"
  }
}

struct ScreenFrameLightbox: View {
  let item: ScreenFrameLightboxItem
  /// Called when the viewer wants to move; nil when the surface has only one frame.
  var onStep: ((Int) -> Void)?
  /// Called once a confirmed delete is accepted by the server. Nil surfaces (the general Rewind
  /// case) never show the delete affordance at all, whatever `item.deletable` says.
  var onDelete: ((ScreenFrameLightboxItem.Deletable) async -> Void)?
  /// The remote image failed to load — most likely an expired signed URL. Called at most once per
  /// presentation so the caller (the store) can re-fetch the set instead of retrying the same URL.
  var onContentUnavailable: (() -> Void)?

  @State private var image: NSImage?
  @State private var didAttemptLoad = false
  @State private var reportedUnavailable = false
  @State private var isConfirmingDelete = false
  @State private var isDeleting = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      frame
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          if let caption = item.caption, !caption.isEmpty {
            Text(caption)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)
          }
          Text(item.subtitle)
            .inkStyle(.statusLabel, color: Ink.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)

        if let deletable = item.deletable, let onDelete {
          deleteButton(deletable: deletable, onDelete: onDelete)
        }
      }
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: 1100)
    .glassCard(cornerRadius: OmiChrome.controlRadius)
    .task(id: item.id) { await load() }
    // Arrow keys only matter when there is somewhere to go; without a stepper the modifiers would
    // silently swallow the keys from whatever is behind the sheet.
    .background {
      if let onStep {
        Color.clear
          .onKeyPress(.leftArrow) {
            onStep(-1)
            return .handled
          }
          .onKeyPress(.rightArrow) {
            onStep(1)
            return .handled
          }
      }
    }
  }

  @ViewBuilder
  private func deleteButton(
    deletable: ScreenFrameLightboxItem.Deletable,
    onDelete: @escaping (ScreenFrameLightboxItem.Deletable) async -> Void
  ) -> some View {
    Button {
      isConfirmingDelete = true
    } label: {
      Image(systemName: "trash")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .frame(width: 28, height: 28)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .disabled(isDeleting)
    .help("Delete this screenshot")
    .alert("Delete Screenshot", isPresented: $isConfirmingDelete) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        isDeleting = true
        Task {
          await onDelete(deletable)
          isDeleting = false
        }
      }
    } message: {
      Text("This removes the screenshot from this meeting's note. This cannot be undone.")
    }
  }

  @ViewBuilder private var frame: some View {
    ZStack {
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(Ink.rowFill)
      switch item.source {
      case .local(let screenshot):
        if let image {
          Image(nsImage: image)
            .resizable()
            .aspectRatio(contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        } else if didAttemptLoad {
          VStack(spacing: OmiSpacing.xs) {
            AppIconView(appName: screenshot.appName, size: 34)
            Text("This moment's pixels are gone — its recording was already cleaned up.")
              .inkStyle(.statusLabel, color: Ink.secondary)
              .multilineTextAlignment(.center)
          }
          .padding(OmiSpacing.lg)
        } else {
          ProgressView().controlSize(.small)
        }
      case .remote(let contentURL):
        AsyncImage(url: contentURL) { phase in
          switch phase {
          case .success(let loaded):
            loaded
              .resizable()
              .aspectRatio(contentMode: .fit)
              .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
          case .failure:
            VStack(spacing: OmiSpacing.xs) {
              Image(systemName: "photo")
                .scaledFont(size: 26)
                .foregroundColor(Ink.secondary)
              Text("This screenshot's preview link expired.")
                .inkStyle(.statusLabel, color: Ink.secondary)
                .multilineTextAlignment(.center)
            }
            .padding(OmiSpacing.lg)
            .task {
              guard !reportedUnavailable else { return }
              reportedUnavailable = true
              onContentUnavailable?()
            }
          default:
            ProgressView().controlSize(.small)
          }
        }
      }
    }
    .frame(maxWidth: .infinity)
    .frame(height: 560)
  }

  private func load() async {
    guard case .local(let screenshot) = item.source else { return }
    didAttemptLoad = false
    // The tile the user clicked has usually already decoded a thumbnail. Showing it immediately
    // means the sheet opens with the right picture rather than a spinner, even though it is soft
    // for the moment it takes the full frame to arrive.
    image = RewindThumbnailLoader.shared.cached(screenshot)
    let full = try? await RewindStorage.shared.loadScreenshotImage(for: screenshot)
    if let full { image = full }
    didAttemptLoad = true
  }
}

extension View {
  /// Present a captured frame full-size. Dismisses on click-outside and on Escape, like every
  /// other sheet in the shell.
  func screenFrameLightbox(
    item: Binding<ScreenFrameLightboxItem?>,
    onStep: ((Int) -> Void)? = nil,
    onDelete: ((ScreenFrameLightboxItem.Deletable) async -> Void)? = nil,
    onContentUnavailable: (() -> Void)? = nil
  ) -> some View {
    dismissableSheet(item: item) { value in
      ScreenFrameLightbox(
        item: value, onStep: onStep, onDelete: onDelete, onContentUnavailable: onContentUnavailable)
    }
  }
}
