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
//  Frames are server-persisted now (contract §9): both the banner inset and the strip's tiles
//  draw from `content_url`/`thumbnail_url`, signed for 60 minutes, not from local Rewind pixels.
//  Neither view retries a broken URL — an expired one reports back to the store, which re-fetches
//  the whole set (`MeetingScreenshotsStore.refreshPersistedSet()`) rather than the caller guessing
//  at a new URL of its own.
//

import OmiTheme
import SwiftUI

/// Owns the feature state only after the gate has admitted this branch. `ConversationDetailView`
/// renders its ordinary summary directly when the gate is off, so a build with the setting
/// disabled constructs no screenshot store, child view, or task.
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
        date: date,
        onContentUnavailable: { Task { await store.refreshPersistedSet() } })
    }
  }
}

struct MeetingNoteBanner: View {
  let frame: ConversationScreenFrame
  let title: String
  let date: Date
  /// The inset failed to load — most likely an expired signed URL. Called at most once.
  var onContentUnavailable: (() -> Void)?

  @State private var reportedUnavailable = false

  /// Below this the banner stacks instead of sitting the inset beside the title. A note pane can be
  /// dragged genuinely narrow, and a side-by-side layout there crops the title to a word and a half.
  private static let stackBelowWidth: CGFloat = 420

  /// The gradient's two stops. The server computes `ground` once, over the canonical bytes, at
  /// approval time (`ConversationScreenFrame.ground`) — both this client and web render from that
  /// shared value instead of each re-deriving it from pixels, so the two surfaces can never drift
  /// apart. `MeetingBannerPalette`'s on-device extraction stays in the tree and keeps its tests:
  /// it is still the right code for the pre-commit path, where a locally-selected candidate that
  /// has not been through adjudication yet has no server ground to give. This view only ever
  /// renders an already-persisted `ConversationScreenFrame`, though, so when `ground` is absent
  /// here it falls back straight to `MeetingBannerPalette.neutral` rather than re-extracting from
  /// (possibly stale, possibly re-encoded) thumbnail pixels and risking a colour the server and
  /// web never agreed to.
  private var gradientColors: [Color] {
    if let ground = frame.ground {
      let parsed = ground.stops.compactMap { Color(hex: $0) }
      if parsed.count == ground.stops.count, !parsed.isEmpty {
        return parsed
      }
    }
    return MeetingBannerPalette.neutral.stops.map {
      Color(hue: $0.hue, saturation: $0.saturation, brightness: $0.brightness)
    }
  }

  private var gradient: LinearGradient {
    LinearGradient(colors: gradientColors, startPoint: .topLeading, endPoint: .bottomTrailing)
  }

  var body: some View {
    GeometryReader { proxy in
      let stacked = proxy.size.width < Self.stackBelowWidth
      ZStack {
        gradient
        if stacked {
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            titleBlock
            inset(width: min(proxy.size.width - OmiSpacing.lg * 2, 260))
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(OmiSpacing.lg)
        } else {
          HStack(alignment: .center, spacing: OmiSpacing.lg) {
            titleBlock
              .frame(maxWidth: .infinity, alignment: .leading)
            // The spec's 25-35% of banner width, clamped so it neither shrinks to a stamp in a
            // narrow pane nor grows into the full-bleed treatment the measurement ruled out.
            inset(width: min(max(proxy.size.width * 0.30, 150), 260))
          }
          .padding(.horizontal, OmiSpacing.lg)
        }
      }
      .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
    .frame(height: bannerHeight)
    .frame(maxWidth: .infinity)
    .task(id: frame.id) { reportedUnavailable = false }
  }

  /// Tall enough for a two-line title over the inset when stacked.
  private var bannerHeight: CGFloat { 132 }

  private var titleBlock: some View {
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
  }

  /// The approved frame, never stretched, never blurred into a texture. At this size a screenshot
  /// reads as "here is the thing we were looking at", which is the only job it can actually do.
  /// Absent entirely — not a placeholder glyph — when the fetch has not landed or has failed: the
  /// gradient and the title alone are a complete banner, so a slow or expired inset costs nothing.
  ///
  /// Loaded declaratively via `AsyncImage` rather than a manual `URLSession` fetch into an
  /// `NSImage`: the gradient no longer needs the decoded pixels for anything (it reads
  /// `frame.ground` instead), so the only reason left to fetch this image at all is to display it,
  /// which SwiftUI already does — and doing it this way keeps a non-`Sendable` `NSImage`/`CGImage`
  /// from ever needing to cross an isolation boundary here.
  @ViewBuilder private func inset(width: CGFloat) -> some View {
    AsyncImage(url: URL(string: frame.thumbnailURL)) { phase in
      switch phase {
      case .success(let image):
        image
          .resizable()
          .aspectRatio(contentMode: .fill)
          .frame(width: width, height: width * 10 / 16)
          .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
          .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
              .strokeBorder(.white.opacity(0.28), lineWidth: 1)
          )
          .shadow(color: .black.opacity(0.28), radius: 10, y: 3)
          .accessibilityLabel(
            frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
      case .failure:
        Color.clear
          .onAppear { reportUnavailableOnce() }
      case .empty:
        Color.clear
      @unknown default:
        Color.clear
      }
    }
  }

  private func reportUnavailableOnce() {
    guard !reportedUnavailable else { return }
    reportedUnavailable = true
    onContentUnavailable?()
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
      MeetingNoteScreenshotsSection(store: store) { frame in
        expandedFrame = store.lightboxItem(for: frame.id)
      }
    }
    .screenFrameLightbox(
      item: $expandedFrame,
      onStep: { step in
        expandedFrame = store.lightboxItem(steppingFrom: expandedFrame?.id, by: step)
      },
      onDelete: { deletable in
        await store.deleteFrame(frameID: deletable.frameID)
        // The deleted frame (and any promoted banner) is only known after the refetch inside
        // `deleteFrame` completes, so close the sheet rather than keep pointing at stale state.
        expandedFrame = nil
      },
      onContentUnavailable: { Task { await store.refreshPersistedSet() } }
    )
    .frame(maxWidth: .infinity, alignment: .leading)
    .task(id: conversation.id) {
      store.load(
        conversationID: conversation.id,
        start: date,
        end: conversation.finishedAt ?? date.addingTimeInterval(3600))
    }
  }
}

struct MeetingNoteScreenshotsSection: View {
  @ObservedObject var store: MeetingScreenshotsStore
  let onOpen: (ConversationScreenFrame) -> Void

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
      // Deliberately silent. A meeting with no screen capture, or none of it approved, is the
      // normal case, and an empty state announcing it is noise in every note.
      Color.clear.frame(height: 0)

    case .failed:
      // No network, a 4xx/5xx, a timeout, an unprovisioned backend — all of it must not turn a
      // meeting note into an error surface.
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
        MeetingScreenshotStripRow(frames: store.frames, onOpen: onOpen)
      }
    }
  }

  private func label(_ text: String) -> some View {
    Text(text)
      .inkStyle(.statusLabel, color: Ink.secondary)
  }
}

// MARK: - Strip row

/// The persisted strip, drawn from signed thumbnail URLs. Same shape as the Activity spine's
/// `SpineMomentsRow` (same tile size, same edge fade) — reusing `SpineStripFade`/`SpineMetrics`
/// directly rather than duplicating the layout math, but built on `ConversationScreenFrame`
/// instead of a local `SpineMoment` because there is no local pixel store behind these tiles.
struct MeetingScreenshotStripRow: View {
  let frames: [ConversationScreenFrame]
  let onOpen: (ConversationScreenFrame) -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 9) {
        ForEach(frames) { frame in
          MeetingScreenshotTile(frame: frame, onOpen: { onOpen(frame) })
        }
      }
      .padding(.vertical, 2)
      // The strip runs past the panel's edge, and a tile sliced off square reads as a layout
      // overflow rather than as "there is more this way".
      .padding(.trailing, SpineStripFade.width)
    }
    .mask(SpineStripFade())
  }
}

/// One strip tile. `AsyncImage` against the signed thumbnail URL; a load failure (most often an
/// expired URL) is treated the same as "not loaded yet" — a neutral placeholder, never a broken-
/// image glyph — because the surrounding row cannot itself refresh the set, only the caption tells
/// the story.
struct MeetingScreenshotTile: View {
  let frame: ConversationScreenFrame
  let onOpen: () -> Void

  @State private var isHovering = false

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 12, style: .continuous)
  }

  private var glyphName: String {
    switch frame.sourceBadge {
    case "code": return "chevron.left.forwardslash.chevron.right"
    case "browser": return "safari"
    case "document": return "doc.text"
    case "slides": return "rectangle.on.rectangle"
    case "product": return "app.badge"
    default: return "photo"
    }
  }

  var body: some View {
    Button(action: onOpen) {
      VStack(alignment: .leading, spacing: 5) {
        shape
          .fill(Ink.rowFill)
          .frame(width: SpineMetrics.thumbnailWidth, height: SpineMetrics.thumbnailHeight)
          .overlay {
            AsyncImage(url: URL(string: frame.thumbnailURL)) { phase in
              switch phase {
              case .success(let image):
                image
                  .resizable()
                  .aspectRatio(contentMode: .fill)
                  .frame(width: SpineMetrics.thumbnailWidth, height: SpineMetrics.thumbnailHeight)
                  .clipped()
              default:
                Image(systemName: glyphName)
                  .scaledFont(size: 20)
                  .foregroundColor(Ink.secondary)
              }
            }
          }
          .clipShape(shape)
          .overlay(shape.strokeBorder(isHovering ? Ink.hairline : Ink.separator, lineWidth: 1))
        Text(frame.caption.isEmpty ? "Screenshot" : frame.caption)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
          .truncationMode(.tail)
          .frame(width: SpineMetrics.thumbnailWidth, alignment: .leading)
      }
      .opacity(isHovering ? 0.86 : 1)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
    .accessibilityLabel(
      Text(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
    )
    .accessibilityHint(Text("Opens this screenshot"))
  }
}
