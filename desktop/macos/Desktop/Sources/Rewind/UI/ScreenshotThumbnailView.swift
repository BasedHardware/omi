@preconcurrency import AppKit
@preconcurrency import Foundation
import OmiTheme
@preconcurrency import SwiftUI

/// Thumbnail view for a single screenshot in the grid
struct ScreenshotThumbnailView: View {
  let screenshot: Screenshot
  let isSelected: Bool
  let searchQuery: String?
  let onSelect: () -> Void
  let onDelete: () -> Void

  @State private var thumbnailImage: NSImage? = nil
  @State private var isHovered = false
  @State private var isLoading = true

  var body: some View {
    Button(action: onSelect) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        // Thumbnail image
        ZStack {
          if let image = thumbnailImage {
            Image(nsImage: image)
              .resizable()
              .aspectRatio(contentMode: .fill)
              .frame(height: 120)
              .clipped()
          } else if isLoading {
            Rectangle()
              .fill(OmiColors.backgroundTertiary)
              .frame(height: 120)
              .overlay {
                ProgressView()
                  .progressViewStyle(.circular)
                  .scaleEffect(0.8)
              }
          } else {
            Rectangle()
              .fill(OmiColors.backgroundTertiary)
              .frame(height: 120)
              .overlay {
                Image(systemName: "photo")
                  .scaledFont(size: 24)
                  .foregroundColor(OmiColors.textQuaternary)
              }
          }

          // Hover overlay with delete button
          if isHovered {
            Color.black.opacity(0.3)

            VStack {
              HStack {
                // App icon badge
                AppIconView(appName: screenshot.appName, size: 20)
                  .padding(OmiSpacing.xxs)
                  .background(Color.black.opacity(0.5))
                  .cornerRadius(OmiChrome.badgeRadius)

                Spacer()

                Button {
                  onDelete()
                } label: {
                  Image(systemName: "trash")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(.white)
                    .padding(OmiSpacing.xs)
                    .background(Color.red.opacity(0.8))
                    .clipShape(Circle())
                }
                .buttonStyle(.plain)
              }
              Spacer()

              // Time overlay at bottom
              HStack {
                Spacer()
                Text(screenshot.formattedTime)
                  .scaledFont(size: OmiType.caption, weight: .medium, design: .monospaced)
                  .foregroundColor(.white)
                  .padding(.horizontal, OmiSpacing.sm)
                  .padding(.vertical, OmiSpacing.xxs)
                  .background(Color.black.opacity(0.6))
                  .cornerRadius(OmiChrome.stripRadius)
              }
            }
            .padding(OmiSpacing.xs)
          }

          // Search match indicator
          if searchQuery != nil && screenshot.ocrDataJson != nil {
            VStack {
              HStack {
                Spacer()
                Image(systemName: "text.magnifyingglass")
                  .scaledFont(size: OmiType.micro)
                  .foregroundColor(OmiColors.backgroundPrimary)
                  .padding(OmiSpacing.xxs)
                  .background(OmiColors.accent)
                  .clipShape(Circle())
              }
              Spacer()
            }
            .padding(OmiSpacing.xs)
          }
        }
        .frame(height: 120)
        .cornerRadius(OmiChrome.elementRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
            .stroke(isSelected ? OmiColors.accent : Color.clear, lineWidth: 2)
        )

        // Info section
        HStack(spacing: OmiSpacing.sm) {
          // App icon
          AppIconView(appName: screenshot.appName, size: 16)

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            // App name
            Text(screenshot.appName)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .lineLimit(1)

            // Time
            Text(screenshot.formattedTime)
              .scaledFont(size: OmiType.micro, design: .monospaced)
              .foregroundColor(OmiColors.textTertiary)
          }

          Spacer()

          // OCR indicator
          if screenshot.isIndexed && screenshot.ocrText != nil && !screenshot.ocrText!.isEmpty {
            Image(systemName: "doc.text.fill")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(OmiColors.accent.opacity(0.6))
              .help("Text extracted")
          }
        }

        // Search context snippet (when searching)
        if let query = searchQuery,
          let snippet = screenshot.contextSnippet(for: query)
        {
          SearchContextSnippet(snippet: snippet, query: query)
        }

        // Window title (if available and no search context)
        else if let title = screenshot.windowTitle, !title.isEmpty {
          Text(title)
            .scaledFont(size: OmiType.micro)
            .foregroundColor(OmiColors.textQuaternary)
            .lineLimit(1)
        }
      }
      .padding(OmiSpacing.sm)
      .background(isSelected ? OmiColors.accent.opacity(0.1) : OmiColors.backgroundTertiary.opacity(0.5))
      .cornerRadius(OmiChrome.smallControlRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .stroke(isSelected ? OmiColors.accent.opacity(0.3) : Color.clear, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
      if hovering {
        NSCursor.pointingHand.push()
      } else {
        NSCursor.pop()
      }
    }
    .task {
      await loadThumbnail()
    }
  }

  private func loadThumbnail() async {
    isLoading = true
    do {
      let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
      // Create thumbnail
      let thumbnailSize = NSSize(width: 300, height: 200)
      thumbnailImage = resizeImage(image, to: thumbnailSize)
    } catch {
      logError("ScreenshotThumbnailView: Failed to load thumbnail: \(error)")
    }
    isLoading = false
  }

  private func resizeImage(_ image: NSImage, to size: NSSize) -> NSImage {
    let newImage = NSImage(size: size)
    newImage.lockFocus()
    image.draw(
      in: NSRect(origin: .zero, size: size),
      from: NSRect(origin: .zero, size: image.size),
      operation: .copy,
      fraction: 1.0
    )
    newImage.unlockFocus()
    return newImage
  }
}

/// Displays a search context snippet with the query highlighted
struct SearchContextSnippet: View {
  let snippet: String
  let query: String

  var body: some View {
    Text(attributedSnippet)
      .scaledFont(size: OmiType.micro)
      .lineLimit(2)
      .padding(.horizontal, OmiSpacing.xs)
      .padding(.vertical, OmiSpacing.xxs)
      .background(OmiColors.accent.opacity(0.1))
      .cornerRadius(OmiChrome.stripRadius)
  }

  private var attributedSnippet: AttributedString {
    var result = AttributedString(snippet)
    result.foregroundColor = OmiColors.textTertiary

    // Highlight the search query
    let lowercasedSnippet = snippet.lowercased()
    let lowercasedQuery = query.lowercased()

    var searchStart = lowercasedSnippet.startIndex
    while let range = lowercasedSnippet.range(of: lowercasedQuery, range: searchStart..<lowercasedSnippet.endIndex) {
      if let attrRange = Range(range, in: result) {
        result[attrRange].foregroundColor = OmiColors.accent
        result[attrRange].font = .system(size: 10, weight: .semibold)
      }
      searchStart = range.upperBound
    }

    return result
  }
}

/// Grid view showing multiple screenshot thumbnails
struct ScreenshotGridView: View {
  let screenshots: [Screenshot]
  let selectedScreenshot: Screenshot?
  let searchQuery: String?
  let onSelect: (Screenshot) -> Void
  let onDelete: (Screenshot) -> Void

  @State private var groupByApp = false

  private let columns = [
    GridItem(.adaptive(minimum: 180, maximum: 250), spacing: OmiSpacing.md)
  ]

  var body: some View {
    VStack(spacing: 0) {
      // View controls
      HStack {
        Text("\(screenshots.count) screenshots")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)

        if let query = searchQuery {
          Text("matching \"\(query)\"")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.accent)
        }

        Spacer()

        // Group toggle
        Toggle(isOn: $groupByApp) {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: groupByApp ? "square.grid.3x3.fill" : "square.grid.3x3")
            Text("Group by app")
          }
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)
        }
        .toggleStyle(.button)
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.bottom, OmiSpacing.md)

      // Grid
      ScrollView {
        if groupByApp {
          groupedGridContent
        } else {
          standardGridContent
        }
      }
    }
  }

  private var standardGridContent: some View {
    LazyVGrid(columns: columns, spacing: OmiSpacing.md) {
      ForEach(screenshots) { screenshot in
        ScreenshotThumbnailView(
          screenshot: screenshot,
          isSelected: selectedScreenshot?.id == screenshot.id,
          searchQuery: searchQuery,
          onSelect: { onSelect(screenshot) },
          onDelete: { onDelete(screenshot) }
        )
      }
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.bottom, OmiSpacing.xxl)
  }

  private var groupedGridContent: some View {
    let grouped = Dictionary(grouping: screenshots) { $0.appName }
    let sortedKeys = grouped.keys.sorted()

    return LazyVStack(alignment: .leading, spacing: OmiSpacing.xxl) {
      ForEach(sortedKeys, id: \.self) { appName in
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
          // App header
          HStack(spacing: OmiSpacing.sm) {
            AppIconView(appName: appName, size: 20)

            Text(appName)
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text("(\(grouped[appName]?.count ?? 0))")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)

            Spacer()
          }
          .padding(.horizontal, OmiSpacing.xxl)

          // Screenshots for this app
          LazyVGrid(columns: columns, spacing: OmiSpacing.md) {
            ForEach(grouped[appName] ?? []) { screenshot in
              ScreenshotThumbnailView(
                screenshot: screenshot,
                isSelected: selectedScreenshot?.id == screenshot.id,
                searchQuery: searchQuery,
                onSelect: { onSelect(screenshot) },
                onDelete: { onDelete(screenshot) }
              )
            }
          }
          .padding(.horizontal, OmiSpacing.xxl)
        }
      }
    }
    .padding(.bottom, OmiSpacing.xxl)
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    ScreenshotGridView(
      screenshots: [],
      selectedScreenshot: nil,
      searchQuery: nil,
      onSelect: { _ in },
      onDelete: { _ in }
    )
    .frame(width: 800, height: 600)
    .background(OmiColors.backgroundPrimary)
  }
#endif
