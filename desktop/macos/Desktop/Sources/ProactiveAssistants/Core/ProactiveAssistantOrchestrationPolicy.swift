import Foundation

enum ProactiveAssistantOrchestrationPolicy {
    enum ScreenshotAppDecision: Equatable {
        case pause(backoffUntil: Date)
        case resumeIntoBackoff
        case resumeAndCapture
        case continueBackoff
        case capture
    }

    enum VideoCallThrottleDecision: Equatable {
        case capture(nextCounter: Int, didLeaveCall: Bool)
        case skip(nextCounter: Int, didEnterCall: Bool)
    }

    enum DistributionDecision: Equatable {
        case flushNow
        case debounce
        case skip
    }

    static func shouldRecheckPermission(
        now: Date,
        lastCheckTime: Date,
        interval: TimeInterval
    ) -> Bool {
        now.timeIntervalSince(lastCheckTime) >= interval
    }

    static func screenshotAppDecision(
        isScreenshotAppFrontmost: Bool,
        wasScreenshotAppFrontmost: Bool,
        backoffUntil: Date,
        now: Date,
        backoffDuration: TimeInterval
    ) -> ScreenshotAppDecision {
        if isScreenshotAppFrontmost {
            return .pause(backoffUntil: now.addingTimeInterval(backoffDuration))
        }

        if wasScreenshotAppFrontmost {
            return now < backoffUntil ? .resumeIntoBackoff : .resumeAndCapture
        }

        if now < backoffUntil {
            return .continueBackoff
        }

        return .capture
    }

    static func videoCallThrottleDecision(
        isVideoCall: Bool,
        currentCounter: Int,
        throttleFactor: Int
    ) -> VideoCallThrottleDecision {
        guard throttleFactor > 1 else {
            return .capture(nextCounter: 0, didLeaveCall: !isVideoCall && currentCounter > 0)
        }

        if isVideoCall {
            let nextCounter = currentCounter + 1
            if nextCounter < throttleFactor {
                return .skip(nextCounter: nextCounter, didEnterCall: nextCounter == 1)
            }
            return .capture(nextCounter: 0, didLeaveCall: false)
        }

        return .capture(nextCounter: 0, didLeaveCall: currentCounter > 0)
    }

    static func distributionDecision(
        lastDistributedApp: String?,
        lastDistributedWindowTitle: String?,
        frameApp: String,
        frameWindowTitle: String?,
        lastDistributionTime: Date,
        now: Date,
        defaultFallbackInterval: TimeInterval,
        messagingFallbackInterval: TimeInterval,
        messagingFastPathApps: Set<String>
    ) -> DistributionDecision {
        guard lastDistributedApp != nil else {
            return .flushNow
        }

        if ContextDetection.didContextChange(
            fromApp: lastDistributedApp,
            fromWindowTitle: lastDistributedWindowTitle,
            toApp: frameApp,
            toWindowTitle: frameWindowTitle
        ) {
            return .debounce
        }

        let fallbackInterval = messagingFastPathApps.contains(frameApp)
            ? messagingFallbackInterval
            : defaultFallbackInterval
        return now.timeIntervalSince(lastDistributionTime) >= fallbackInterval ? .flushNow : .skip
    }
}

struct ProactiveScreenshotCaptureGate {
    private(set) var wasScreenshotAppFrontmost = false
    private(set) var backoffUntil: Date = .distantPast

    mutating func nextDecision(
        isScreenshotAppFrontmost: Bool,
        now: Date,
        backoffDuration: TimeInterval
    ) -> ProactiveAssistantOrchestrationPolicy.ScreenshotAppDecision {
        let decision = ProactiveAssistantOrchestrationPolicy.screenshotAppDecision(
            isScreenshotAppFrontmost: isScreenshotAppFrontmost,
            wasScreenshotAppFrontmost: wasScreenshotAppFrontmost,
            backoffUntil: backoffUntil,
            now: now,
            backoffDuration: backoffDuration
        )

        switch decision {
        case .pause(let nextBackoffUntil):
            wasScreenshotAppFrontmost = true
            backoffUntil = nextBackoffUntil
        case .resumeIntoBackoff, .resumeAndCapture:
            wasScreenshotAppFrontmost = false
        case .continueBackoff, .capture:
            break
        }

        return decision
    }

    mutating func reset() {
        wasScreenshotAppFrontmost = false
        backoffUntil = .distantPast
    }
}

struct ProactiveVideoCallThrottleGate {
    private(set) var counter = 0

    mutating func nextDecision(
        isVideoCall: Bool,
        throttleFactor: Int
    ) -> ProactiveAssistantOrchestrationPolicy.VideoCallThrottleDecision {
        let decision = ProactiveAssistantOrchestrationPolicy.videoCallThrottleDecision(
            isVideoCall: isVideoCall,
            currentCounter: counter,
            throttleFactor: throttleFactor
        )

        switch decision {
        case .capture(let nextCounter, _), .skip(let nextCounter, _):
            counter = nextCounter
        }

        return decision
    }

    mutating func reset() {
        counter = 0
    }
}

struct ProactiveFrameDistributionGate {
    enum Action: Equatable {
        case flushNow
        case scheduleDebounce
        case skip
    }

    private(set) var lastDistributedApp: String?
    private(set) var lastDistributedWindowTitle: String?
    private(set) var lastDistributionTime: Date = .distantPast

    mutating func reset() {
        lastDistributedApp = nil
        lastDistributedWindowTitle = nil
        lastDistributionTime = .distantPast
    }

    mutating func nextAction(
        frameApp: String,
        frameWindowTitle: String?,
        now: Date,
        defaultFallbackInterval: TimeInterval,
        messagingFallbackInterval: TimeInterval,
        messagingFastPathApps: Set<String>
    ) -> Action {
        let decision = ProactiveAssistantOrchestrationPolicy.distributionDecision(
            lastDistributedApp: lastDistributedApp,
            lastDistributedWindowTitle: lastDistributedWindowTitle,
            frameApp: frameApp,
            frameWindowTitle: frameWindowTitle,
            lastDistributionTime: lastDistributionTime,
            now: now,
            defaultFallbackInterval: defaultFallbackInterval,
            messagingFallbackInterval: messagingFallbackInterval,
            messagingFastPathApps: messagingFastPathApps
        )

        switch decision {
        case .flushNow:
            return .flushNow
        case .debounce:
            // Track the pending context immediately so repeated captures in that same
            // context do not starve the debounce timer by rescheduling forever.
            lastDistributedApp = frameApp
            lastDistributedWindowTitle = frameWindowTitle
            return .scheduleDebounce
        case .skip:
            return .skip
        }
    }

    mutating func markFlushed(
        frameApp: String,
        frameWindowTitle: String?,
        at time: Date
    ) {
        lastDistributedApp = frameApp
        lastDistributedWindowTitle = frameWindowTitle
        lastDistributionTime = time
    }
}
