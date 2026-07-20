import AppKit
import OmiTheme
import SwiftUI

/// "Today in Rewind" — a slim filmstrip of sampled frames from today's screen
/// capture. The deepest hands-on desktop feature gets a presence on Home;
/// clicking a frame opens Rewind at that moment. Hidden entirely when today
/// has no frames (no empty shell).
struct HomeRewindFilmstrip: View {
  let screenshots: [Screenshot]
  let onOpen: (Screenshot?) -> Void

  var body: some View {
    if !screenshots.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        HStack {
          Text("Today in Rewind")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .kerning(1.1)
            .textCase(.uppercase)
            .foregroundStyle(HomeStagePalette.muted)

          Spacer()

          Button {
            onOpen(nil)
          } label: {
            Text("Open Rewind →")
              .scaledFont(size: OmiType.micro, weight: .semibold)
              .foregroundStyle(HomeStagePalette.secondary)
          }
          .buttonStyle(.plain)
        }

        HStack(spacing: OmiSpacing.xs) {
          ForEach(screenshots, id: \.id) { screenshot in
            HomeFilmstripFrame(screenshot: screenshot) {
              onOpen(screenshot)
            }
          }
        }
        .frame(height: Self.frameHeight)
      }
      .accessibilityIdentifier("home-rewind-filmstrip")
    }
  }

  static let frameHeight: CGFloat = 58
}

private struct HomeFilmstripFrame: View {
  let screenshot: Screenshot
  let onTap: () -> Void

  @State private var thumbnail: NSImage?
  @State private var isHovering = false

  private static let timeFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "H:mm"
    return formatter
  }()

  var body: some View {
    Button(action: onTap) {
      ZStack(alignment: .bottomLeading) {
        Group {
          if let thumbnail {
            Image(nsImage: thumbnail)
              .resizable()
              .aspectRatio(contentMode: .fill)
          } else {
            HomeStagePalette.tile
          }
        }
        .frame(maxWidth: .infinity)
        .frame(height: HomeRewindFilmstrip.frameHeight)
        .clipped()

        Text(Self.timeFormatter.string(from: screenshot.timestamp))
          .scaledFont(size: 9, weight: .semibold)
          .foregroundStyle(Color.white.opacity(0.85))
          .padding(.horizontal, 4)
          .padding(.vertical, 2)
          .background(Color.black.opacity(0.45))
          .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
          .padding(4)
      }
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .stroke(
            isHovering ? HomeStagePalette.secondary.opacity(0.5) : HomeStagePalette.hairline,
            lineWidth: 1
          )
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .task(id: screenshot.id) {
      await loadThumbnail()
    }
  }

  private func loadThumbnail() async {
    guard thumbnail == nil else { return }
    do {
      let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
      guard !Task.isCancelled else { return }
      thumbnail = Self.downscale(image, maxHeight: HomeRewindFilmstrip.frameHeight * 2)
    } catch {
      // Pruned frames are expected occasionally; keep the neutral tile but
      // leave a trace for diagnosis.
      log("HomeFilmstrip: thumbnail load failed for frame \(screenshot.id ?? -1): \(error)")
    }
  }

  private static func downscale(_ image: NSImage, maxHeight: CGFloat) -> NSImage {
    let size = image.size
    guard size.height > maxHeight, size.height > 0 else { return image }
    let scale = maxHeight / size.height
    let target = NSSize(width: size.width * scale, height: maxHeight)
    let resized = NSImage(size: target)
    resized.lockFocus()
    image.draw(
      in: NSRect(origin: .zero, size: target),
      from: NSRect(origin: .zero, size: size),
      operation: .copy,
      fraction: 1.0
    )
    resized.unlockFocus()
    return resized
  }
}
