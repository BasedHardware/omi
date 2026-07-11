import AppKit

/// Pure frame math for the floating bar.
///
/// Keep window state transitions in `FloatingControlBarWindow`, but keep geometry
/// policy here so resize anchors are explicit and testable.
enum FloatingControlBarGeometry {
    enum TransitionAnchor {
        case center
        case topCenter
        case screenTopCenter(NSRect)
    }

    enum SurfaceTransition {
        case pushToTalk(expanded: Bool)
        case agentSwitcher(visible: Bool)
    }

    enum SurfacePlacement {
        case notch(screenFrame: NSRect?)
        case pill(draggable: Bool, canonicalCompactFrame: NSRect)
    }

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

    /// Canonical top-center placement. Non-draggable notch surfaces must use
    /// the display midpoint rather than an in-flight window frame: PTT, chat,
    /// and the agent list can otherwise preserve a transient animation offset.
    static func topCenteredFrame(size: NSSize, anchorFrame: NSRect) -> NSRect {
        NSRect(
            x: (anchorFrame.midX - size.width / 2).rounded(.toNearestOrAwayFromZero),
            y: anchorFrame.maxY - size.height,
            width: size.width,
            height: size.height
        )
    }

    /// Single pure authority for converting a surface-state size transition
    /// into its window frame. `FloatingControlBarWindow` owns the state machine
    /// and selects the anchor; this function guarantees every transition uses
    /// the same placement policy.
    static func targetFrame(
        currentFrame: NSRect,
        targetSize: NSSize,
        anchor: TransitionAnchor
    ) -> NSRect {
        switch anchor {
        case .center:
            return centerAnchoredFrame(currentFrame: currentFrame, targetSize: targetSize)
        case .topCenter:
            return topCenterAnchoredFrame(currentFrame: currentFrame, targetSize: targetSize)
        case let .screenTopCenter(screenFrame):
            return topCenteredFrame(size: targetSize, anchorFrame: screenFrame)
        }
    }

    /// Semantic placement contract shared by the live PTT and agent-switcher
    /// state transitions. Window owns which transition is active and supplies
    /// its already-adjusted target size; geometry owns whether that transition
    /// may inherit the current midpoint or must return to a canonical anchor.
    static func surfaceTransitionFrame(
        currentFrame: NSRect,
        targetSize: NSSize,
        transition: SurfaceTransition,
        placement: SurfacePlacement
    ) -> NSRect {
        switch placement {
        case let .notch(screenFrame):
            guard let screenFrame,
                  screenFrame.width > 0,
                  screenFrame.height > 0
            else {
                return targetFrame(currentFrame: currentFrame, targetSize: targetSize, anchor: .topCenter)
            }
            return targetFrame(
                currentFrame: currentFrame,
                targetSize: targetSize,
                anchor: .screenTopCenter(screenFrame)
            )

        case let .pill(draggable, canonicalCompactFrame):
            switch transition {
            case .pushToTalk:
                let sourceFrame = draggable ? currentFrame : canonicalCompactFrame
                return targetFrame(currentFrame: sourceFrame, targetSize: targetSize, anchor: .center)
            case let .agentSwitcher(visible):
                if visible {
                    return targetFrame(currentFrame: currentFrame, targetSize: targetSize, anchor: .topCenter)
                }
                return targetFrame(
                    currentFrame: canonicalCompactFrame,
                    targetSize: targetSize,
                    anchor: .center
                )
            }
        }
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
            return targetFrame(currentFrame: currentFrame, targetSize: targetSize, anchor: .topCenter)
        }

        return targetFrame(
            currentFrame: currentFrame,
            targetSize: targetSize,
            anchor: .screenTopCenter(screenFrame)
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

        return surfaceTransitionFrame(
            currentFrame: currentFrame,
            targetSize: expanded ? voiceSize : compactSize,
            transition: .pushToTalk(expanded: expanded),
            placement: .pill(draggable: draggable, canonicalCompactFrame: compactSourceFrame)
        )
    }
}
