import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// What the system share sheet is opened with, and what happens once it closes.
struct ShareRequest: Identifiable {
    let id = UUID()
    let items: [Any]
    /// `true` when something was actually shared.
    var onFinish: @MainActor @Sendable (Bool) -> Void = { _ in }
}

#if canImport(UIKit)
    /// The system share sheet; reports whether the user shared or dismissed it.
    struct ShareSheet: UIViewControllerRepresentable {
        let request: ShareRequest

        func makeUIViewController(context _: Context) -> UIActivityViewController {
            let controller = UIActivityViewController(activityItems: request.items, applicationActivities: nil)
            let onFinish = request.onFinish
            controller.completionWithItemsHandler = { _, completed, _, _ in
                MainActor.assumeIsolated { onFinish(completed) }
            }
            return controller
        }

        func updateUIViewController(_: UIActivityViewController, context _: Context) {}
    }
#endif
