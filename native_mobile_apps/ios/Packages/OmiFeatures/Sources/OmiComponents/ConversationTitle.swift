import OmiCore
import OmiDesign

public extension Conversation {
    /// The title, else "Discarded Conversation" or "Untitled conversation".
    var displayTitle: String {
        guard title.isEmpty else { return title }
        return isDiscarded ? L("discardedConversation") : L("untitledConversation")
    }
}
