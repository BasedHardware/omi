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

  /// Bottom-left origin that centers a window of `size` on `center`.
  static func restoreOrigin(center: NSPoint, size: NSSize) -> NSPoint {
    NSPoint(x: center.x - size.width / 2, y: center.y - size.height / 2)
  }

  /// The center a window ends up reporting (`frame.midX/midY`) after it is
  /// snapped to `origin` with `size`. Round-trips with `restoreOrigin` ONLY when
  /// the same `size` is used for both: computing the origin with a glow-inflated
  /// size but snapping with the bare pill size shifts the recorded center by half
  /// the size difference — the pill-drift bug.
  static func recordedCenter(afterSnapOrigin origin: NSPoint, size: NSSize) -> NSPoint {
    NSPoint(x: origin.x + size.width / 2, y: origin.y + size.height / 2)
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
    case .screenTopCenter(let screenFrame):
      return topCenteredFrame(size: targetSize, anchorFrame: screenFrame)
    }
  }

  /// Semantic placement contract shared by the live PTT and agent-switcher
  /// state transitions. Window owns which transition is active and supplies
  /// its already-adjusted target size; geometry owns whether that transition
  /// may inherit the current midpoint or must return to a canonical anchor.
  /// A notch island hangs from the display's top edge by definition. Auto
  /// layout can grow the panel to fit content that has not finished
  /// collapsing (the hosting view forwards SwiftUI's min size as a window
  /// constraint), and AppKit grows windows from their pinned bottom-left
  /// origin — which pushes the top-anchored chrome above the screen where
  /// nothing ever brings it back (the "island disappeared after hovering"
  /// bug). Whenever a resize leaves the top edge somewhere other than the
  /// screen top while the island is in its non-interactive chrome state,
  /// the frame is re-anchored instead of trusted.
  /// `isConversationOpen` is the chrome/content boundary: an open conversation
  /// surface (input, response, agent chat) is user content whose frame the user
  /// may have moved or resized — Spaces transitions and content growth on it
  /// must never be snapped back to the screen-top chrome anchor. Only the
  /// closed-surface island (idle pill, hover menu) is chrome this guard owns.
  static func notchTopReanchoredFrame(
    frame: NSRect,
    screenFrame: NSRect,
    isResizable: Bool,
    isUserDragging: Bool,
    isConversationOpen: Bool,
    epsilon: CGFloat = 0.5
  ) -> NSRect? {
    guard !isResizable, !isUserDragging, !isConversationOpen else { return nil }
    guard screenFrame.width > 0, screenFrame.height > 0 else { return nil }
    let desiredTop = screenFrame.maxY
    guard abs(frame.maxY - desiredTop) > epsilon else { return nil }
    return NSRect(
      x: screenFrame.midX - frame.width / 2,
      y: desiredTop - frame.height,
      width: frame.width,
      height: frame.height
    )
  }

  static func surfaceTransitionFrame(
    currentFrame: NSRect,
    targetSize: NSSize,
    transition: SurfaceTransition,
    placement: SurfacePlacement
  ) -> NSRect {
    switch placement {
    case .notch(let screenFrame):
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

    case .pill(let draggable, let canonicalCompactFrame):
      switch transition {
      case .pushToTalk:
        let sourceFrame = draggable ? currentFrame : canonicalCompactFrame
        return targetFrame(currentFrame: sourceFrame, targetSize: targetSize, anchor: .center)
      case .agentSwitcher(let visible):
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

  /// Whether the notch window may treat its ENTIRE fixed frame as clickable. Only content that
  /// visibly fills the window earns that: an expanded AI response panel or a notification card.
  /// A conversation that is merely open (ask input, "thinking" shimmer) must keep the
  /// content-derived hit region, or the oversized fixed window becomes an invisible click sink
  /// over whatever sits beneath it — the bug where the main window's Tasks/Rewind/Apps pills went
  /// dead whenever the bar was "thinking".
  static func notchWholeWindowHitsAllowed(
    showingAIConversation: Bool,
    showingAIResponse: Bool,
    hasNotification: Bool
  ) -> Bool {
    if hasNotification { return true }
    return showingAIConversation && showingAIResponse
  }

  /// Hit region for surface-filling content states (expanded response panel,
  /// notification card). The window frame still carries transparent glow
  /// outsets beside and below the visible surface; content owns exactly the
  /// surface, so the glow ring keeps passing clicks through to other apps.
  static func notchSurfaceContentContainsLocal(
    localPoint: NSPoint,
    windowSize: NSSize,
    bottomOutset: CGFloat,
    horizontalOutset: CGFloat
  ) -> Bool {
    notchChromeActivationContainsLocal(
      localPoint: localPoint,
      windowSize: windowSize,
      chromeHeight: max(0, windowSize.height - bottomOutset),
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

  static func unionSize(_ a: NSSize, _ b: NSSize) -> NSSize {
    NSSize(width: max(a.width, b.width), height: max(a.height, b.height))
  }

  /// A mounted notification card owns the closed surface. Every transient
  /// island state — PTT listening, thinking, the too-short/mic-error status
  /// banner — may only *grow* that surface, never replace it.
  ///
  /// The bug this exists to prevent: the card stays mounted while the user
  /// holds the reply shortcut against it (Interject), so any resize that
  /// substitutes the bare voice-island size crushes a 508pt card into a
  /// ~270pt notch lobe and the copy re-wraps to three truncated words. Height
  /// is the card's own plus `additionalHeight` — whatever the transient state
  /// stacks alongside the card (the status banner row) — because the island's
  /// chrome band is already counted inside the card size. `transientSize` is
  /// the no-card surface and already carries that budget itself, so
  /// `additionalHeight` applies only when a card is mounted.
  static func notificationPreservingSurfaceSize(
    transientSize: NSSize,
    hasMountedNotification: Bool,
    notificationSize: NSSize,
    additionalHeight: CGFloat = 0
  ) -> NSSize {
    guard hasMountedNotification else { return transientSize }
    return NSSize(
      width: max(notificationSize.width, transientSize.width),
      height: notificationSize.height + additionalHeight
    )
  }

  /// Closed-conversation chrome size. A mounted notification card wins over
  /// listening/thinking island sizes (or the union if listening is larger).
  static func collapsedSurfaceSize(
    hasMountedNotification: Bool,
    isVoiceListening: Bool,
    isThinking: Bool,
    notificationSize: NSSize,
    listeningSize: NSSize,
    thinkingSize: NSSize,
    idleSize: NSSize
  ) -> NSSize {
    if hasMountedNotification {
      var size = notificationSize
      if isVoiceListening { size = unionSize(size, listeningSize) }
      if isThinking { size = unionSize(size, thinkingSize) }
      return size
    }
    if isVoiceListening { return listeningSize }
    if isThinking { return thinkingSize }
    return idleSize
  }

  static func windowResizeMinimumSize(
    showingAIConversation: Bool,
    hasMountedNotification: Bool,
    isVoiceListening: Bool,
    isHovering: Bool,
    usesNotchIsland: Bool,
    conversationWidth: CGFloat,
    notificationSize: NSSize,
    listeningWidth: CGFloat,
    hoverWidth: CGFloat,
    idleSize: NSSize
  ) -> NSSize {
    if showingAIConversation {
      return NSSize(width: conversationWidth, height: idleSize.height)
    }
    if hasMountedNotification {
      var size = notificationSize
      if isVoiceListening {
        size = unionSize(size, NSSize(width: listeningWidth, height: notificationSize.height))
      }
      return size
    }
    if isVoiceListening && !usesNotchIsland {
      return NSSize(width: listeningWidth, height: idleSize.height)
    }
    if isHovering {
      return NSSize(width: hoverWidth, height: idleSize.height)
    }
    return idleSize
  }

  /// Insight teasers collapse to one line unless the pointer is over the card
  /// or Interject PTT is holding a reply against it.
  static func interjectInsightTeaserLineLimit(
    kindIsInsight: Bool,
    isHovering: Bool,
    interjectBarHovering: Bool,
    interjectPTTHoldActive: Bool
  ) -> Int {
    guard kindIsInsight else { return 3 }
    return (isHovering || interjectBarHovering || interjectPTTHoldActive) ? 6 : 1
  }
}
