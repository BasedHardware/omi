import SwiftUI
import AppKit

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
            VStack(alignment: .leading, spacing: 8) {
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
                                    .font(.system(size: 24))
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
                                    .padding(4)
                                    .background(Color.black.opacity(0.5))
                                    .cornerRadius(6)

                                Spacer()

                                Button {
                                    onDelete()
                                } label: {
                                    Image(systemName: "trash")
                                        .font(.system(size: 12))
                                        .foregroundColor(.white)
                                        .padding(6)
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
                                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(Color.black.opacity(0.6))
                                    .cornerRadius(4)
                            }
                        }
                        .padding(6)
                    }

                    // Search match indicator
                    if searchQuery != nil && screenshot.ocrDataJson != nil {
                        VStack {
                            HStack {
                                Spacer()
                                Image(systemName: "text.magnifyingglass")
                                    .font(.system(size: 10))
                                    .foregroundColor(.white)
                                    .padding(4)
                                    .background(OmiColors.purplePrimary)
                                    .clipShape(Circle())
                            }
                            Spacer()
                        }
                        .padding(6)
                    }
                }
                .frame(height: 120)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? OmiColors.purplePrimary : Color.clear, lineWidth: 2)
                )

                // Info section
                HStack(spacing: 8) {
                    // App icon
                    AppIconView(appName: screenshot.appName, size: 16)

                    VStack(alignment: .leading, spacing: 2) {
                        // App name
                        Text(screenshot.appName)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                            .lineLimit(1)

                        // Time
                        Text(screenshot.formattedTime)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer()

                    // OCR indicator
                    if screenshot.isIndexed && screenshot.ocrText != nil && !screenshot.ocrText!.isEmpty {
                        Image(systemName: "doc.text.fill")
                            .font(.system(size: 10))
                            .foregroundColor(OmiColors.purplePrimary.opacity(0.6))
                            .help("Text extracted")
                    }
                }

                // Search context snippet (when searching)
                if let query = searchQuery,
                   let snippet = screenshot.contextSnippet(for: query) {
                    SearchContextSnippet(snippet: snippet, query: query)
                }

                // Window title (if available and no search context)
                else if let title = screenshot.windowTitle, !title.isEmpty {
                    Text(title)
                        .font(.system(size: 10))
                        .foregroundColor(OmiColors.textQuaternary)
                        .lineLimit(1)
                }
            }
            .padding(8)
            .background(isSelected ? OmiColors.purplePrimary.opacity(0.1) : OmiColors.backgroundTertiary.opacity(0.5))
            .cornerRadius(10)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.3) : Color.clear, lineWidth: 1)
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
            .font(.system(size: 10))
            .lineLimit(2)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .background(OmiColors.purplePrimary.opacity(0.1))
            .cornerRadius(4)
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
                result[attrRange].foregroundColor = OmiColors.purplePrimary
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
        GridItem(.adaptive(minimum: 180, maximum: 250), spacing: 12)
    ]

    var body: some View {
        VStack(spacing: 0) {
            // View controls
            HStack {
                Text("\(screenshots.count) screenshots")
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textTertiary)

                if let query = searchQuery {
                    Text("matching \"\(query)\"")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.purplePrimary)
                }

                Spacer()

                // Group toggle
                Toggle(isOn: $groupByApp) {
                    HStack(spacing: 4) {
                        Image(systemName: groupByApp ? "square.grid.3x3.fill" : "square.grid.3x3")
                        Text("Group by app")
                    }
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textSecondary)
                }
                .toggleStyle(.button)
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 12)

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
        LazyVGrid(columns: columns, spacing: 12) {
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
        .padding(.horizontal, 24)
        .padding(.bottom, 24)
    }

    private var groupedGridContent: some View {
        let grouped = Dictionary(grouping: screenshots) { $0.appName }
        let sortedKeys = grouped.keys.sorted()

        return LazyVStack(alignment: .leading, spacing: 24) {
            ForEach(sortedKeys, id: \.self) { appName in
                VStack(alignment: .leading, spacing: 12) {
                    // App header
                    HStack(spacing: 8) {
                        AppIconView(appName: appName, size: 20)

                        Text(appName)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(OmiColors.textPrimary)

                        Text("(\(grouped[appName]?.count ?? 0))")
                            .font(.system(size: 12))
                            .foregroundColor(OmiColors.textTertiary)

                        Spacer()
                    }
                    .padding(.horizontal, 24)

                    // Screenshots for this app
                    LazyVGrid(columns: columns, spacing: 12) {
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
                    .padding(.horizontal, 24)
                }
            }
        }
        .padding(.bottom, 24)
    }
}

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
