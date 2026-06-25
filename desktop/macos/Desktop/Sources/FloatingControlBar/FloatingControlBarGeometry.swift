import AppKit

/// Pure frame math for the floating bar.
///
/// Keep window state transitions in `FloatingControlBarWindow`, but keep geometry
/// policy here so resize anchors are explicit and testable.
enum FloatingControlBarGeometry {
    enum CompactPlacement {
        case canonical
        case preservingCurrentCenter
    }

    static func centerAnchoredFrame(currentFrame: NSRect, targetSize: NSSize) -> NSRect {
        NSRect(
            x: currentFrame.midX - targetSize.width / 2,
            y: currentFrame.midY - targetSize.height / 2,
            width: targetSize.width,
            height: targetSize.height
        )
    }

    static func topCenterAnchoredFrame(currentFrame: NSRect, targetSize: NSSize) -> NSRect {
        NSRect(
            x: currentFrame.midX - targetSize.width / 2,
            y: currentFrame.maxY - targetSize.height,
            width: targetSize.width,
            height: targetSize.height
        )
    }

    static func defaultPillFrame(size: NSSize, visibleFrame: NSRect, topInset: CGFloat) -> NSRect {
        let x = (visibleFrame.midX - size.width / 2).rounded(.toNearestOrAwayFromZero)
        let y = visibleFrame.maxY - size.height - topInset
        return NSRect(origin: NSPoint(x: x, y: y), size: size)
    }

    static func compactFrame(
        currentFrame: NSRect,
        placement: CompactPlacement,
        visibleFrame: NSRect,
        topInset: CGFloat,
        compactSize: NSSize
    ) -> NSRect {
        switch placement {
        case .canonical:
            return defaultPillFrame(size: compactSize, visibleFrame: visibleFrame, topInset: topInset)
        case .preservingCurrentCenter:
            return centerAnchoredFrame(currentFrame: currentFrame, targetSize: compactSize)
        }
    }

    /// PTT is a transient compact-bar state. Expanded voice UI grows from the
    /// compact pill center; collapse either preserves the user's dragged center or
    /// snaps back to the canonical default pill when dragging is disabled.
    static func pushToTalkFrame(
        currentFrame: NSRect,
        expanded: Bool,
        draggable: Bool,
        visibleFrame: NSRect,
        topInset: CGFloat,
        compactSize: NSSize,
        voiceSize: NSSize
    ) -> NSRect {
        let compactPlacement: CompactPlacement = draggable ? .preservingCurrentCenter : .canonical
        let compactSourceFrame = compactFrame(
            currentFrame: currentFrame,
            placement: compactPlacement,
            visibleFrame: visibleFrame,
            topInset: topInset,
            compactSize: compactSize
        )

        if expanded {
            return centerAnchoredFrame(currentFrame: compactSourceFrame, targetSize: voiceSize)
        }

        return compactSourceFrame
    }
}
