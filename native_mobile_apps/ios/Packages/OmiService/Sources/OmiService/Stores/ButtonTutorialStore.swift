import Foundation
import Observation
import OmiDevice

/// The Omi button lessons (Flutter `DeviceOnboardingProvider`, steps single press and double press):
/// while one runs, the Omi's button events come here first. Asking practises the real thing (the
/// question goes to `v2/voice-messages`, the answer can be read aloud); double press only counts
/// the presses and saves the chosen action, so practice never ends, mutes or stars anything.
@MainActor
@Observable
public final class ButtonTutorialStore {
    public enum Lesson: Equatable, Sendable {
        /// Press once, ask, press again.
        case ask
        /// Pick what a double press does, then try it.
        case doublePress
    }

    public private(set) var lesson: Lesson?
    /// Double presses since the action was picked.
    public private(set) var doublePresses = 0
    /// The last press on the double-press lesson was a single one.
    public private(set) var singlePressHint = false

    public let devices: DeviceStore
    public let askOmi: AskOmiStore

    public init(devices: DeviceStore, askOmi: AskOmiStore) {
        self.devices = devices
        self.askOmi = askOmi
    }

    /// The action double press runs: the same setting as My Devices › Controls.
    public var doublePressAction: DoubleTapAction {
        devices.doubleTapAction
    }

    public func begin(_ lesson: Lesson) {
        self.lesson = lesson
        doublePresses = 0
        singlePressHint = false
        askOmi.isPractice = lesson == .ask
        devices.buttonInterceptor = { [weak self] event in
            self?.handle(event) ?? false
        }
    }

    /// Ends `only` (when given) or whichever lesson runs; a step leaving after the next one began
    /// does not end the new one.
    public func end(_ only: Lesson? = nil) {
        guard lesson != nil, only == nil || only == lesson else { return }
        lesson = nil
        askOmi.isPractice = false
        devices.buttonInterceptor = nil
    }

    /// Picking starts the count over (Flutter `selectDoubleTapAction`).
    public func choose(_ action: DoubleTapAction) {
        devices.doubleTapAction = action
        doublePresses = 0
        singlePressHint = false
    }

    /// Every button event while a lesson runs; always consumed.
    func handle(_ event: OmiGATT.ButtonEvent) -> Bool {
        switch lesson {
        case .ask:
            switch event {
            case .singleTap: askOmi.handle(.askToggle)
            case .longPress: askOmi.handle(.askHoldStart)
            case .release: askOmi.handle(.askHoldEnd)
            case .doubleTap, .press: break
            }
        case .doublePress:
            switch event {
            case .singleTap:
                singlePressHint = true
            case .doubleTap:
                singlePressHint = false
                doublePresses += 1
            case .longPress, .release, .press:
                break
            }
        case nil:
            return false
        }
        return true
    }
}
