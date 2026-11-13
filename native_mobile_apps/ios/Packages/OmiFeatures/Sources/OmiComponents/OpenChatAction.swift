import SwiftUI

/// Opens the chat from a feature that cannot present it itself (an app page in Settings: the
/// shell closes Settings, then shows the chat). Set by `SettingsScreen` from the shell's closure.
public struct OpenChatAction: Sendable {
    private let action: @MainActor () -> Void

    public init(_ action: @escaping @MainActor () -> Void) {
        self.action = action
    }

    @MainActor
    public func callAsFunction() {
        action()
    }
}

public extension EnvironmentValues {
    @Entry var openChat = OpenChatAction {}
}
