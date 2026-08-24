//
//  MeetingNoteScreenshotViews.swift — the banner and the strip, as the note draws them.
//
//  **The banner is designed, not photographic, and that is a finding rather than a preference.**
//  Across five real meetings not one captured frame worked as a full-bleed article header: the
//  frames are Claude Code, Cursor, ChatGPT and GitHub, and a wide crop of a text-editing session
//  is a smear of grey. So the banner is a composition the app renders — a muted ground derived
//  from the chosen frame, the title as real text, and the frame itself as a small legible inset —
//  and the screenshot is an ingredient in it rather than the surface of it.
//
//  Two consequences worth keeping through any refactor:
//
//  - **The title is never burned into pixels.** It stays selectable, resizable, themed text, which
//    is also the only version that survives a narrow window.
//  - **No banner is a first-class state.** A meeting whose frames are all dense text gets the
//    note's ordinary header and still gets its strip. Absence of a banner never suppresses the
//    strip; they are independent.
//
//  The strip is `SpineMomentsRow`, unchanged, from the Activity spine. Reusing the component was
//  the point: the same tiles, the same edge fade, the same graceful behaviour when a chunk has
//  been aged out and a frame has no pixels left.
//

import OmiTheme
import SwiftUI

#if canImport(AppKit)
  import AppKit
#endif

/// Owns the feature state only after the developer gate has admitted this branch.
/// `ConversationDetailView` renders its ordinary summary directly when the gate is off, so a
/// shipped bundle constructs no screenshot store, child view, or task.
struct MeetingNoteScreenshotsLayout<BeforeScreenshots: View, AfterScreenshots: View>: View {
  @StateObject private var store = MeetingScreenshotsStore()

  let conversation: ServerConversation
  let date: Date
  let beforeScreenshots: BeforeScreenshots
  let afterScreenshots: AfterScreenshots

  init(
    conversation: ServerConversation,
    date: Date,
    @ViewBuilder beforeScreenshots: () -> BeforeScreenshots,
    @ViewBuilder afterScreenshots: () -> AfterScreenshots
  ) {
    self.conversation = conversation
    self.date = date
    self.beforeScreenshots = beforeScreenshots()
    self.afterScreenshots = afterScreenshots()
  }

  var body: some View {
    MeetingNoteScreenshotBannerSlot(store: store, conversation: conversation, date: date)
    beforeScreenshots
    MeetingNoteScreenshotStrip(store: store, conversation: conversation, date: date)
    afterScreenshots
  }
}

// MARK: - Banner

struct MeetingNoteScreenshotBannerSlot: View {
  @ObservedObject var store: MeetingScreenshotsStore
  let conversation: ServerConversation
  let date: Date

  @ViewBuilder var body: some View {
    if let banner = store.banner {
      MeetingNoteBanner(
        frame: banner,
        title: conversation.structured.title.isEmpty ? "Untitled conversation" : conversation.structured.title,
        date: date)
    }
  }
}

struct MeetingNoteBanner: View {
  let frame: MeetingScreenshotsStore.Frame
  let title: String
  let date: Date

  @State private var image: NSImage?
  @State private var ground: [Color] = []

  private static let height: CGFloat = 132

  var body: some View {
    ZStack {
      // The ground: two or three colours sampled from the frame itself, clamped well away from
      // both ends of the luminance range so text over it is legible in either appearance.
      LinearGradient(
        colors: ground.isEmpty ? [Ink.rowFill, Ink.rowFillHover] : ground,
        startPoint: .topLeading,
        endPoint: .bottomTrailing)

      HStack(alignment: .center, spacing: OmiSpacing.lg) {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(title)
            .scaledFont(size: OmiType.title, weight: .semibold)
            .foregroundStyle(.white)
            .lineLimit(2)
            .multilineTextAlignment(.leading)
            .shadow(color: .black.opacity(0.35), radius: 8, y: 1)
          Text(date.formatted(date: .abbreviated, time: .shortened))
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundStyle(.white.opacity(0.82))
            .shadow(color: .black.opacity(0.3), radius: 6, y: 1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)

        // The inset. Roughly a third of the width, never stretched, never blurred into a texture:
        // at this size a screenshot reads as "here is the thing we were looking at", which is the
        // only job it can actually do.
        if let image {
          Image(nsImage: image)
            .resizable()
            .aspectRatio(contentMode: .fill)
            .frame(width: 176, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(.white.opacity(0.28), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.28), radius: 10, y: 3)
            .accessibilityLabel(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
    }
    .frame(height: Self.height)
    .frame(maxWidth: .infinity)
    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    .task(id: frame.id) { await load() }
  }

  private func load() async {
    guard let loaded = await RewindThumbnailLoader.shared.thumbnail(for: frame.moment.screenshot) else { return }
    image = loaded
    ground = MeetingBannerPalette.ground(from: loaded)
  }
}

// MARK: - Palette

/// Two colours pulled out of a frame and forced into a range a white title survives.
///
/// A screenshot's own dominant colour is usually near-white (a document) or near-black (an editor),
/// and either taken literally makes the title unreadable. So the sample sets the *hue*, and the
/// luminance and saturation are ours.
enum MeetingBannerPalette {
  static func ground(from image: NSImage) -> [Color] {
    #if canImport(AppKit)
      guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return [] }
      let width = 8
      let height = 8
      var pixels = [UInt8](repeating: 0, count: width * height * 4)
      guard
        let context = CGContext(
          data: &pixels, width: width, height: height, bitsPerComponent: 8,
          bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
      else { return [] }
      context.interpolationQuality = .low
      context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))

      // Average hue, weighted towards the more saturated pixels — the chrome of an app carries its
      // identity, and a page of black text on white carries none.
      var x = 0.0
      var y = 0.0
      var weight = 0.0
      for i in stride(from: 0, to: pixels.count, by: 4) {
        let colour = NSColor(
          red: CGFloat(pixels[i]) / 255, green: CGFloat(pixels[i + 1]) / 255,
          blue: CGFloat(pixels[i + 2]) / 255, alpha: 1)
        var h: CGFloat = 0
        var s: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 0
        colour.usingColorSpace(.deviceRGB)?.getHue(&h, saturation: &s, brightness: &b, alpha: &a)
        let w = Double(s) + 0.05
        x += cos(Double(h) * 2 * .pi) * w
        y += sin(Double(h) * 2 * .pi) * w
        weight += w
      }
      guard weight > 0 else { return [] }
      var hue = atan2(y / weight, x / weight) / (2 * .pi)
      if hue < 0 { hue += 1 }

      return [
        Color(hue: hue, saturation: 0.42, brightness: 0.46),
        Color(hue: (hue + 0.06).truncatingRemainder(dividingBy: 1), saturation: 0.55, brightness: 0.28),
      ]
    #else
      return []
    #endif
  }

}

// MARK: - The section inside the note

struct MeetingNoteScreenshotStrip: View {
  @ObservedObject var store: MeetingScreenshotsStore
  let conversation: ServerConversation
  let date: Date

  @State private var expandedFrame: ScreenFrameLightboxItem?

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      MeetingNoteScreenshotsSection(store: store) { moment in
        expandedFrame = store.lightboxItem(for: moment.id)
      }
    }
    .screenFrameLightbox(item: $expandedFrame) { step in
      expandedFrame = store.lightboxItem(steppingFrom: expandedFrame?.id, by: step)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .task(id: conversation.id) {
      store.load(
        conversationID: conversation.id,
        title: conversation.structured.title,
        start: date,
        end: conversation.finishedAt ?? date.addingTimeInterval(3600))
    }
  }
}

struct MeetingNoteScreenshotsSection: View {
  @ObservedObject var store: MeetingScreenshotsStore
  let onOpen: (SpineMoment) -> Void

  var body: some View {
    switch store.phase {
    case .idle, .disabled:
      // **Not `EmptyView()`.** A view that resolves to `EmptyView` contributes nothing to the
      // render tree, and SwiftUI is entitled to skip lifecycle modifiers attached to it -- which
      // is exactly how the `.task` that starts this whole pipeline never fired, leaving the note
      // with no banner, no strip, and no diagnostics to explain the absence. A zero-height
      // `Color.clear` is a real view and keeps the modifier alive.
      Color.clear.frame(height: 0)

    case .selecting:
      label("Looking through what was on screen…")

    case .judging(let candidates):
      label("Reviewing \(candidates) moment\(candidates == 1 ? "" : "s")…")

    case .noCapture:
      // Deliberately silent. A meeting with no screen capture is the normal case for anyone who
      // does not leave Rewind on, and an empty state announcing it is noise in every note.
      Color.clear.frame(height: 0)

    case .failed:
      // The judge is developer-run prototype infrastructure. Its absence must not turn a meeting
      // note into an error surface.
      Color.clear.frame(height: 0)

    case .ready:
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "photo.on.rectangle.angled")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
          Text("What was on screen")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.secondary)
          Spacer()
        }
        SpineMomentsRow(
          moments: store.frames.map(\.moment),
          total: store.frames.count,
          onOpen: onOpen)
      }
    }
  }

  private func label(_ text: String) -> some View {
    Text(text)
      .inkStyle(.statusLabel, color: Ink.secondary)
  }
}
