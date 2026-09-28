import Foundation

// Port of `react-native/src/app/onboardingFlow.ts` — the pure onboarding
// step vocabulary and itineraries — plus `usePostSetupHomeCue.ts` (the
// one-shot post-setup Home cue tracker). Pure logic only: no I/O, no
// transport, fully unit-testable.

// MARK: - Desktop onboarding (onboardingFlow.ts)

/// `desktopOnboardingSteps`.
public enum DesktopOnboardingStep: String, Sendable, Hashable, CaseIterable {
    case welcome
    case value
    case signIn
    case permissions
    case harnesses
    case data
    case tutorial
    case finish

    /// Canonical rank in `desktopOnboardingSteps`.
    public var rank: Int {
        DesktopOnboardingStep.allCases.firstIndex(of: self) ?? 0
    }
}

/// Port of `desktopItinerary`: the sign-in card only exists pre-sign-in.
public func desktopItinerary(signedIn: Bool) -> [DesktopOnboardingStep] {
    DesktopOnboardingStep.allCases.filter { step in
        step == .signIn ? !signedIn : true
    }
}

/// Port of `nextDesktopStep`: the next itinerary step; when `step` fell off
/// the itinerary (e.g. sign-in completed mid-flow), the first remaining
/// step ranked after it.
public func nextDesktopStep(
    _ step: DesktopOnboardingStep, signedIn: Bool
) -> DesktopOnboardingStep? {
    let itinerary = desktopItinerary(signedIn: signedIn)
    if let index = itinerary.firstIndex(of: step) {
        let next = index + 1
        return next < itinerary.count ? itinerary[next] : nil
    }
    return itinerary.first { $0.rank > step.rank }
}

/// Port of `previousDesktopStep`: back is hand-authored so a completed
/// sign-in never walks back onto the sign-in card.
public func previousDesktopStep(
    _ step: DesktopOnboardingStep, signedIn: Bool
) -> DesktopOnboardingStep? {
    switch step {
    case .welcome, .permissions:
        return nil
    case .harnesses:
        return .permissions
    case .data:
        return .harnesses
    case .tutorial:
        return .data
    case .finish:
        return .tutorial
    case .value:
        return .welcome
    case .signIn:
        return signedIn ? nil : .value
    }
}

/// Port of `desktopProgressSteps` — every step except `welcome`.
public func desktopProgressSteps(signedIn: Bool) -> [DesktopOnboardingStep] {
    DesktopOnboardingStep.allCases.filter { $0 != .welcome }
}

// MARK: - Mobile setup steps (onboardingFlow.ts)

/// `mobileSetupSteps` in order.
public enum MobileSetupStep: String, Sendable, Hashable, CaseIterable {
    case consent
    case name
    case language
    case source
    case permissions
    case speech
    case knowledge
    case complete
}

/// `MobileOnboardingStep` = welcome | setup step.
public enum MobileOnboardingStep: Sendable, Hashable {
    case welcome
    case setup(MobileSetupStep)
}

/// Port of `nextMobileSetupStep`.
public func nextMobileSetupStep(_ step: MobileSetupStep) -> MobileSetupStep? {
    let steps = MobileSetupStep.allCases
    guard let index = steps.firstIndex(of: step) else { return nil }
    let next = index + 1
    return next < steps.count ? steps[next] : nil
}

/// Port of `previousMobileSetupStep`.
public func previousMobileSetupStep(_ step: MobileSetupStep) -> MobileSetupStep? {
    let steps = MobileSetupStep.allCases
    guard let index = steps.firstIndex(of: step), index > 0 else { return nil }
    return steps[index - 1]
}

// MARK: - Post-setup Home cue (usePostSetupHomeCue.ts)

/// One-shot Home cue after leaving Welcome/setup.
public enum PostSetupHomeCue: Sendable, Equatable {
    case proven
    case unavailable
}

/// Port of `usePostSetupHomeCue` as an explicit state machine (no React
/// effects): arms only on an explicit `true → false` onboarding transition,
/// never a cold probe (`nil → false`), then settles from `readsPhase`.
public struct PostSetupHomeCueTracker: Sendable, Equatable {
    public private(set) var cue: PostSetupHomeCue?
    public private(set) var armed: Bool
    public private(set) var previousOnboardingRequired: Bool?

    public init() {
        cue = nil
        armed = false
        previousOnboardingRequired = nil
    }

    /// Feeds the next `(onboardingRequired, readsPhase)` observation and
    /// returns the cue to display (nil = none).
    public mutating func update(
        onboardingRequired: Bool?, readsPhase: ReadsPhase
    ) -> PostSetupHomeCue? {
        let previous = previousOnboardingRequired
        previousOnboardingRequired = onboardingRequired

        if onboardingRequired == true {
            armed = false
            cue = nil
            return nil
        }
        if previous == true && onboardingRequired == false {
            armed = true
            cue = nil
        }
        guard armed, cue == nil else { return cue }
        switch readsPhase {
        case .ready:
            armed = false
            cue = .proven
        case .unavailable, .savedButRefreshFailed:
            armed = false
            cue = .unavailable
        case .initialLoading, .refreshing:
            break
        }
        return cue
    }
}

// MARK: - Reads phase (useDesktopReads.ts)

/// `ReadsPhase` from `useDesktopReads.ts`.
public enum ReadsPhase: Sendable, Equatable {
    case initialLoading
    case refreshing
    case ready
    case savedButRefreshFailed
    case unavailable
}

/// Port of the `readsPhase` judgment: hard failures degrade the phase;
/// projection-unavailable outcomes (a dev backend without the canonical
/// store wired) do not — every affected card renders its own empty copy.
public func deriveReadsPhase(
    showingSavedRows: Bool, hardFailed: Bool
) -> ReadsPhase {
    if hardFailed {
        return showingSavedRows ? .savedButRefreshFailed : .unavailable
    }
    return .ready
}

/// Copy ported from `onboardingCopy.ts`.
public let onboardingSessionUnreachableCopy =
    "Couldn't reach Omi to check your session. Try Sign in again when you are online."
public let onboardingPrivacyURL = "https://www.omi.me/pages/privacy"
public let onboardingTermsURL = "https://www.omi.me/pages/terms-of-service"

/// `PRIMARY_LANGUAGES` from `onboardingCopy.ts`.
public let onboardingPrimaryLanguages: [(code: String, name: String)] = [
    ("en", "English"),
    ("en-US", "English (US)"),
    ("es", "Spanish"),
    ("zh", "Chinese (Mandarin, Simplified)"),
    ("hi", "Hindi"),
    ("pt", "Portuguese"),
    ("ja", "Japanese"),
    ("de", "German"),
    ("fr", "French"),
    ("ko", "Korean"),
    ("ar", "Arabic"),
    ("it", "Italian"),
    ("vi", "Vietnamese"),
]

/// `ACQUISITION_SOURCES` from `onboardingCopy.ts`.
public let onboardingAcquisitionSources: [String] = [
    "TikTok", "YouTube", "Instagram", "X (Twitter)", "Reddit", "LinkedIn",
    "Friend", "Coworker", "Event", "App Store", "Google Search", "Other",
]

/// `DESKTOP_VALUE_CLAIMS` from `onboardingCopy.ts`.
public let desktopValueClaims: [String] = [
    "I watch your screen — the frames, and the text in your windows.",
    "I listen — your microphone, and the audio of your calls.",
    "It lands in your Omi account, and you read it back from Home.",
]
