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
//  Two things worth keeping:
//
//  - **It loads the full-resolution frame, not the thumbnail.** `RewindThumbnailLoader` decodes
//    downsampled on purpose, and showing that enlarged is a blurry picture of the thing the user
//    just asked to look at. The tile's cached thumbnail is shown immediately as a placeholder so
//    the sheet never opens empty, then replaced when the real decode lands.
//  - **A frame with no recoverable pixels is a normal state**, not an error: retention removes
//    video chunks and an abandoned chunk is zero bytes on disk. It says so, plainly, instead of
//    presenting a broken-image glyph.
//

import OmiTheme
import SwiftUI

#if canImport(AppKit)
  import AppKit
#endif

/// One frame, plus the words a surface wants shown under it.
///
/// `Identifiable` on the screenshot id so `dismissableSheet(item:)` drives presentation directly:
/// the selection *is* the presentation state, and there is no separate `isPresented` to keep in
/// sync with it.
struct ScreenFrameLightboxItem: Identifiable, Equatable {
  let screenshot: Screenshot
  /// A one-line description, when the surface has one. The window title is the fallback.
  let caption: String?

  var id: Int64 { screenshot.id ?? 0 }

  init(screenshot: Screenshot, caption: String? = nil) {
    self.screenshot = screenshot
    self.caption = caption
  }
}

struct ScreenFrameLightbox: View {
  let item: ScreenFrameLightboxItem
  /// Called when the viewer wants to move; nil when the surface has only one frame.
  var onStep: ((Int) -> Void)?

  @State private var image: NSImage?
  @State private var didAttemptLoad = false

  private var subtitle: String {
    let app = item.screenshot.appName
    let time = item.screenshot.timestamp.formatted(date: .abbreviated, time: .shortened)
    guard let title = item.screenshot.windowTitle, !title.isEmpty, title != app else {
      return "\(app) · \(time)"
    }
    return "\(app) · \(title) · \(time)"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      frame
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        if let caption = item.caption, !caption.isEmpty {
          Text(caption)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
        }
        Text(subtitle)
          .inkStyle(.statusLabel, color: Ink.secondary)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
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

  @ViewBuilder private var frame: some View {
    ZStack {
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(Ink.rowFill)
      if let image {
        Image(nsImage: image)
          .resizable()
          .aspectRatio(contentMode: .fit)
          .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
      } else if didAttemptLoad {
        VStack(spacing: OmiSpacing.xs) {
          AppIconView(appName: item.screenshot.appName, size: 34)
          Text("This moment's pixels are gone — its recording was already cleaned up.")
            .inkStyle(.statusLabel, color: Ink.secondary)
            .multilineTextAlignment(.center)
        }
        .padding(OmiSpacing.lg)
      } else {
        ProgressView().controlSize(.small)
      }
    }
    .frame(maxWidth: .infinity)
    .frame(height: 560)
  }

  private func load() async {
    didAttemptLoad = false
    // The tile the user clicked has usually already decoded a thumbnail. Showing it immediately
    // means the sheet opens with the right picture rather than a spinner, even though it is soft
    // for the moment it takes the full frame to arrive.
    image = RewindThumbnailLoader.shared.cached(item.screenshot)
    let full = try? await RewindStorage.shared.loadScreenshotImage(for: item.screenshot)
    if let full { image = full }
    didAttemptLoad = true
  }
}

extension View {
  /// Present a captured frame full-size. Dismisses on click-outside and on Escape, like every
  /// other sheet in the shell.
  func screenFrameLightbox(
    item: Binding<ScreenFrameLightboxItem?>,
    onStep: ((Int) -> Void)? = nil
  ) -> some View {
    dismissableSheet(item: item) { value in
      ScreenFrameLightbox(item: value, onStep: onStep)
    }
  }
}
