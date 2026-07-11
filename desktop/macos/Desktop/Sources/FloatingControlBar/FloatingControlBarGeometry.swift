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

    /// A notch island is tied to the display's camera housing, not to a prior
    /// transient panel frame. When its surface changes size, retain the display
    /// top edge and re-center it on the display so a stale panel offset cannot
    /// leave a lobe underneath the hardware notch.
    static func topAnchoredFrame(
        currentFrame: NSRect,
        targetSize: NSSize,
        screenFrame: NSRect?,
        pinsToScreenCenter: Bool
    ) -> NSRect {
        guard pinsToScreenCenter,
              let screenFrame,
              screenFrame.width > 0,
              screenFrame.height > 0
        else {
            return topCenterAnchoredFrame(currentFrame: currentFrame, targetSize: targetSize)
        }

        return NSRect(
            x: (screenFrame.midX - targetSize.width / 2).rounded(.toNearestOrAwayFromZero),
            y: screenFrame.maxY - targetSize.height,
            width: targetSize.width,
            height: targetSize.height
        )
    }

    /// The notch window often includes transparent glow/layout outsets below and
    /// beside the visible black island. Hover activation must be limited to the
    /// actual top chrome so transparent pixels do not steal hover from windows
    /// sitting immediately under the notch.
    static func notchChromeActivationContains(
        mouseLocation: NSPoint,
        windowFrame: NSRect,
        chromeHeight: CGFloat,
        horizontalOutset: CGFloat
    ) -> Bool {
        guard windowFrame.contains(mouseLocation) else { return false }

        let localX = mouseLocation.x - windowFrame.minX
        let distanceFromTop = windowFrame.maxY - mouseLocation.y
        return notchChromeActivationContainsLocal(
            localX: localX,
            distanceFromTop: distanceFromTop,
            windowWidth: windowFrame.width,
            chromeHeight: chromeHeight,
            horizontalOutset: horizontalOutset
        )
    }

    static func notchChromeActivationContainsLocal(
        localPoint: NSPoint,
        windowSize: NSSize,
        chromeHeight: CGFloat,
        horizontalOutset: CGFloat
    ) -> Bool {
        let distanceFromTop = windowSize.height - localPoint.y
        return notchChromeActivationContainsLocal(
            localX: localPoint.x,
            distanceFromTop: distanceFromTop,
            windowWidth: windowSize.width,
            chromeHeight: chromeHeight,
            horizontalOutset: horizontalOutset
        )
    }

    private static func notchChromeActivationContainsLocal(
        localX: CGFloat,
        distanceFromTop: CGFloat,
        windowWidth: CGFloat,
        chromeHeight: CGFloat,
        horizontalOutset: CGFloat
    ) -> Bool {
        guard distanceFromTop >= 0, distanceFromTop <= chromeHeight else { return false }

        let minX = max(0, horizontalOutset)
        let maxX = max(minX, windowWidth - horizontalOutset)
        return localX >= minX && localX <= maxX
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
