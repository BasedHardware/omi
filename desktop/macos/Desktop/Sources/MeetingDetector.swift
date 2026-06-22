import AppKit
import Foundation

/// Detects whether a conferencing call ("meeting") is currently active by scanning on-screen
/// windows for known call apps (see `ConferencingApps`).
///
/// Used to gate system-audio capture in "Only during meetings" mode. It is created and started
/// **only** while a recording is active in that mode, so there is zero overhead otherwise.
///
/// Transitions **on** as soon as a call is detected, but transitions **off** only after a grace
/// period of sustained "no meeting" (hysteresis) to avoid flapping when a call window briefly
/// disappears (focus changes, screen-share popups, etc.).
@MainActor
final class MeetingDetector {

    /// Current meeting state. Updated on the main actor by `applyDetected(_:)`.
    private(set) var isMeetingActive: Bool = false

    private let pollInterval: TimeInterval
    private let offGracePeriod: TimeInterval
    private let isMeetingNow: () -> Bool
    private let now: () -> Date
    private let onChange: (Bool) -> Void

    private var timer: Timer?
    private var workspaceObservers: [NSObjectProtocol] = []
    /// When the call first goes undetected, the time at which we will actually flip to inactive.
    /// `nil` whenever a meeting is detected or no pending-off is in progress.
    private var pendingOffDeadline: Date?
    private var started = false

    /// - Parameters:
    ///   - pollInterval: how often to re-probe (browser tab-title changes only surface via the poll).
    ///   - offGracePeriod: sustained "no meeting" time required before flipping off.
    ///   - isMeetingNow: conferencing-call probe (injectable for tests). Default: a native or browser
    ///     app using the mic (macOS 14.4+), or a browser call window (window-title fallback).
    ///   - now: clock (injectable for tests).
    ///   - onChange: called on the main actor whenever `isMeetingActive` flips.
    init(
        pollInterval: TimeInterval = 4.0,
        offGracePeriod: TimeInterval = 8.0,
        isMeetingNow: @escaping () -> Bool = {
            if #available(macOS 14.4, *), ConferencingApps.callAppIsUsingMicrophone() { return true }
            return ConferencingApps.browserCallWindowPresent()
        },
        now: @escaping () -> Date = { Date() },
        onChange: @escaping (Bool) -> Void
    ) {
        self.pollInterval = pollInterval
        self.offGracePeriod = offGracePeriod
        self.isMeetingNow = isMeetingNow
        self.now = now
        self.onChange = onChange
    }

    /// Begin observing app launch/terminate/activation and polling. Emits the initial state
    /// synchronously so callers can read `isMeetingActive` immediately after `start()`.
    func start() {
        guard !started else { return }
        started = true

        let nc = NSWorkspace.shared.notificationCenter
        for name in [
            NSWorkspace.didActivateApplicationNotification,
            NSWorkspace.didLaunchApplicationNotification,
            NSWorkspace.didTerminateApplicationNotification,
        ] {
            let observer = nc.addObserver(forName: name, object: nil, queue: .main) {
                [weak self] _ in
                Task { @MainActor in self?.tick() }
            }
            workspaceObservers.append(observer)
        }

        timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) {
            [weak self] _ in
            Task { @MainActor in self?.tick() }
        }

        // Establish the initial state. The probe runs off the main actor and is applied
        // asynchronously (and surfaced via onChange), so the caller's gate converges shortly after.
        tick()
        log("MeetingDetector: started (poll=\(pollInterval)s, offGrace=\(offGracePeriod)s)")
    }

    /// Stop all observation. Resets pending-off state; `isMeetingActive` is left as-is.
    func stop() {
        guard started else { return }
        started = false

        timer?.invalidate()
        timer = nil

        let nc = NSWorkspace.shared.notificationCenter
        for observer in workspaceObservers {
            nc.removeObserver(observer)
        }
        workspaceObservers.removeAll()
        pendingOffDeadline = nil
        log("MeetingDetector: stopped")
    }

    /// Probe for an active call off the main actor — the CoreAudio process scan / CGWindowList query
    /// can block (notably right after wake) — then apply the result back on the main actor.
    private func tick() {
        let probe = isMeetingNow
        Task.detached(priority: .utility) { [weak self] in
            let detected = probe()
            await MainActor.run { self?.applyDetected(detected) }
        }
    }

    /// Apply a boolean detection result, honoring the off-hysteresis. Exposed for tests; normally
    /// driven by the poll timer and workspace notifications via `tick()`.
    func applyDetected(_ detected: Bool) {
        if detected {
            // Meeting present: cancel any pending-off and ensure we're active.
            pendingOffDeadline = nil
            setActive(true)
        } else if isMeetingActive {
            // Meeting undetected while active: arm or honor the off grace period.
            if let deadline = pendingOffDeadline {
                if now() >= deadline {
                    pendingOffDeadline = nil
                    setActive(false)
                }
            } else {
                pendingOffDeadline = now().addingTimeInterval(offGracePeriod)
            }
        } else {
            // Already inactive and still no meeting.
            pendingOffDeadline = nil
        }
    }

    private func setActive(_ active: Bool) {
        guard active != isMeetingActive else { return }
        isMeetingActive = active
        log("MeetingDetector: meeting \(active ? "STARTED" : "ENDED")")
        onChange(active)
    }
}
