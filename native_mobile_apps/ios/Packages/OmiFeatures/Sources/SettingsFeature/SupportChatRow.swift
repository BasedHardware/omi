import OmiDesign
import SwiftUI

/// Opens the support chat (Intercom, set by the app when the build has its keys).
public struct SupportChatAction: Sendable {
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
    /// Nil when the build has no Intercom keys.
    @Entry var supportChat: SupportChatAction?
}

/// "Need help? Chat with us" (Flutter's Help and feedback sheet), only when the support chat is
/// configured; otherwise nothing, and the help center and feedback links stand alone.
struct SupportChatRow: View {
    @Environment(\.supportChat) private var supportChat

    var body: some View {
        if let supportChat {
            Button(L("needHelpChatWithUs")) { supportChat() }
                .accessibilityIdentifier("help.supportChat")
        }
    }
}
