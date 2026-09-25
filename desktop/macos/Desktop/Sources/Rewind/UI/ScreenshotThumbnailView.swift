//
//  ScreenshotThumbnailView.swift — one result card, the well it is built around, and the one decoder
//  the grid loads its pictures through.
//
//  **One shape, two contents.** Every card is the same size and carries the same three parts (a well,
//  a title, a source line), so a grid row is never ragged and `RewindSearchLayout.cardHeight` keeps
//  describing every card in it. What differs is what is *in* the well — a photograph, or the words
//  the frame matched on when its picture is gone. A picture and a run of type are not mistakable for
//  each other at a glance, which is why this needs no badge and no legend.
//
//  **And it is a control.** A search result you cannot open is half a feature: the whole reason to
//  find the moment you were looking at something is to go and look at it. The hit state is drawn
//  *outside* the card's own bounds so pressing one never changes the grid's geometry by a point.
//

@preconcurrency import AppKit
import OmiTheme
import SwiftUI

// MARK: - The decoder

/// The one place the results grid turns a screenshot into a picture.
///
/// A grid of thumbnails is the hot path of this whole surface, and two things make it stutter:
/// decoding the full-resolution screenshot behind a 231 pt card, and decoding it again every time a
/// row scrolls out of view and back. This fixes both — it asks `RewindStorage` for a *downsampled*
/// image at the size the card actually draws, and it keeps what it decoded.
///
/// **The decode runs off the main thread.** `RewindStorage.loadScreenshotThumbnail` is `@MainActor`,
/// so its ImageIO step lands on the main thread and every cell that appears mid-scroll pays for it in
/// dropped frames. `downsampledImage` is `nonisolated` and pure, so this calls the actor only for the
/// bytes and does the decode on a background task.
///
/// Carries one decoded image back from that task. `NSImage` is a mutable AppKit class old enough to
/// predate `Sendable` and cannot conform, so the hand-off is boxed rather than bare. It is safe
/// because the image is built inside the detached task and read exactly once on the way out — the
/// two isolation domains never hold it at the same time.
private struct ThumbnailBox: @unchecked Sendable {
  let image: NSImage?
}

@MainActor
final class RewindThumbnailLoader {
  static let shared = RewindThumbnailLoader()

  /// Longest edge asked of the decoder. A card is `cardWidth` (≈231 pt) across and Retina draws it at
  /// 2×, so 480 px is the size the picture is actually shown at. Asking for more than the file holds
  /// costs nothing — `kCGImageSourceThumbnailMaxPixelSize` is a ceiling, not a target.
  static let maxPixelSize = Int(
    (RewindSearchLayout.cardWidth(panelWidth: ChatComposerLayout.contentLaneMaxWidth) * 2).rounded())

  /// Roughly 60 decoded cards. A 480 px thumbnail is ~1.2 MB decoded, so this is ~72 MB — enough that
  /// scrolling a page of results and coming back is free, and bounded so a long session cannot grow
  /// without limit. `NSCache` also drops it all under memory pressure, which a dictionary would not.
  private let cache: NSCache<NSNumber, NSImage> = {
    let cache = NSCache<NSNumber, NSImage>()
    cache.countLimit = 60
    return cache
  }()

  private init() {}

  /// What is already decoded, answered synchronously.
  ///
  /// Checked before the card ever shows its placeholder: a cell that scrolls back into view has its
  /// picture on the very first frame, so a fast scroll does not flash grey wells behind it.
  func cached(_ screenshot: Screenshot) -> NSImage? {
    guard let id = screenshot.id else { return nil }
    return cache.object(forKey: NSNumber(value: id))
  }

  /// Decode this screenshot's thumbnail, or hand back what was already decoded.
  func thumbnail(for screenshot: Screenshot) async -> NSImage? {
    if let cached = cached(screenshot) { return cached }
    let size = Self.maxPixelSize
    do {
      let data = try await RewindStorage.shared.loadScreenshotData(for: screenshot)
      // The expensive half, off the main thread. `downsampledImage` touches no actor state.
      //
      // `NSImage` predates `Sendable` and cannot conform, so the decoded image comes back in a box
      // rather than bare: the value is constructed inside the detached task and read once here, so
      // no two isolation domains ever hold it at the same time.
      let boxed = await Task.detached(priority: .utility) {
        ThumbnailBox(image: RewindStorage.downsampledImage(from: data, maxPixelSize: size))
      }.value
      guard let image = boxed.image else { return nil }
      if let id = screenshot.id {
        cache.setObject(image, forKey: NSNumber(value: id))
      }
      return image
    } catch {
      // A frame whose file retention already removed is a real and common state, not an error worth
      // logging on every scroll. The card draws what the frame said instead.
      return nil
    }
  }
}

// MARK: - The well

/// The card's picture, or the words that stand in for it.
///
/// Both forms are built here, from the same shape, aspect ratio, clip and edge, so they are the same
/// object at the same size and neither can drift into being taller than the other. That identity is
/// what lets `RewindSearchLayout.cardHeight` describe a card without knowing which kind it is.
struct RewindSearchWell: View {
  let screenshot: Screenshot
  /// What the frame said, for the state where there is no picture to show it.
  var fallbackText: String?

  @State private var image: NSImage?

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: RewindSearchLayout.cardCornerRadius, style: .continuous)
  }

  var body: some View {
    shape
      .fill(image == nil && fallbackText?.isEmpty == false ? RewindSearchInk.textWell : RewindSearchInk.wellPlaceholder)
      .aspectRatio(RewindSearchLayout.thumbnailAspect, contentMode: .fit)
      .overlay { content }
      .clipShape(shape)
      .overlay(shape.strokeBorder(Ink.hairline.opacity(0.5), lineWidth: 1))
      .task(id: screenshot.id) {
        // Synchronous hit first, so a cached picture never costs a frame of placeholder.
        if let cached = RewindThumbnailLoader.shared.cached(screenshot) {
          image = cached
          return
        }
        image = await RewindThumbnailLoader.shared.thumbnail(for: screenshot)
      }
  }

  @ViewBuilder
  private var content: some View {
    if let image {
      Image(nsImage: image)
        .resizable()
        // Fill and clip: a screenshot letterboxed inside a 4:3 well leaves two grey bars, and a grid
        // of those reads as broken images.
        .aspectRatio(contentMode: .fill)
        .clipped()
    } else if let fallbackText, !fallbackText.isEmpty {
      // The no-picture state, when the frame still knows what was on it. The text is the honest
      // substitute for the picture — same well, same size, nothing invented.
      VStack(alignment: .leading, spacing: 5) {
        Image(systemName: "text.alignleft")
          .font(.system(size: 11, weight: .semibold))
          .foregroundStyle(Ink.secondary)
        Text(fallbackText)
          .inkStyle(.statusLabel, color: Ink.primary)
          .lineLimit(4)
          .truncationMode(.tail)
          .multilineTextAlignment(.leading)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(10)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    } else {
      // …and the no-picture, no-text state, which is still a real one. A neutral well with a quiet
      // glyph is honest; nothing here is ever a broken-image icon.
      Image(systemName: "photo")
        .font(.system(size: 18, weight: .light))
        .foregroundStyle(Ink.secondary)
    }
  }
}

// MARK: - The card

/// One thing the search found: a moment on screen, as a picture with a title and a source under it.
struct RewindSearchResultCard: View {
  let group: SearchResultGroup
  let query: String
  var panelWidth: CGFloat = RewindSearchLayout.panelWidth
  /// Whether the keyboard is on this card. Drawn as weight, never as hue.
  var isSelected: Bool = false
  var onOpen: () -> Void = {}

  @State private var isHovering = false

  /// The front of a window title is the part that says what it is; when there is none, the app is the
  /// most specific true thing the card can be called.
  private var title: String {
    guard let windowTitle = group.windowTitle, !windowTitle.isEmpty else { return group.appName }
    return windowTitle
  }

  private var snippet: String? { group.representativeScreenshot.contextSnippet(for: query) }

  var body: some View {
    Button(action: onOpen) {
      content
    }
    .buttonStyle(RewindSearchCardStyle(isHovering: isHovering, isSelected: isSelected))
    .onHover { isHovering = $0 }
    .omiAnimation(.easeOut(duration: InkMotion.press), value: isHovering)
    // The matched text, whole, for the two readers a 231 pt card cannot serve: somebody hovering to
    // check *why* this frame came back, and somebody who cannot see the picture at all.
    .help(snippet ?? title)
    // Clicking the card opens the group on the timeline, which is what someone searching usually
    // wants — the moment in its context, scrubable. Quick Look is the other thing they might want,
    // reading the frame itself, and a right-click is where a second action on a tile belongs.
    .contextMenu {
      Button("Quick Look") {
        let frames = group.screenshots.map { QuickLookFrame(screenshot: $0) }
        guard let first = frames.first else { return }
        ScreenFrameQuickLook.shared.present(frames, startingAt: first.id)
      }
      Divider()
      Button("Open on Timeline", action: onOpen)
    }
    .accessibilityLabel(Text(readAloud))
    .accessibilityHint(Text(Self.activationHint))
    .accessibilityAddTraits(isSelected ? [.isSelected] : [])
  }

  static let activationHint = "Opens the timeline at this moment"

  private var content: some View {
    VStack(alignment: .leading, spacing: 7) {
      RewindSearchWell(screenshot: group.representativeScreenshot, fallbackText: snippet)
      Text(title)
        // One line, always. `.tail` and not the default middle truncation.
        .inkStyle(.rowCopy, color: Ink.primary)
        .lineLimit(1)
        .truncationMode(.tail)
      HStack(spacing: 5) {
        AppIconView(appName: group.appName, size: 12)
        Text(group.appName)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
          .truncationMode(.tail)
          .layoutPriority(1)
        Text("•").inkStyle(.statusLabel, color: Ink.secondary)
        Text(RewindSearchTime.describe(group.startTime))
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
          .fixedSize()
      }
    }
    .frame(width: RewindSearchLayout.cardWidth(panelWidth: panelWidth), alignment: .leading)
  }

  /// The card read aloud. The snippet is left out because the title and source already name the card;
  /// a page of OCR read after every one would make the grid unusable with VoiceOver.
  private var readAloud: String {
    let when = RewindSearchTime.describe(group.startTime)
    let frames = group.count > 1 ? ", \(group.count) frames" : ""
    return "\(title), \(group.appName)\(frames), \(when)"
  }
}

/// How a result card answers the pointer: a wash behind it on hover, a stronger one with an edge when
/// the keyboard is on it, and a dip in opacity while it is held.
///
/// **The affordance is drawn outside the card's own bounds, and that is deliberate.** A card is a
/// picture, a title and a source line with no padding of its own — insetting them to make room for a
/// highlight would change `RewindSearchLayout.cardHeight`, which the panel's ceiling and its scroll
/// fade are both stated in terms of. A `background` is layout-neutral, and the negative padding lets
/// the wash spread into the gutter the grid already leaves between cards. So the card gains a hit
/// state without the grid moving by a point.
private struct RewindSearchCardStyle: ButtonStyle {
  let isHovering: Bool
  let isSelected: Bool

  /// A shade larger than the card's own corner, because the wash sits outside it: two concentric
  /// rounded rectangles with the *same* radius read as a rendering seam rather than as one object.
  private static let cornerRadius = RewindSearchLayout.cardCornerRadius + 4
  /// How far the wash spreads past the card. Half the grid's gutter, so two selected neighbours could
  /// never touch.
  private static let outset: CGFloat = RewindSearchLayout.cardGutter / 2

  func makeBody(configuration: Configuration) -> some View {
    let shape = RoundedRectangle(cornerRadius: Self.cornerRadius, style: .continuous)
    let fill: Color = {
      if isSelected { return RewindSearchInk.chipFillSelected }
      return isHovering || configuration.isPressed ? RewindSearchInk.chipFillHover : .clear
    }()
    return
      configuration.label
      // Pressed drops opacity rather than scaling: a card is a picture of something real, and a
      // photograph that shrinks under the finger reads as a toy.
      .opacity(configuration.isPressed ? 0.72 : 1)
      .background(
        shape
          .fill(fill)
          .overlay(shape.strokeBorder(isSelected ? Ink.hairline : Color.clear, lineWidth: 1))
          .padding(-Self.outset)
      )
      // The whole card is the target, including the air between the picture and the caption — a
      // control with holes in it is a control that ignores half its clicks.
      .contentShape(Rectangle())
      .omiAnimation(.easeOut(duration: InkMotion.press), value: configuration.isPressed)
  }
}

// MARK: - When

/// How a card says when it was.
///
/// A pure function of two dates so the phrasing is a test rather than a screenshot. Relative for
/// anything inside a day, because "3 hours ago" is the question a person actually asks of their own
/// screen history; a clock time for anything older, because "at 5:49 PM" without a day is a lie.
enum RewindSearchTime {
  static func describe(_ date: Date, now: Date = Date()) -> String {
    let seconds = now.timeIntervalSince(date)
    if seconds < 60 { return "just now" }
    if seconds < 3600 { return "\(Int(seconds / 60))m ago" }
    if seconds < 86_400 { return "\(Int(seconds / 3600))h ago" }

    let calendar = Calendar.current
    let formatter = DateFormatter()
    if calendar.isDateInYesterday(date) {
      formatter.dateFormat = "'yesterday' h:mm a"
    } else if calendar.isDate(date, equalTo: now, toGranularity: .year) {
      formatter.dateFormat = "MMM d, h:mm a"
    } else {
      formatter.dateFormat = "MMM d, yyyy"
    }
    return formatter.string(from: date)
  }
}
