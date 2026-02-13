import SwiftUI
import AppKit

/// Enhanced timeline scrubber view with app icons, time markers, and scroll support
struct RewindTimelineView: View {
    let screenshots: [Screenshot]
    @Binding var selectedScreenshot: Screenshot?
    let onSelect: (Screenshot) -> Void

    @State private var hoveredIndex: Int? = nil
    @State private var hoverLocation: CGPoint = .zero
    @State private var containerWidth: CGFloat = 0

    private let timelineHeight: CGFloat = 60
    private let appIconSize: CGFloat = 24
    private let markerWidth: CGFloat = 3

    var body: some View {
        VStack(spacing: 0) {
            // App icons row (showing unique apps in timeline)
            appIconsBar

            // Timeline scrubber with scroll support
            GeometryReader { geometry in
                let width = geometry.size.width

                ZStack(alignment: .leading) {
                    // Background
                    RoundedRectangle(cornerRadius: 4)
                        .fill(OmiColors.backgroundTertiary.opacity(0.5))

                    // Activity markers
                    activityMarkers(width: width)

                    // Current position indicator
                    if let selected = selectedScreenshot,
                       let index = screenshots.firstIndex(where: { $0.id == selected.id }) {
                        let position = positionForIndex(index, width: width)
                        Rectangle()
                            .fill(OmiColors.purplePrimary)
                            .frame(width: 2, height: timelineHeight - 16)
                            .position(x: position, y: (timelineHeight - 8) / 2)
                    }

                    // Hover indicator
                    if let hoverIndex = hoveredIndex {
                        let position = positionForIndex(hoverIndex, width: width)

                        VStack(spacing: 4) {
                            // Hover preview tooltip
                            if let screenshot = screenshots[safe: hoverIndex] {
                                HoverPreviewTooltip(screenshot: screenshot)
                                    .offset(y: -80)
                            }

                            Rectangle()
                                .fill(Color.white.opacity(0.6))
                                .frame(width: 1, height: timelineHeight - 20)
                        }
                        .position(x: position, y: (timelineHeight - 8) / 2)
                    }
                }
                .frame(height: timelineHeight - 8)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            let index = indexForPosition(value.location.x, width: width)
                            hoveredIndex = index
                            if let screenshot = screenshots[safe: index] {
                                onSelect(screenshot)
                            }
                        }
                        .onEnded { _ in
                            hoveredIndex = nil
                        }
                )
                .onContinuousHover { phase in
                    switch phase {
                    case .active(let location):
                        let index = indexForPosition(location.x, width: width)
                        hoveredIndex = index
                    case .ended:
                        hoveredIndex = nil
                    }
                }
                .onAppear {
                    containerWidth = width
                }
            }
            .frame(height: timelineHeight - 8)
            .padding(.horizontal, 16)

            // Time labels
            timeLabels
        }
        .frame(height: timelineHeight + 50)
        .background(
            OmiColors.backgroundSecondary.opacity(0.95)
                .background(.ultraThinMaterial)
        )
        // Scroll wheel handler for timeline navigation
        .onScrollWheelGesture { delta in
            handleScrollWheel(delta: delta)
        }
    }

    // MARK: - Scroll Wheel Handler

    private func handleScrollWheel(delta: CGFloat) {
        guard !screenshots.isEmpty else { return }

        // Find current index
        let currentIndex: Int
        if let selected = selectedScreenshot,
           let index = screenshots.firstIndex(where: { $0.id == selected.id }) {
            currentIndex = index
        } else {
            currentIndex = 0
        }

        // Calculate new index based on scroll direction
        // Scroll down (negative delta) = go to earlier screenshots (higher index)
        // Scroll up (positive delta) = go to newer screenshots (lower index)
        let scrollSensitivity = 3 // How many screenshots to skip per scroll unit
        let indexDelta = Int(-delta * CGFloat(scrollSensitivity))
        let newIndex = max(0, min(screenshots.count - 1, currentIndex + indexDelta))

        if newIndex != currentIndex {
            onSelect(screenshots[newIndex])
        }
    }

    // MARK: - App Icons Bar

    private var appIconsBar: some View {
        let uniqueApps = getUniqueAppsInOrder()

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(uniqueApps, id: \.self) { appName in
                    AppIconButton(
                        appName: appName,
                        isActive: selectedScreenshot?.appName == appName,
                        onTap: {
                            // Jump to first screenshot of this app
                            if let screenshot = screenshots.first(where: { $0.appName == appName }) {
                                onSelect(screenshot)
                            }
                        }
                    )
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
    }

    // MARK: - Activity Markers

    private func activityMarkers(width: CGFloat) -> some View {
        Canvas { context, size in
            guard !screenshots.isEmpty else { return }

            let markerSpacing = max(1, width / CGFloat(screenshots.count))

            for (index, screenshot) in screenshots.enumerated() {
                let x = CGFloat(index) * markerSpacing
                let color = colorForApp(screenshot.appName)

                let rect = CGRect(
                    x: x,
                    y: 4,
                    width: max(markerSpacing - 0.5, 1),
                    height: size.height - 8
                )

                context.fill(Path(rect), with: .color(color.opacity(0.7)))
            }
        }
    }

    // MARK: - Time Labels

    private var timeLabels: some View {
        HStack {
            if let oldest = screenshots.last {
                Text(oldest.formattedTime)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()

            if let selected = selectedScreenshot {
                VStack(spacing: 2) {
                    Text(selected.formattedTime)
                        .font(.system(size: 12, weight: .semibold, design: .monospaced))
                        .foregroundColor(OmiColors.textPrimary)

                    Text(selected.appName)
                        .font(.system(size: 10))
                        .foregroundColor(OmiColors.textSecondary)
                }
            }

            Spacer()

            if let newest = screenshots.first {
                Text(newest.formattedTime)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }

    // MARK: - Helpers

    private func getUniqueAppsInOrder() -> [String] {
        var seen = Set<String>()
        var result: [String] = []

        for screenshot in screenshots {
            if !seen.contains(screenshot.appName) {
                seen.insert(screenshot.appName)
                result.append(screenshot.appName)
            }
        }

        return result
    }

    private func positionForIndex(_ index: Int, width: CGFloat) -> CGFloat {
        guard screenshots.count > 1 else { return width / 2 }
        let spacing = width / CGFloat(screenshots.count - 1)
        return CGFloat(index) * spacing
    }

    private func indexForPosition(_ x: CGFloat, width: CGFloat) -> Int {
        guard screenshots.count > 1 else { return 0 }
        let spacing = width / CGFloat(screenshots.count - 1)
        let index = Int(x / spacing)
        return max(0, min(screenshots.count - 1, index))
    }

    private func colorForApp(_ appName: String) -> Color {
        // Generate consistent color based on app name hash
        let hash = abs(appName.hashValue)
        let hue = Double(hash % 360) / 360.0
        return Color(hue: hue, saturation: 0.6, brightness: 0.8)
    }
}

// MARK: - Scroll Wheel Gesture Modifier

struct ScrollWheelGestureModifier: ViewModifier {
    let action: (CGFloat) -> Void

    func body(content: Content) -> some View {
        content.background(
            ScrollWheelView(action: action)
        )
    }
}

struct ScrollWheelView: NSViewRepresentable {
    let action: (CGFloat) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = ScrollWheelNSView()
        view.action = action
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? ScrollWheelNSView)?.action = action
    }
}

class ScrollWheelNSView: NSView {
    var action: ((CGFloat) -> Void)?

    override func scrollWheel(with event: NSEvent) {
        // Use deltaY for vertical scroll
        let delta = event.deltaY
        if abs(delta) > 0.1 {
            action?(delta)
        }
    }
}

extension View {
    func onScrollWheelGesture(action: @escaping (CGFloat) -> Void) -> some View {
        modifier(ScrollWheelGestureModifier(action: action))
    }
}

/// App icon button for the timeline bar
struct AppIconButton: View {
    let appName: String
    let isActive: Bool
    let onTap: () -> Void

    @State private var isHovered = false

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 4) {
                AppIconView(appName: appName, size: 24)
                    .opacity(isActive ? 1.0 : 0.6)

                // Active indicator dot
                Circle()
                    .fill(isActive ? OmiColors.purplePrimary : Color.clear)
                    .frame(width: 4, height: 4)
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 4)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isHovered ? OmiColors.backgroundTertiary : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovered = hovering
        }
        .help(appName)
    }
}

/// Hover preview tooltip showing screenshot thumbnail
struct HoverPreviewTooltip: View {
    let screenshot: Screenshot

    @State private var thumbnailImage: NSImage? = nil

    var body: some View {
        VStack(spacing: 4) {
            // Thumbnail
            Group {
                if let image = thumbnailImage {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: 160, height: 100)
                        .clipped()
                } else {
                    Rectangle()
                        .fill(OmiColors.backgroundTertiary)
                        .frame(width: 160, height: 100)
                }
            }
            .cornerRadius(6)

            // Info
            VStack(spacing: 2) {
                Text(screenshot.formattedTime)
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
                    .foregroundColor(OmiColors.textPrimary)

                Text(screenshot.appName)
                    .font(.system(size: 10))
                    .foregroundColor(OmiColors.textSecondary)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.backgroundSecondary)
                .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
        )
        .task {
            await loadThumbnail()
        }
    }

    private func loadThumbnail() async {
        do {
            let fullImage = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
            let thumbnailSize = NSSize(width: 320, height: 200)
            thumbnailImage = resizeImage(fullImage, to: thumbnailSize)
        } catch {
            // Silently fail
        }
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

/// Full-size screenshot preview view with search highlighting
struct ScreenshotPreviewView: View {
    let screenshot: Screenshot
    let searchQuery: String?
    let onPrevious: () -> Void
    let onNext: () -> Void
    let onClose: () -> Void

    @State private var fullImage: NSImage? = nil
    @State private var imageSize: CGSize = .zero
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                // App icon and info
                HStack(spacing: 10) {
                    AppIconView(appName: screenshot.appName, size: 24)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(screenshot.appName)
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(OmiColors.textPrimary)

                        if let title = screenshot.windowTitle, !title.isEmpty {
                            Text(title)
                                .font(.system(size: 12))
                                .foregroundColor(OmiColors.textSecondary)
                                .lineLimit(1)
                        }
                    }
                }

                Spacer()

                // Search match info
                if let query = searchQuery {
                    let matchCount = screenshot.matchingBlocks(for: query).count
                    if matchCount > 0 {
                        HStack(spacing: 4) {
                            Image(systemName: "text.magnifyingglass")
                                .font(.system(size: 11))
                            Text("\(matchCount) match\(matchCount == 1 ? "" : "es")")
                                .font(.system(size: 11))
                        }
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(OmiColors.purplePrimary.opacity(0.15))
                        .cornerRadius(4)
                    }
                }

                // Time
                Text(screenshot.formattedDate)
                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                    .foregroundColor(OmiColors.textSecondary)

                // Keyboard hints
                HStack(spacing: 12) {
                    keyboardHint("←", label: "Prev")
                    keyboardHint("→", label: "Next")
                    keyboardHint("esc", label: "Close")
                }
                .padding(.leading, 16)

                // Close button
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(OmiColors.backgroundTertiary)
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(OmiColors.backgroundSecondary.opacity(0.95))

            // Image with highlight overlays
            GeometryReader { geometry in
                ZStack {
                    if let image = fullImage {
                        Image(nsImage: image)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .background(
                                GeometryReader { imageGeometry in
                                    Color.clear.preference(
                                        key: ImageSizePreferenceKey.self,
                                        value: imageGeometry.size
                                    )
                                }
                            )
                            .overlay {
                                // Search highlight overlays
                                if let query = searchQuery {
                                    SearchHighlightOverlay(
                                        screenshot: screenshot,
                                        query: query,
                                        imageSize: imageSize,
                                        containerSize: geometry.size
                                    )
                                }
                            }
                    } else if isLoading {
                        ProgressView()
                            .progressViewStyle(.circular)
                    } else {
                        Image(systemName: "photo")
                            .font(.system(size: 48))
                            .foregroundColor(OmiColors.textQuaternary)
                    }

                    // Navigation arrows
                    HStack {
                        navButton(systemName: "chevron.left", action: onPrevious)
                        Spacer()
                        navButton(systemName: "chevron.right", action: onNext)
                    }
                    .padding(.horizontal, 16)
                }
                .onPreferenceChange(ImageSizePreferenceKey.self) { size in
                    imageSize = size
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black.opacity(0.4))

            // OCR text preview (if available)
            if let ocrText = screenshot.ocrText, !ocrText.isEmpty {
                ocrTextSection(ocrText)
            }
        }
        .task {
            await loadFullImage()
        }
    }

    private func keyboardHint(_ key: String, label: String) -> some View {
        HStack(spacing: 4) {
            Text(key)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(4)

            Text(label)
                .font(.system(size: 10))
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func navButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
                .frame(width: 40, height: 40)
                .background(Color.black.opacity(0.5))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
    }

    private func ocrTextSection(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "doc.text.viewfinder")
                    .font(.system(size: 12))
                    .foregroundColor(OmiColors.textTertiary)

                Text("Extracted Text")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(text, forType: .string)
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "doc.on.doc")
                        Text("Copy")
                    }
                    .font(.system(size: 11))
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                // Highlight search query in text if present
                if let query = searchQuery {
                    Text(highlightedText(text, query: query))
                        .font(.system(size: 11))
                        .textSelection(.enabled)
                        .if_available_writingToolsNone()
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text(text)
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textSecondary)
                        .textSelection(.enabled)
                        .if_available_writingToolsNone()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .frame(maxHeight: 100)
        }
        .padding(12)
        .background(OmiColors.backgroundTertiary.opacity(0.8))
    }

    private func highlightedText(_ text: String, query: String) -> AttributedString {
        var result = AttributedString(text)
        result.foregroundColor = OmiColors.textSecondary

        let lowercasedText = text.lowercased()
        let lowercasedQuery = query.lowercased()

        var searchStart = lowercasedText.startIndex
        while let range = lowercasedText.range(of: lowercasedQuery, range: searchStart..<lowercasedText.endIndex) {
            if let attrRange = Range(range, in: result) {
                result[attrRange].foregroundColor = OmiColors.purplePrimary
                result[attrRange].backgroundColor = OmiColors.purplePrimary.opacity(0.2)
                result[attrRange].font = .system(size: 11, weight: .semibold)
            }
            searchStart = range.upperBound
        }

        return result
    }

    private func loadFullImage() async {
        isLoading = true
        do {
            let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
            fullImage = image
        } catch {
            logError("ScreenshotPreviewView: Failed to load image: \(error)")
        }
        isLoading = false
    }
}

// MARK: - Image Size Preference Key

struct ImageSizePreferenceKey: PreferenceKey {
    static var defaultValue: CGSize = .zero
    static func reduce(value: inout CGSize, nextValue: () -> CGSize) {
        value = nextValue()
    }
}

// MARK: - Search Highlight Overlay

struct SearchHighlightOverlay: View {
    let screenshot: Screenshot
    let query: String
    let imageSize: CGSize
    let containerSize: CGSize

    private var displayedSizeAndOffset: (size: CGSize, offset: CGSize) {
        let aspectRatio = imageSize.width / max(imageSize.height, 1)
        let containerAspect = containerSize.width / max(containerSize.height, 1)

        if aspectRatio > containerAspect {
            // Image is wider - fits width
            let displayedWidth = containerSize.width
            let displayedHeight = displayedWidth / aspectRatio
            return (
                size: CGSize(width: displayedWidth, height: displayedHeight),
                offset: CGSize(width: 0, height: (containerSize.height - displayedHeight) / 2)
            )
        } else {
            // Image is taller - fits height
            let displayedHeight = containerSize.height
            let displayedWidth = displayedHeight * aspectRatio
            return (
                size: CGSize(width: displayedWidth, height: displayedHeight),
                offset: CGSize(width: (containerSize.width - displayedWidth) / 2, height: 0)
            )
        }
    }

    var body: some View {
        let matchingBlocks = screenshot.matchingBlocks(for: query)
        let layout = displayedSizeAndOffset

        ZStack {
            ForEach(Array(matchingBlocks.enumerated()), id: \.offset) { _, block in
                let screenRect = block.screenRect(for: CGSize(width: 1, height: 1)) // Normalized

                Rectangle()
                    .stroke(OmiColors.purplePrimary, lineWidth: 2)
                    .background(OmiColors.purplePrimary.opacity(0.2))
                    .frame(
                        width: screenRect.width * layout.size.width,
                        height: screenRect.height * layout.size.height
                    )
                    .position(
                        x: layout.offset.width + screenRect.midX * layout.size.width,
                        y: layout.offset.height + screenRect.midY * layout.size.height
                    )
            }
        }
    }
}

// MARK: - Safe Array Access Extension

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
