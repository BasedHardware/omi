import SwiftUI

// Port of `react-native/src/desktop/desktopChrome.ts` (motion tokens, layout
// constants) and `desktopMotion.ts` (easings) onto SwiftUI animation curves
// with the same feel. `desktopEaseSmoothOut()` is bezier(0.22, 1, 0.36, 1) —
// SwiftUI's `timingCurve` takes exactly those control points. Reduce Motion
// maps to zero-duration, like `motionDuration(ms, reduceMotion)`.

// MARK: - Layout constants (desktopChrome.ts)

/// The 12/44 traffic-light contract. `windowInset = 12` on every window edge
/// and the first chrome row (the omnibar row) is 44 high; the native host
/// pins the same values (`OmiWindowInset = 12.0`, `OmiChromeRowHeight = 44.0`)
/// and centers the system lights on that row. desktopChrome.test.ts asserts
/// the pair; change both sides together.
public enum DesktopLayout {
    public static let windowInset: CGFloat = 12
    public static let omnibarHeight: CGFloat = 44
    public static let filterRowHeight: CGFloat = 36
    public static let trafficLightButton: CGFloat = 14
    public static let trafficLightSpacing: CGFloat = 8
    public static let trafficLightTrailing: CGFloat = 16
    /// 3 * 14 + 2 * 8.
    public static let trafficLightClusterWidth: CGFloat = 58
    /// Cluster + trailing spacer, the reserved window-controls slot.
    public static let trafficLightRowWidth: CGFloat = 74
    public static let glassCornerRadius: CGFloat = 22
    public static let stageMaxWidth: CGFloat = 992
}

public let desktopSearchPlaceholder = "Search what you've seen and heard…"

/// The v5.1 Activity filters (All / Conversations / Recall / Tasks) and the
/// Date / Type / Topic grouping live in OmiKit as `TimelineFilter` /
/// `TimelineGrouping`; labels come from those types.

/// Settings panes (`desktopSettingsPanes`).
public enum DesktopSettingsPane: String, CaseIterable, Sendable {
    case general = "General"
    case account = "Account & Plan"
    case transcription = "Transcription"
    case rewind = "Rewind"
    case alertsPrivacy = "Alerts & Privacy"
    case aiAutomation = "AI & Automation"
    case apps = "Apps"
    case about = "About"
}

// MARK: - Motion tokens (desktopChrome.ts desktopMotion)

public enum DesktopMotion {
    public static let staggerMs: Double = 40
    public static let microMs: Double = 80
    public static let quickMs: Double = 150
    public static let fastMs: Double = 250
    public static let mediumMs: Double = 350
    public static let slowMs: Double = 400
    public static let verySlowMs: Double = 500
    /// navMs == fastMs.
    public static let navMs: Double = fastMs
    /// pressMs == microMs.
    public static let pressMs: Double = microMs
    /// stepMs == fastMs.
    public static let stepMs: Double = fastMs
    /// settleMs == mediumMs.
    public static let settleMs: Double = mediumMs
    /// overlayMs == slowMs.
    public static let overlayMs: Double = slowMs
    /// checkboxMs == quickMs.
    public static let checkboxMs: Double = quickMs
    /// searchExpandMs == quickMs.
    public static let searchExpandMs: Double = quickMs
    public static let listInsertMs: Double = 0
    public static let glassMs: Double = 0

    // desktopStageFade.
    public static let chatRiseY: CGFloat = 10
    public static let dropScale: CGFloat = 0.98
    public static let hubOffsetY: CGFloat = 8

    // MARK: Easings (desktopMotion.ts)

    /// `desktopEaseSmoothOut` — bezier(0.22, 1, 0.36, 1).
    public static func smoothOut(_ duration: Double) -> Animation {
        .timingCurve(0.22, 1.0, 0.36, 1.0, duration: duration)
    }

    /// `desktopEaseInOut` — inOut cubic.
    public static func easeInOut(_ duration: Double) -> Animation {
        .timingCurve(0.65, 0, 0.35, 1.0, duration: duration)
    }

    /// `desktopEaseBounce` — bezier(0.34, 1.36, 0.64, 1).
    public static func bounce(_ duration: Double) -> Animation {
        .timingCurve(0.34, 1.36, 0.64, 1.0, duration: duration)
    }

    // MARK: Reduce-motion gates (motionDuration et al)

    public static func motionDuration(_ ms: Double, reduceMotion: Bool) -> Double {
        reduceMotion ? 0 : ms
    }

    public static func navAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(navMs, reduceMotion)
    }

    public static func pressAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(pressMs, reduceMotion)
    }

    public static func stepAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(stepMs, reduceMotion)
    }

    public static func overlayAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(overlayMs, reduceMotion)
    }

    public static func searchExpandAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(searchExpandMs, reduceMotion)
    }

    public static func checkboxAnimation(_ reduceMotion: Bool) -> Animation? {
        animation(checkboxMs, reduceMotion)
    }

    /// Zero-duration collapses to nil — `runShippingTiming` sets the value
    /// directly instead of animating when the effective duration is 0.
    private static func animation(_ ms: Double, _ reduceMotion: Bool) -> Animation? {
        let duration = motionDuration(ms, reduceMotion: reduceMotion)
        guard duration > 0 else { return nil }
        return smoothOut(duration)
    }
}

// MARK: - Chat error visibility (desktopChrome.ts visibleChatError)

/// Desktop session phase mirroring `DesktopSession`.
public enum DesktopSessionPhase: Sendable, Equatable {
    case probing
    case signedOut
    case ready
}

/// Chat transport errors never take over the stage: they surface under the
/// omnibar only once the session is ready; a signed-out or probing first
/// paint stays quiet.
public func visibleChatError(_ session: DesktopSessionPhase, _ error: String?) -> String? {
    guard session == DesktopSessionPhase.ready, let error, !error.isEmpty else { return nil }
    return error
}

// MARK: - Explore checklist (exploreChecklist.ts)

public enum ExploreCheck: String, CaseIterable, Sendable {
    case recall
    case chat
    case conversations
    case tasks
    case settings

    public var label: String {
        switch self {
        case ExploreCheck.recall: return "Find something you saw"
        case ExploreCheck.chat: return "Ask about your day"
        case ExploreCheck.conversations: return "Browse your conversations"
        case ExploreCheck.tasks: return "Check your tasks"
        case ExploreCheck.settings: return "Make Omi yours"
        }
    }
}

/// `parseExploreProgress` — CSV of check ids persisted through the
/// `omi.onboarding.exploreProgress` preference.
public func parseExploreProgress(_ value: String) -> Set<ExploreCheck> {
    var done = Set<ExploreCheck>()
    for part in value.split(separator: ",") {
        let id = part.trimmingCharacters(in: .whitespaces)
        if let check = ExploreCheck(rawValue: id) {
            done.insert(check)
        }
    }
    return done
}

/// `serializeExploreProgress` — checklist order, CSV.
public func serializeExploreProgress(_ done: Set<ExploreCheck>) -> String {
    ExploreCheck.allCases
        .filter { done.contains($0) }
        .map { $0.rawValue }
        .joined(separator: ",")
}

// MARK: - Window commands

/// Window commands the traffic lights dispatch to the native host. The macOS
/// host (Platforms/macOS) observes the `omi.desktop.windowCommand`
/// notification (name exposed as `DesktopWindowSignals.windowCommand`) and
/// runs the same AppKit paths as the real buttons (`performClose:` honors
/// `windowShouldClose:` and app teardown). Outside macOS the dots are inert,
/// exactly like the RN surface with no `OmiDesktopCommands` module.
public enum DesktopWindowCommand: String, Sendable {
    case close
    case minimize
    case zoom
}

/// Notification names the desktop surface shares with the native host. Kept
/// as plain string constants: Skip cannot resolve implicit members on
/// `Notification.Name` extensions.
public enum DesktopWindowSignals {
    public static let windowCommand = "omi.desktop.windowCommand"
    /// Edit → Search (Cmd+K) menu event published by the desktop commands
    /// host; the chrome opens Search mode on Home and focuses the omnibar.
    public static let searchCommand = "omi.desktop.searchCommand"
}

/// Fire-and-forget dispatch to the host (`performWindowCommand`).
public func performDesktopWindowCommand(_ command: DesktopWindowCommand) {
    NotificationCenter.default.post(
        name: Notification.Name(DesktopWindowSignals.windowCommand),
        object: nil,
        userInfo: ["command": command.rawValue]
    )
}
