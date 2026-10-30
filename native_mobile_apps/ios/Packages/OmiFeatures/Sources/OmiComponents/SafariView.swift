import SafariServices
import SwiftUI

/// In-app browser (Stripe checkout and portal, help pages).
public struct SafariView: UIViewControllerRepresentable {
    let url: URL

    public init(url: URL) {
        self.url = url
    }

    public func makeUIViewController(context _: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    public func updateUIViewController(_: SFSafariViewController, context _: Context) {}
}

/// Identifiable wrapper for `.sheet(item:)`.
public struct BrowserItem: Identifiable {
    public let url: URL
    public var id: String {
        url.absoluteString
    }

    public init(_ url: URL) {
        self.url = url
    }
}
