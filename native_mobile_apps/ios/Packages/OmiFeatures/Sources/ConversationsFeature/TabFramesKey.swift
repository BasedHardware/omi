import SwiftUI

/// The detail page's tab labels and their frames in the tab row, for the sliding underline.
struct TabFramesKey: PreferenceKey {
    static let defaultValue: [ConversationDetailScreen.Page: CGRect] = [:]

    static func reduce(value: inout [ConversationDetailScreen.Page: CGRect], nextValue: () -> [ConversationDetailScreen.Page: CGRect]) {
        value.merge(nextValue()) { $1 }
    }
}
