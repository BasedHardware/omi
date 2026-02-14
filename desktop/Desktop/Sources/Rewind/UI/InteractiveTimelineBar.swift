import SwiftUI
import AppKit

/// Full-width timeline bar with time-based positioning and gap indicators
struct InteractiveTimelineBar: View {
    let screenshots: [Screenshot]
    let currentIndex: Int
    let searchResultIndices: Set<Int>?
    let onSelect: (Int) -> Void

    @State private var hoveredIndex: Int? = nil
    @State private var hoveredGapIndex: Int? = nil

    private let barHeight: CGFloat = 32

    var body: some View {
        // Full-width timeline with moving playhead
        TimeBasedTimelineView(
            screenshots: screenshots,
            currentIndex: currentIndex,
            searchResultIndices: searchResultIndices,
            hoveredIndex: $hoveredIndex,
            hoveredGapIndex: $hoveredGapIndex,
            barHeight: barHeight,
            onSelect: onSelect
        )
        .frame(height: barHeight + 40) // Space for tooltip
    }
}

// MARK: - Timeline Segment Model

/// Represents either a capture segment (with frames) or a gap (no frames)
struct TimelineSegment {
    let startIndex: Int      // First frame index in this segment (-1 for gaps)
    let endIndex: Int        // Last frame index in this segment (-1 for gaps)
    let startTime: Date
    let endTime: Date
    let isGap: Bool
    let gapDuration: TimeInterval  // Only for gaps

    var frameCount: Int {
        isGap ? 0 : (endIndex - startIndex + 1)
    }
}

// MARK: - Time-Based Timeline View

struct TimeBasedTimelineView: NSViewRepresentable {
    let screenshots: [Screenshot]
    let currentIndex: Int
    let searchResultIndices: Set<Int>?
    @Binding var hoveredIndex: Int?
    @Binding var hoveredGapIndex: Int?
    let barHeight: CGFloat
    let onSelect: (Int) -> Void

    func makeNSView(context: Context) -> TimeBasedTimelineNSView {
        let view = TimeBasedTimelineNSView()
        view.onSelect = onSelect
        view.onHover = { index in
            DispatchQueue.main.async {
                hoveredIndex = index
            }
        }
        view.onGapHover = { gapIndex in
            DispatchQueue.main.async {
                hoveredGapIndex = gapIndex
            }
        }
        return view
    }

    func updateNSView(_ nsView: TimeBasedTimelineNSView, context: Context) {
        nsView.screenshots = screenshots
        nsView.currentIndex = currentIndex
        nsView.searchResultIndices = searchResultIndices
        nsView.hoveredIndex = hoveredIndex
        nsView.hoveredGapIndex = hoveredGapIndex
        nsView.barHeight = barHeight
        nsView.onSelect = onSelect
        nsView.rebuildSegments()
        nsView.needsDisplay = true
    }
}

// MARK: - NSView Implementation

class TimeBasedTimelineNSView: NSView {
    var screenshots: [Screenshot] = []
    var currentIndex: Int = 0
    var searchResultIndices: Set<Int>?
    var hoveredIndex: Int?
    var hoveredGapIndex: Int?
    var barHeight: CGFloat = 32
    var onSelect: ((Int) -> Void)?
    var onHover: ((Int?) -> Void)?
    var onGapHover: ((Int?) -> Void)?

    // Computed layout
    private var segments: [TimelineSegment] = []
    private var segmentRects: [NSRect] = []  // Cached rects for each segment
    private var frameXPositions: [CGFloat] = []  // X position for each frame
    private var lastLayoutBounds: NSRect = .zero  // Track bounds changes

    // Gap threshold: 2 minutes
    private let gapThreshold: TimeInterval = 120
    // Minimum gap width in pixels
    private let minGapWidth: CGFloat = 30

    private var trackingArea: NSTrackingArea?
    private var tooltipWindow: NSWindow?

    override var isFlipped: Bool { true }

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        setupTrackingArea()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        setupTrackingArea()
    }

    private func setupTrackingArea() {
        let options: NSTrackingArea.Options = [.activeInActiveApp, .mouseMoved, .mouseEnteredAndExited, .inVisibleRect]
        trackingArea = NSTrackingArea(rect: bounds, options: options, owner: self, userInfo: nil)
        addTrackingArea(trackingArea!)
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let existing = trackingArea {
            removeTrackingArea(existing)
        }
        setupTrackingArea()
    }

    // MARK: - Segment Building

    private func needsLayoutRecalculation() -> Bool {
        // Recalculate if bounds have changed significantly
        let currentRect = timelineRect()
        return abs(currentRect.width - lastLayoutBounds.width) > 1 ||
               abs(currentRect.height - lastLayoutBounds.height) > 1 ||
               lastLayoutBounds.width < 10  // Initial layout
    }

    func rebuildSegments() {
        segments = []
        segmentRects = []
        frameXPositions = Array(repeating: 0, count: screenshots.count)

        guard screenshots.count > 1 else {
            if screenshots.count == 1 {
                frameXPositions = [timelineRect().midX]
            }
            return
        }

        // Build segments by detecting gaps
        var currentSegmentStart = 0

        for i in 1..<screenshots.count {
            let prevTime = screenshots[i-1].timestamp
            let currTime = screenshots[i].timestamp
            let timeDiff = currTime.timeIntervalSince(prevTime)

            if timeDiff > gapThreshold {
                // End current segment
                segments.append(TimelineSegment(
                    startIndex: currentSegmentStart,
                    endIndex: i - 1,
                    startTime: screenshots[currentSegmentStart].timestamp,
                    endTime: screenshots[i - 1].timestamp,
                    isGap: false,
                    gapDuration: 0
                ))

                // Add gap segment
                segments.append(TimelineSegment(
                    startIndex: -1,
                    endIndex: -1,
                    startTime: screenshots[i - 1].timestamp,
                    endTime: screenshots[i].timestamp,
                    isGap: true,
                    gapDuration: timeDiff
                ))

                currentSegmentStart = i
            }
        }

        // Add final segment
        segments.append(TimelineSegment(
            startIndex: currentSegmentStart,
            endIndex: screenshots.count - 1,
            startTime: screenshots[currentSegmentStart].timestamp,
            endTime: screenshots[screenshots.count - 1].timestamp,
            isGap: false,
            gapDuration: 0
        ))

        // Calculate layout
        calculateLayout()
    }

    private func calculateLayout() {
        let rect = timelineRect()
        segmentRects = []
        lastLayoutBounds = rect  // Track that we calculated with these bounds

        guard !segments.isEmpty else { return }

        // Calculate total "visual width" needed
        // - Frame segments: proportional to their duration
        // - Gap segments: fixed minimum width

        var totalFrameDuration: TimeInterval = 0
        var totalGapCount = 0

        for segment in segments {
            if segment.isGap {
                totalGapCount += 1
            } else {
                totalFrameDuration += segment.endTime.timeIntervalSince(segment.startTime)
            }
        }

        // Available width for frames (after subtracting gap widths)
        let totalGapWidth = CGFloat(totalGapCount) * minGapWidth
        let availableFrameWidth = max(rect.width - totalGapWidth, rect.width * 0.5)

        // Calculate x positions for each segment
        var currentX = rect.minX

        for segment in segments {
            if segment.isGap {
                let segmentRect = NSRect(x: currentX, y: rect.minY, width: minGapWidth, height: rect.height)
                segmentRects.append(segmentRect)
                currentX += minGapWidth
            } else {
                // Width proportional to duration
                let segmentDuration = segment.endTime.timeIntervalSince(segment.startTime)
                let widthRatio = totalFrameDuration > 0 ? segmentDuration / totalFrameDuration : 1.0
                let segmentWidth = max(20, availableFrameWidth * CGFloat(widthRatio))

                let segmentRect = NSRect(x: currentX, y: rect.minY, width: segmentWidth, height: rect.height)
                segmentRects.append(segmentRect)

                // Calculate frame positions within this segment
                let frameCount = segment.endIndex - segment.startIndex + 1
                for i in 0..<frameCount {
                    let frameIndex = segment.startIndex + i
                    let ratio = frameCount > 1 ? CGFloat(i) / CGFloat(frameCount - 1) : 0.5
                    frameXPositions[frameIndex] = currentX + ratio * segmentWidth
                }

                currentX += segmentWidth
            }
        }
    }

    // MARK: - Mouse Handling

    override func mouseDown(with event: NSEvent) {
        let location = convert(event.locationInWindow, from: nil)
        let rect = timelineRect()

        if let index = indexAtPoint(location) {
            log("TimelineBar: Click at \(location) resolved to index \(index) of \(screenshots.count)")
            onSelect?(index)
        } else {
            log("TimelineBar: Click at \(location) not in timeline rect \(rect), bounds=\(bounds), screenshots=\(screenshots.count)")
        }
    }

    override func mouseMoved(with event: NSEvent) {
        let location = convert(event.locationInWindow, from: nil)

        // Check if hovering over a gap
        if let gapIndex = gapAtPoint(location) {
            hoveredIndex = nil
            hoveredGapIndex = gapIndex
            onHover?(nil)
            onGapHover?(gapIndex)
            showGapTooltip(for: segments[gapIndex], at: location)
        } else if let index = indexAtPoint(location) {
            hoveredIndex = index
            hoveredGapIndex = nil
            onHover?(index)
            onGapHover?(nil)
            showTooltip(for: screenshots[index], at: location)
        } else {
            hoveredIndex = nil
            hoveredGapIndex = nil
            onHover?(nil)
            onGapHover?(nil)
            hideTooltip()
        }
        needsDisplay = true
    }

    override func mouseExited(with event: NSEvent) {
        hoveredIndex = nil
        hoveredGapIndex = nil
        onHover?(nil)
        onGapHover?(nil)
        hideTooltip()
        needsDisplay = true
    }

    private func indexAtPoint(_ point: CGPoint) -> Int? {
        let rect = timelineRect()
        guard rect.contains(point), !screenshots.isEmpty else { return nil }

        // Ensure layout is calculated
        if frameXPositions.isEmpty || needsLayoutRecalculation() {
            rebuildSegments()
        }

        // If we still have no positions or all positions are 0, use linear fallback
        if frameXPositions.isEmpty || (frameXPositions.count > 1 && frameXPositions.allSatisfy { $0 == 0 }) {
            // Linear fallback (like the old implementation)
            let relativeX = point.x - rect.minX
            let ratio = relativeX / rect.width
            let index = Int(ratio * CGFloat(screenshots.count))
            return max(0, min(screenshots.count - 1, index))
        }

        // Find closest frame to this x position
        var closestIndex = 0
        var closestDistance = CGFloat.infinity

        for (index, x) in frameXPositions.enumerated() {
            let distance = abs(point.x - x)
            if distance < closestDistance {
                closestDistance = distance
                closestIndex = index
            }
        }

        return closestIndex
    }

    private func gapAtPoint(_ point: CGPoint) -> Int? {
        for (index, segment) in segments.enumerated() {
            if segment.isGap && index < segmentRects.count {
                if segmentRects[index].contains(point) {
                    return index
                }
            }
        }
        return nil
    }

    private func timelineRect() -> NSRect {
        let padding: CGFloat = 20
        let bottomY = bounds.height - barHeight - 8
        return NSRect(x: padding, y: bottomY, width: bounds.width - padding * 2, height: barHeight)
    }

    private func xPositionForIndex(_ index: Int) -> CGFloat {
        guard index >= 0 && index < frameXPositions.count else {
            return timelineRect().midX
        }
        return frameXPositions[index]
    }

    // MARK: - Tooltips

    private func showTooltip(for screenshot: Screenshot, at point: CGPoint) {
        hideTooltip()

        let tooltipView = NSHostingView(rootView: TooltipView(screenshot: screenshot).withFontScaling())
        tooltipView.frame.size = tooltipView.fittingSize

        let windowPoint = convert(point, to: nil)
        guard let screenPoint = window?.convertPoint(toScreen: windowPoint) else { return }

        let tooltipWindow = NSWindow(
            contentRect: NSRect(x: screenPoint.x - tooltipView.frame.width / 2,
                              y: screenPoint.y + 20,
                              width: tooltipView.frame.width,
                              height: tooltipView.frame.height),
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )
        tooltipWindow.backgroundColor = .clear
        tooltipWindow.isOpaque = false
        tooltipWindow.level = .floating
        tooltipWindow.contentView = tooltipView
        tooltipWindow.orderFront(nil)
        self.tooltipWindow = tooltipWindow
    }

    private func showGapTooltip(for segment: TimelineSegment, at point: CGPoint) {
        hideTooltip()

        let tooltipView = NSHostingView(rootView: GapTooltipView(duration: segment.gapDuration).withFontScaling())
        tooltipView.frame.size = tooltipView.fittingSize

        let windowPoint = convert(point, to: nil)
        guard let screenPoint = window?.convertPoint(toScreen: windowPoint) else { return }

        let tooltipWindow = NSWindow(
            contentRect: NSRect(x: screenPoint.x - tooltipView.frame.width / 2,
                              y: screenPoint.y + 20,
                              width: tooltipView.frame.width,
                              height: tooltipView.frame.height),
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )
        tooltipWindow.backgroundColor = .clear
        tooltipWindow.isOpaque = false
        tooltipWindow.level = .floating
        tooltipWindow.contentView = tooltipView
        tooltipWindow.orderFront(nil)
        self.tooltipWindow = tooltipWindow
    }

    private func hideTooltip() {
        tooltipWindow?.orderOut(nil)
        tooltipWindow = nil
    }

    // MARK: - Drawing

    override func draw(_ dirtyRect: NSRect) {
        guard !screenshots.isEmpty else { return }

        // Recalculate layout if bounds have changed (needed for proper click detection)
        if segmentRects.isEmpty || needsLayoutRecalculation() {
            rebuildSegments()
        }

        let rect = timelineRect()

        // Draw background track
        let trackPath = NSBezierPath(roundedRect: rect, xRadius: 4, yRadius: 4)
        NSColor(white: 0.15, alpha: 1.0).setFill()
        trackPath.fill()

        // Draw segments
        for (index, segment) in segments.enumerated() {
            guard index < segmentRects.count else { continue }
            let segmentRect = segmentRects[index]

            if segment.isGap {
                drawGapIndicator(segment: segment, rect: segmentRect, isHovered: hoveredGapIndex == index)
            } else {
                drawFrameSegment(segment: segment, rect: segmentRect)
            }
        }

        // Draw search result markers
        if let searchIndices = searchResultIndices, !searchIndices.isEmpty {
            drawSearchMarkers(indices: searchIndices, in: rect)
        }

        // Draw playhead (current position)
        drawPlayhead(in: rect)

        // Draw hover indicator
        if let hovered = hoveredIndex, hovered != currentIndex {
            drawHoverIndicator(at: hovered, in: rect)
        }
    }

    private func drawFrameSegment(segment: TimelineSegment, rect: NSRect) {
        // Draw activity blocks for frames in this segment
        let frameCount = segment.endIndex - segment.startIndex + 1
        guard frameCount > 0 else { return }

        let blockWidth = rect.width / CGFloat(frameCount)

        if blockWidth < 0.5 {
            // Too dense - draw gradient
            let gradient = NSGradient(colors: [
                NSColor(white: 0.3, alpha: 1.0),
                NSColor(white: 0.4, alpha: 1.0)
            ])
            gradient?.draw(in: rect, angle: 0)
            return
        }

        for i in 0..<frameCount {
            let frameIndex = segment.startIndex + i
            let screenshot = screenshots[frameIndex]
            let x = rect.minX + CGFloat(i) * blockWidth
            let blockRect = NSRect(x: x, y: rect.minY, width: max(1, blockWidth - 0.5), height: rect.height)
            let color = colorForApp(screenshot.appName)
            color.withAlphaComponent(0.6).setFill()
            NSBezierPath(rect: blockRect).fill()
        }
    }

    private func drawGapIndicator(segment: TimelineSegment, rect: NSRect, isHovered: Bool) {
        // Draw gap background
        let gapColor = isHovered ? NSColor(white: 0.25, alpha: 1.0) : NSColor(white: 0.1, alpha: 1.0)
        gapColor.setFill()
        NSBezierPath(rect: rect).fill()

        // Draw dashed line in center
        let centerY = rect.midY
        let dashPath = NSBezierPath()
        dashPath.move(to: NSPoint(x: rect.minX + 4, y: centerY))
        dashPath.line(to: NSPoint(x: rect.maxX - 4, y: centerY))
        dashPath.setLineDash([2, 2], count: 2, phase: 0)
        NSColor(white: 0.4, alpha: 1.0).setStroke()
        dashPath.lineWidth = 1
        dashPath.stroke()

        // Draw duration text
        let durationText = formatGapDuration(segment.gapDuration)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.monospacedDigitSystemFont(ofSize: 8, weight: .medium),
            .foregroundColor: NSColor(white: 0.6, alpha: 1.0)
        ]
        let textSize = durationText.size(withAttributes: attributes)

        // Only draw text if it fits
        if textSize.width < rect.width - 4 {
            let textRect = NSRect(
                x: rect.midX - textSize.width / 2,
                y: rect.midY - textSize.height / 2,
                width: textSize.width,
                height: textSize.height
            )
            durationText.draw(in: textRect, withAttributes: attributes)
        }
    }

    private func formatGapDuration(_ duration: TimeInterval) -> String {
        if duration < 60 {
            return "\(Int(duration))s"
        } else if duration < 3600 {
            return "\(Int(duration / 60))m"
        } else if duration < 86400 {
            let hours = Int(duration / 3600)
            let mins = Int((duration.truncatingRemainder(dividingBy: 3600)) / 60)
            return mins > 0 ? "\(hours)h\(mins)m" : "\(hours)h"
        } else {
            let days = Int(duration / 86400)
            return "\(days)d"
        }
    }

    private func drawSearchMarkers(indices: Set<Int>, in rect: NSRect) {
        let markerWidth: CGFloat = 3

        for index in indices {
            let x = xPositionForIndex(index)
            let markerRect = NSRect(
                x: x - markerWidth / 2,
                y: rect.minY - 2,
                width: markerWidth,
                height: rect.height + 4
            )
            NSColor.yellow.withAlphaComponent(0.8).setFill()
            NSBezierPath(roundedRect: markerRect, xRadius: 1, yRadius: 1).fill()
        }
    }

    private func drawPlayhead(in rect: NSRect) {
        let x = xPositionForIndex(currentIndex)
        let playheadWidth: CGFloat = 4
        let playheadHeight: CGFloat = rect.height + 8

        let playheadRect = NSRect(
            x: x - playheadWidth / 2,
            y: rect.minY - 4,
            width: playheadWidth,
            height: playheadHeight
        )

        // Glow effect
        let glowRect = playheadRect.insetBy(dx: -2, dy: -2)
        NSColor.white.withAlphaComponent(0.3).setFill()
        NSBezierPath(roundedRect: glowRect, xRadius: 4, yRadius: 4).fill()

        // Main playhead
        NSColor.white.setFill()
        NSBezierPath(roundedRect: playheadRect, xRadius: 2, yRadius: 2).fill()

        // Top triangle indicator
        let triangleSize: CGFloat = 8
        let triangle = NSBezierPath()
        triangle.move(to: NSPoint(x: x, y: rect.minY - 6))
        triangle.line(to: NSPoint(x: x - triangleSize / 2, y: rect.minY - 6 - triangleSize))
        triangle.line(to: NSPoint(x: x + triangleSize / 2, y: rect.minY - 6 - triangleSize))
        triangle.close()
        NSColor.white.setFill()
        triangle.fill()
    }

    private func drawHoverIndicator(at index: Int, in rect: NSRect) {
        let x = xPositionForIndex(index)
        let indicatorWidth: CGFloat = 2

        let indicatorRect = NSRect(
            x: x - indicatorWidth / 2,
            y: rect.minY,
            width: indicatorWidth,
            height: rect.height
        )
        NSColor.white.withAlphaComponent(0.5).setFill()
        NSBezierPath(roundedRect: indicatorRect, xRadius: 1, yRadius: 1).fill()
    }

    private func colorForApp(_ appName: String) -> NSColor {
        let hash = abs(appName.hashValue)
        let hue = CGFloat(hash % 360) / 360.0
        return NSColor(hue: hue, saturation: 0.3, brightness: 0.5, alpha: 1.0)
    }
}

// MARK: - Tooltip Views

struct TooltipView: View {
    let screenshot: Screenshot

    var body: some View {
        HStack(spacing: 6) {
            AppIconView(appName: screenshot.appName, size: 14)
            Text(screenshot.appName)
                .scaledFont(size: 10, weight: .medium)
                .foregroundColor(.white)
                .lineLimit(1)
            Text(screenshot.formattedTime)
                .scaledFont(size: 10, design: .monospaced)
                .foregroundColor(.white.opacity(0.7))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.black.opacity(0.95))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.white.opacity(0.2), lineWidth: 0.5)
                )
        )
    }
}

struct GapTooltipView: View {
    let duration: TimeInterval

    var body: some View {
        VStack(spacing: 2) {
            Text("No capture")
                .scaledFont(size: 9, weight: .medium)
                .foregroundColor(.white.opacity(0.6))
            Text(formatDuration(duration))
                .scaledFont(size: 11, weight: .semibold, design: .monospaced)
                .foregroundColor(.white)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.black.opacity(0.95))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.orange.opacity(0.4), lineWidth: 0.5)
                )
        )
    }

    private func formatDuration(_ duration: TimeInterval) -> String {
        if duration < 60 {
            return "\(Int(duration)) seconds"
        } else if duration < 3600 {
            let mins = Int(duration / 60)
            let secs = Int(duration.truncatingRemainder(dividingBy: 60))
            return secs > 0 ? "\(mins) min \(secs) sec" : "\(mins) minutes"
        } else if duration < 86400 {
            let hours = Int(duration / 3600)
            let mins = Int((duration.truncatingRemainder(dividingBy: 3600)) / 60)
            return mins > 0 ? "\(hours) hr \(mins) min" : "\(hours) hours"
        } else {
            let days = Int(duration / 86400)
            let hours = Int((duration.truncatingRemainder(dividingBy: 86400)) / 3600)
            return hours > 0 ? "\(days) days \(hours) hr" : "\(days) days"
        }
    }
}

#Preview {
    InteractiveTimelineBar(
        screenshots: [],
        currentIndex: 50,
        searchResultIndices: [10, 25, 40, 60, 80],
        onSelect: { _ in }
    )
    .frame(width: 800, height: 100)
    .background(Color.black)
}
