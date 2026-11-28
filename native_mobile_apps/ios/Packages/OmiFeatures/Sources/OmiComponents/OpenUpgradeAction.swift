import SwiftUI

/// Opens the plans (Account › plan) from a feature that cannot present Settings itself: a locked
/// conversation's "Upgrade to Unlimited". Set by the app shell.
public struct OpenUpgradeAction: Sendable {
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
    @Entry var openUpgrade = OpenUpgradeAction {}
}
