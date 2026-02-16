import SwiftUI
import WebKit

struct HelpPage: View {
    var body: some View {
        CrispWebView()
            .ignoresSafeArea()
            .onAppear {
                CrispManager.shared.isViewingHelp = true
            }
            .onDisappear {
                CrispManager.shared.isViewingHelp = false
            }
    }
}

/// Displays the persistent Crisp WKWebView from CrispManager.
/// Uses Auto Layout constraints so the webview fills the container even when
/// the container's initial bounds are zero (which is the case in makeNSView).
struct CrispWebView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let container = NSView()
        guard let webView = CrispManager.shared.webView else { return container }

        // Reparent: remove from previous container if needed
        webView.removeFromSuperview()

        webView.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            webView.topAnchor.constraint(equalTo: container.topAnchor),
            webView.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
        return container
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}
