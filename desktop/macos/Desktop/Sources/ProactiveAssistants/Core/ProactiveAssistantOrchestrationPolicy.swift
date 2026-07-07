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
