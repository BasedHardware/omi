import Foundation
import OmiDevice

/// What a double tap on the Omi does. Raw values are the Flutter app's `doubleTapAction`
/// preference (`device_control_sheets.dart`): 0 end and process, 1 mute/unmute, 2 star.
public enum DoubleTapAction: Int, CaseIterable, Sendable {
    case endConversation = 0
    case toggleMute = 1
    case star = 2
}

/// What the app does for a button event (`capture_controller.dart` `_handleButtonEvent`).
public enum ButtonAction: Equatable, Sendable {
    case endConversation
    /// Stars the conversation when it ends; a second double tap takes the star back.
    case toggleStar
    case toggleMute
    /// Single press: start a question, or send it on the next press.
    case askToggle
    /// Older firmware: a long press records a question until the button is released.
    case askHoldStart
    case askHoldEnd
}

public extension ButtonAction {
    /// Routes a firmware button event. With button actions off nothing happens; a plain
    /// press/release (sent around every tap) only matters to a question held since a long press.
    static func route(_ event: OmiGATT.ButtonEvent, doubleTap: DoubleTapAction, actionsEnabled: Bool) -> ButtonAction? {
        guard actionsEnabled else { return nil }
        switch event {
        case .singleTap:
            return .askToggle
        case .doubleTap:
            switch doubleTap {
            case .endConversation: return .endConversation
            case .toggleMute: return .toggleMute
            case .star: return .toggleStar
            }
        case .longPress:
            return .askHoldStart
        case .release:
            return .askHoldEnd
        case .press:
            return nil
        }
    }
}
