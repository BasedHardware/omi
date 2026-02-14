import SwiftUI
import AppKit

/// Horizontally scrollable filmstrip of search result thumbnails
struct SearchResultsFilmstrip: View {
    let screenshots: [Screenshot]
    let searchQuery: String?
    @Binding var selectedIndex: Int
    let onSelect: (Int) -> Void

    @State private var thumbnailCache: [Int64: NSImage] = [:]
    @State private var thumbnailAccessOrder: [Int64] = []  // Track access order for LRU eviction
    @State private var loadingIds: Set<Int64> = []
    @State private var scrollProxy: ScrollViewProxy?

    private let thumbnailWidth: CGFloat = 160
    private let thumbnailHeight: CGFloat = 100
    private let spacing: CGFloat = 12
    private let maxCachedThumbnails = 50  // Limit cache to prevent memory bloat

    var body: some View {
        VStack(spacing: 0) {
            // Header with result count
            HStack {
                if let query = searchQuery {
                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.purplePrimary)

                        Text("\(screenshots.count) results for \"\(query)\"")
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(.white)
                    }
                }

                Spacer()

                // Navigation hint
                Text("← scroll or use arrow keys →")
                    .scaledFont(size: 11)
                    .foregroundColor(.white.opacity(0.4))

                // Keyboard shortcuts
                HStack(spacing: 8) {
                    keyHint("←", action: "Prev")
                    keyHint("→", action: "Next")
                }
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)

            // Filmstrip
            ScrollViewReader { proxy in
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: spacing) {
                        ForEach(Array(screenshots.enumerated()), id: \.element.id) { index, screenshot in
                            FilmstripThumbnail(
                                screenshot: screenshot,
                                searchQuery: searchQuery,
                                isSelected: index == selectedIndex,
                                thumbnail: screenshot.id.flatMap { thumbnailCache[$0] },
                                isLoading: screenshot.id.map { loadingIds.contains($0) } ?? false
                            ) {
                                onSelect(index)
                            }
                            .id(index)
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 8)
                }
                .onAppear {
                    scrollProxy = proxy
                }
                .onChange(of: selectedIndex) { _, newIndex in
                    withAnimation(.easeInOut(duration: 0.2)) {
                        proxy.scrollTo(newIndex, anchor: .center)
                    }
                }
            }
            .frame(height: thumbnailHeight + 60) // Extra space for labels and selection ring

            // Progress indicator showing position in results
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    // Track
                    Capsule()
                        .fill(Color.white.opacity(0.1))
                        .frame(height: 4)

                    // Progress
                    Capsule()
                        .fill(OmiColors.purplePrimary)
                        .frame(
                            width: max(20, geometry.size.width * progressWidth),
                            height: 4
                        )
                        .offset(x: geometry.size.width * progressOffset)
                }
            }
            .frame(height: 4)
            .padding(.horizontal, 20)
            .padding(.bottom, 12)
        }
        .background(Color.black.opacity(0.9))
        .task {
            await loadVisibleThumbnails()
        }
        .onChange(of: screenshots) { _, _ in
            thumbnailCache.removeAll()
            Task { await loadVisibleThumbnails() }
        }
    }

    private var progressWidth: CGFloat {
        guard screenshots.count > 1 else { return 1.0 }
        return 1.0 / CGFloat(screenshots.count) * 3 // Show ~3 items worth
    }

    private var progressOffset: CGFloat {
        guard screenshots.count > 1 else { return 0 }
        let progress = CGFloat(selectedIndex) / CGFloat(screenshots.count - 1)
        return progress * (1.0 - progressWidth)
    }

    private func keyHint(_ key: String, action: String) -> some View {
        HStack(spacing: 3) {
            Text(key)
                .scaledFont(size: 10, weight: .medium, design: .monospaced)
                .foregroundColor(.white.opacity(0.7))
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(Color.white.opacity(0.15))
                .cornerRadius(3)

            Text(action)
                .scaledFont(size: 10)
                .foregroundColor(.white.opacity(0.4))
        }
    }

    private func loadVisibleThumbnails() async {
        // Load thumbnails for first batch
        let batchSize = 20
        let startIndex = max(0, selectedIndex - batchSize / 2)
        let endIndex = min(screenshots.count, startIndex + batchSize)

        for index in startIndex..<endIndex {
            let screenshot = screenshots[index]
            guard let screenshotId = screenshot.id,
                  thumbnailCache[screenshotId] == nil,
                  !loadingIds.contains(screenshotId) else { continue }

            loadingIds.insert(screenshotId)

            do {
                let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
                let thumbnail = await createThumbnail(from: image)

                await MainActor.run {
                    cacheThumbnail(thumbnail, for: screenshotId)
                    loadingIds.remove(screenshotId)
                }
            } catch {
                await MainActor.run {
                    _ = loadingIds.remove(screenshotId)
                }
            }
        }
    }

    /// Cache a thumbnail with LRU eviction
    private func cacheThumbnail(_ thumbnail: NSImage, for screenshotId: Int64) {
        // Add to cache
        thumbnailCache[screenshotId] = thumbnail

        // Update access order (move to end = most recently used)
        if let existingIndex = thumbnailAccessOrder.firstIndex(of: screenshotId) {
            thumbnailAccessOrder.remove(at: existingIndex)
        }
        thumbnailAccessOrder.append(screenshotId)

        // Evict oldest entries if cache is too large
        while thumbnailCache.count > maxCachedThumbnails {
            if let oldestId = thumbnailAccessOrder.first {
                thumbnailAccessOrder.removeFirst()
                thumbnailCache.removeValue(forKey: oldestId)
            } else {
                break
            }
        }
    }

    private func createThumbnail(from image: NSImage) async -> NSImage {
        let targetSize = NSSize(width: thumbnailWidth * 2, height: thumbnailHeight * 2) // 2x for retina

        let newImage = NSImage(size: targetSize)
        newImage.lockFocus()

        image.draw(
            in: NSRect(origin: .zero, size: targetSize),
            from: NSRect(origin: .zero, size: image.size),
            operation: .copy,
            fraction: 1.0
        )

        newImage.unlockFocus()
        return newImage
    }
}

// MARK: - Filmstrip Thumbnail

struct FilmstripThumbnail: View {
    let screenshot: Screenshot
    let searchQuery: String?
    let isSelected: Bool
    let thumbnail: NSImage?
    let isLoading: Bool
    let onTap: () -> Void

    @State private var isHovered = false

    private let width: CGFloat = 160
    private let height: CGFloat = 100

    // Screenpipe-style hover: scale up and lift
    private var hoverScale: CGFloat { isHovered ? 1.15 : 1.0 }
    private var liftOffset: CGFloat { isHovered ? -16 : 0 }

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 6) {
                // Thumbnail container
                ZStack {
                    // Thumbnail or placeholder
                    Group {
                        if let image = thumbnail {
                            Image(nsImage: image)
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        } else if isLoading {
                            Rectangle()
                                .fill(Color.white.opacity(0.05))
                                .overlay(
                                    ProgressView()
                                        .progressViewStyle(.circular)
                                        .scaleEffect(0.6)
                                        .tint(.white.opacity(0.5))
                                )
                        } else {
                            Rectangle()
                                .fill(Color.white.opacity(0.05))
                                .overlay(
                                    Image(systemName: "photo")
                                        .scaledFont(size: 20)
                                        .foregroundColor(.white.opacity(0.2))
                                )
                        }
                    }
                    .frame(width: width, height: height)
                    .clipped()

                    // Match indicator badge with glow
                    if let query = searchQuery,
                       let matchCount = screenshot.matchCount(for: query),
                       matchCount > 0 {
                        VStack {
                            HStack {
                                Spacer()
                                Text("\(matchCount)")
                                    .scaledFont(size: 10, weight: .bold)
                                    .foregroundColor(.black)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.yellow)
                                    .cornerRadius(4)
                                    .shadow(color: Color.yellow.opacity(0.5), radius: 4)
                                    .padding(6)
                            }
                            Spacer()
                        }
                    }

                    // App icon overlay with background
                    VStack {
                        Spacer()
                        HStack {
                            AppIconView(appName: screenshot.appName, size: 18)
                                .background(
                                    Circle()
                                        .fill(Color.black.opacity(0.5))
                                        .blur(radius: 4)
                                )
                                .padding(6)
                            Spacer()
                        }
                    }
                }
                .frame(width: width, height: height)
                .cornerRadius(isHovered ? 12 : 8)
                .overlay(
                    RoundedRectangle(cornerRadius: isHovered ? 12 : 8)
                        .stroke(
                            isSelected ? OmiColors.purplePrimary :
                            (isHovered ? Color.white.opacity(0.6) : Color.white.opacity(0.15)),
                            lineWidth: isSelected ? 3 : (isHovered ? 2 : 1)
                        )
                )
                // Selected glow
                .shadow(
                    color: isSelected ? OmiColors.purplePrimary.opacity(0.5) : .clear,
                    radius: isSelected ? 12 : 0
                )
                // Hover glow
                .shadow(
                    color: isHovered && !isSelected ? Color.white.opacity(0.15) : .clear,
                    radius: isHovered ? 8 : 0
                )
                // Screenpipe-style scale and lift
                .scaleEffect(hoverScale)
                .offset(y: liftOffset)
                .zIndex(isHovered ? 100 : (isSelected ? 50 : 0))

                // Time label
                Text(screenshot.formattedTime)
                    .scaledFont(size: 11, weight: isSelected ? .semibold : .regular, design: .monospaced)
                    .foregroundColor(isSelected ? OmiColors.purplePrimary : .white.opacity(0.7))
                    .offset(y: liftOffset / 2)

                // App name (shows on hover or selection)
                if isSelected || isHovered {
                    Text(screenshot.appName)
                        .scaledFont(size: 10, weight: .medium)
                        .foregroundColor(.white.opacity(0.6))
                        .lineLimit(1)
                        .offset(y: liftOffset / 2)
                        .transition(.opacity.combined(with: .scale(scale: 0.9)))
                }
            }
            // Spring animation like Screenpipe (stiffness: 300, damping: 30)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelected)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isHovered)
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
    }
}

// MARK: - Screenshot Extension for Match Count

extension Screenshot {
    func matchCount(for query: String) -> Int? {
        guard let ocrText = ocrText else { return nil }
        let lowercased = ocrText.lowercased()
        let queryLower = query.lowercased()

        var count = 0
        var searchRange = lowercased.startIndex..<lowercased.endIndex

        while let range = lowercased.range(of: queryLower, range: searchRange) {
            count += 1
            searchRange = range.upperBound..<lowercased.endIndex
        }

        return count > 0 ? count : nil
    }
}

#Preview {
    SearchResultsFilmstrip(
        screenshots: [],
        searchQuery: "test",
        selectedIndex: .constant(0),
        onSelect: { _ in }
    )
    .frame(width: 800, height: 200)
    .background(Color.black)
}
