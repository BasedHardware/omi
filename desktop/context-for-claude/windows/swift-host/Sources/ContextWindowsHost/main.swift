import CContextCore
import Foundation
import WindowsFoundation

@main
struct ContextWindowsHost {
    static func main() {
        print("Context for Claude — Windows host")
        print("Core version: \(String(cString: ctx_core_version()))")

        let gap = ctx_session_default_gap_seconds()
        print("Session gap: \(gap) seconds")

        let opensNew = ctx_should_open_new_session(1, 0, gap + 1, gap)
        print("Gap+1s opens new session: \(opensNew != 0)")

        let continues = ctx_should_open_new_session(1, 0, gap - 1, gap)
        print("Gap-1s continues session: \(continues == 0)")

        let score = ctx_recall_score(1.0, 0.8, 0)
        print("Recall score (full coverage, 0.8 lexical, now): \(score)")

        let floor = ctx_relevance_floor(score)
        print("Relevance floor: \(floor)")

        // WinRT: prove the projection is linked by constructing a Uri.
        // Windows.Foundation.Uri is the canonical "hello WinRT" type.
        if let uri = try? WindowsFoundation.Uri("ms-appx:///ContextWindowsHost") {
            print("WinRT projection: Uri domain = \(uri.domain)")
        }
    }
}
