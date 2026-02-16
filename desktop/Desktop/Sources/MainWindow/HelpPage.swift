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

/// Displays the persistent Crisp WKWebView from CrispManager
struct CrispWebView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let container = NSView()
        if let webView = CrispManager.shared.webView {
            webView.frame = container.bounds
            webView.autoresizingMask = [.width, .height]
            container.addSubview(webView)
        }
        return container
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        // Ensure webview fills container on layout changes
        if let webView = CrispManager.shared.webView {
            webView.frame = nsView.bounds
        }
    }
}
