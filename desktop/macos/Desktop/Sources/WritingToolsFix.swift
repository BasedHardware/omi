import SwiftUI

extension View {
    /// Disables Apple Intelligence writing tools (summarization, etc.) on macOS 15.1+.
    /// Prevents 100%+ CPU caused by `_IntelligenceSupportMakeSummarySymbol` on selectable text.
    @ViewBuilder
    func if_available_writingToolsNone() -> some View {
        if #available(macOS 15.1, *) {
            self.writingToolsBehavior(.disabled)
        } else {
            self
        }
    }
}
