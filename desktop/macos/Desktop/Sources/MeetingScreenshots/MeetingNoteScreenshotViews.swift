//
//  MeetingNoteScreenshotViews.swift — the ground behind the title, and the strip.
//
//  **The banner is designed, not photographic, and that is a finding rather than a preference.**
//  Across five real meetings not one captured frame worked as a full-bleed article header: the
//  frames are Claude Code, Cursor, ChatGPT and GitHub, and a wide crop of a text-editing session
//  is a smear of grey. So the banner is a composition the app renders — a muted ground derived
//  from the chosen frame — and the screenshot is an ingredient in it rather than the surface of it.
//
//  **It is now the note header's background rather than a slot of its own, and that is a
//  correction.** As a slot it drew the conversation's title and date onto a gradient — a hundred
//  points below the header, which was already drawing the same title and the same date. Two
//  copies of one line, and 132pt of the pane spent on the second of them. Painting the ground
//  behind the header instead removes the duplicate, returns the vertical space, and leaves the
//  title where it always was: real, selectable, resizable chrome, never burned into pixels.
//
//  What that costs is honest to state. A header band is ~62pt tall, and the finding above says a
//  screenshot only earns its place when it is *legible*. At this height it cannot be, so the frame
//  bleeds in from the trailing edge as atmosphere and nothing more. The legible copy is the strip
//  tile directly below, which now opens into Quick Look at full resolution — so nothing was lost
//  that the reader could previously read.
//
//  Two consequences worth keeping through any refactor:
//
//  - **The store is owned above this file.** `ConversationDetailView` holds it, because the header
//    is its sibling rather than its child and both halves have to read the same banner. Nothing
//    here constructs one.
//  - **No banner is a first-class state.** A meeting whose frames are all dense text gets the
//    note's ordinary header and still gets its strip. Absence of a banner never suppresses the
//    strip; they are independent.
//
//  Frames are server-persisted (contract §9): both the header ground and the strip's tiles draw
//  from `content_url`/`thumbnail_url`, signed for 60 minutes, not from local Rewind pixels.
//  Neither view retries a broken URL — an expired one reports back to the store, which re-fetches
//  the whole set (`MeetingScreenshotsStore.refreshPersistedSet()`) rather than the caller guessing
//  at a new URL of its own.
//

import OmiTheme
import SwiftUI

/// The summary body, with the strip in its place among the note's other sections.
///
/// The store is passed in rather than created here: the note's header paints this conversation's
/// banner as its ground, and the header is this view's *sibling* — so one owner above both is the
/// only arrangement in which the two halves cannot disagree about which frame the banner is.
/// `ConversationDetailView` still renders its ordinary summary directly when the gate is off, so a
/// build with the setting disabled constructs no child view and starts no task.
struct MeetingNoteScreenshotsLayout<BeforeScreenshots: View, AfterScreenshots: View>: View {
  @ObservedObject var store: MeetingScreenshotsStore

  let conversation: ServerConversation
  let date: Date
  let beforeScreenshots: BeforeScreenshots
  let afterScreenshots: AfterScreenshots

  init(
    store: MeetingScreenshotsStore,
    conversation: ServerConversation,
    date: Date,
    @ViewBuilder beforeScreenshots: () -> BeforeScreenshots,
    @ViewBuilder afterScreenshots: () -> AfterScreenshots
  ) {
    self.store = store
    self.conversation = conversation
    self.date = date
    self.beforeScreenshots = beforeScreenshots()
    self.afterScreenshots = afterScreenshots()
  }

  var body: some View {
    beforeScreenshots
    MeetingNoteScreenshotStrip(store: store, conversation: conversation, date: date)
    afterScreenshots
  }
}

// MARK: - The ground behind the note header, and the frame on it

/// This conversation's banner ground, painted behind `ConversationDetailView`'s header.
///
/// Background only — it draws no text and no picture. The title, date, emoji, back chip and every
/// action button are the header's own real chrome, in front of it; the frame itself is
/// `MeetingNoteHeaderInset`, a discrete element in the header's own layout.
///
/// **Those are two views because one of them could not be both.** The first attempt put the frame
/// *in* this ground, behind the chrome, and the two requirements it had to satisfy are mutually
/// exclusive: the shell is light-pinned (`InkGlass.appearance` is `.aqua`, so `Ink.primary` is
/// near-black in every window) and approved frames are routinely near-black too, because most of
/// them are dark-mode editors — so the veil that keeps the title and the five action buttons
/// legible over a black screenshot is, necessarily, a veil that erases the screenshot. Measured on
/// a real note, at the strength the header needs it reads as a plain grey gradient and nothing
/// else. A picture with chrome on top of it is not a picture. So the ground is a wash, and the
/// frame gets a place of its own where nothing is written over it.
struct MeetingNoteHeaderBanner: View {
  let frame: ConversationScreenFrame

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

  var body: some View {
    ZStack {
      LinearGradient(colors: gradientColors, startPoint: .leading, endPoint: .trailing)
        .opacity(0.30)
      // The veil, and its floor is set by the worst case rather than the pretty one: white at 0.38
      // over a black ground resolves to about #616161, against which near-black `Ink.primary`
      // measures roughly 3.4:1 and `Ink.secondary` about 3:1 — both short of 4.5:1. At 0.58 the
      // same ground resolves to about #949494 and `Ink.primary` clears 5:1.
      LinearGradient(
        colors: [
          Color.white.opacity(0.72),
          Color.white.opacity(0.62),
          Color.white.opacity(0.58),
        ],
        startPoint: .leading,
        endPoint: .trailing)
    }
    .allowsHitTesting(false)
    .accessibilityHidden(true)
  }
}

/// The chosen frame, in the note header, at a size where it is actually a picture.
///
/// Sharp, unveiled, and given room of its own between the title block and the action buttons —
/// which is the whole difference between this and the wash it replaced. It sets the header band's
/// height, so a note with a banner gets a slightly taller header and a note without one is exactly
/// as it was.
///
/// Deliberately the same proportion and treatment as a strip tile below it: this is the same
/// picture, and two different croppings of one frame on one screen reads as two frames.
///
/// Absent entirely — not a placeholder glyph — when the fetch has not landed or has failed. The
/// ground alone is a complete header background, so a slow or expired image costs nothing but its
/// own absence.
///
/// Loaded declaratively via `AsyncImage` rather than a manual `URLSession` fetch into an
/// `NSImage`: the gradient does not need the decoded pixels for anything (it reads `frame.ground`
/// instead), so the only reason left to fetch this image is to display it, which SwiftUI already
/// does — and doing it this way keeps a non-`Sendable` `NSImage`/`CGImage` from ever needing to
/// cross an isolation boundary here.
struct MeetingNoteHeaderInset: View {
  let frame: ConversationScreenFrame
  /// Open this frame full size. Same gesture as a strip tile, because it is the same picture.
  var onOpen: (() -> Void)?
  /// The image failed to load — most likely an expired signed URL. Called at most once.
  var onContentUnavailable: (() -> Void)?

  @State private var reportedUnavailable = false
  @State private var isHovering = false

  static let height: CGFloat = 64
  private static var width: CGFloat { height * 16 / 10 }

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 8, style: .continuous)
  }

  var body: some View {
    AsyncImage(url: URL(string: frame.thumbnailURL)) { phase in
      switch phase {
      case .success(let image):
        Button(action: { onOpen?() }) {
          image
            .resizable()
            .aspectRatio(contentMode: .fill)
            .frame(width: Self.width, height: Self.height)
            .clipShape(shape)
            .overlay(shape.strokeBorder(isHovering ? Ink.hairline : Ink.separator, lineWidth: 1))
            .shadow(color: .black.opacity(0.14), radius: 6, y: 2)
            .opacity(isHovering ? 0.86 : 1)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
        .accessibilityLabel(
          Text(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
        )
        .accessibilityHint(Text("Opens this screenshot in Quick Look"))
      case .failure:
        Color.clear
          .frame(width: Self.width, height: Self.height)
          .onAppear { reportUnavailableOnce() }
      default:
        Color.clear
          .frame(width: Self.width, height: Self.height)
      }
    }
    .task(id: frame.id) { reportedUnavailable = false }
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

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      MeetingNoteScreenshotsSection(
        store: store,
        onOpen: { frame in
          // The whole set, not the one tile: Quick Look's own left/right stepping walks what it
          // was handed, which is what replaced the stepper this view used to own.
          //
          // `refreshing` is the expired-signed-URL path the deleted lightbox owned as
          // `onContentUnavailable`. A frame's pixels are signed for 60 minutes, so a note left
          // open across lunch has nothing but dead links in it, and without this a click on one
          // would open Quick Look on "no preview" and stay that way however many times it was
          // clicked, because nothing would ever ask the server for fresh URLs.
          ScreenFrameQuickLook.shared.present(
            store.quickLookFrames,
            startingAt: frame.id,
            refreshing: {
              await store.refreshPersistedSet()
              return store.quickLookFrames
            })
        },
        onDelete: { frame in await store.deleteFrame(frameID: frame.id) })
    }
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
  let onDelete: (ConversationScreenFrame) async -> Void

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
        MeetingScreenshotStripRow(frames: store.frames, onOpen: onOpen, onDelete: onDelete)
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
  let onDelete: (ConversationScreenFrame) async -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 9) {
        ForEach(frames) { frame in
          MeetingScreenshotTile(
            frame: frame,
            onOpen: { onOpen(frame) },
            onDelete: { await onDelete(frame) })
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
  /// Removes this frame from the note, server-side. Reached by right-click rather than by a button
  /// inside the viewer: the viewer is Quick Look now, its chrome is Apple's, and a tile's context
  /// menu is where the Finder puts exactly this command anyway.
  let onDelete: () async -> Void

  @State private var isHovering = false
  @State private var isConfirmingDelete = false
  @State private var isDeleting = false

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
    .contextMenu {
      Button("Quick Look", action: onOpen)
      Divider()
      Button("Delete Screenshot…", role: .destructive) { isConfirmingDelete = true }
        .disabled(isDeleting)
    }
    .alert("Delete Screenshot", isPresented: $isConfirmingDelete) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        isDeleting = true
        Task {
          await onDelete()
          isDeleting = false
        }
      }
    } message: {
      Text("This removes the screenshot from this meeting's note. This cannot be undone.")
    }
    .accessibilityLabel(
      Text(frame.caption.isEmpty ? "Screenshot from this meeting" : frame.caption)
    )
    .accessibilityHint(Text("Opens this screenshot in Quick Look"))
  }
}
