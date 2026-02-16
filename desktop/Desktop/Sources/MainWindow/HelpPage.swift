import SwiftUI
import WebKit

struct HelpPage: View {
    var body: some View {
        CrispWebView()
            .ignoresSafeArea()
    }
}

struct CrispWebView: NSViewRepresentable {
    private let websiteID = "0dcf3d1f-863d-4576-a534-31f2bb102ae5"

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        // Register JS message handler for incoming Crisp messages
        config.userContentController.add(context.coordinator, name: "crispMessage")

        // Inject script that listens for Crisp messages and forwards to Swift
        let script = WKUserScript(source: """
            (function() {
                var checkCrisp = setInterval(function() {
                    if (window.$crisp) {
                        clearInterval(checkCrisp);
                        $crisp.push(["on", "message:received", function(data) {
                            var text = "";
                            if (data && data.content) {
                                text = data.content;
                            } else if (typeof data === "string") {
                                text = data;
                            }
                            window.webkit.messageHandlers.crispMessage.postMessage(text);
                        }]);
                    }
                }, 500);
            })();
            """, injectionTime: .atDocumentEnd, forMainFrameOnly: false)
        config.userContentController.addUserScript(script)

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        context.coordinator.webView = webView

        var urlString = "https://go.crisp.chat/chat/embed/?website_id=\(websiteID)"
        if let email = AuthState.shared.userEmail,
           let encodedEmail = email.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            urlString += "&user_email=\(encodedEmail)"
        }
        let name = AuthService.shared.displayName
        if !name.isEmpty,
           let encodedName = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            urlString += "&user_nickname=\(encodedName)"
        }

        if let url = URL(string: urlString) {
            webView.load(URLRequest(url: url))
        }
        return webView
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}

    class Coordinator: NSObject, WKScriptMessageHandler {
        weak var webView: WKWebView?

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard message.name == "crispMessage" else { return }

            let text = (message.body as? String) ?? "New message"
            let preview = text.count > 100 ? String(text.prefix(100)) + "..." : text

            log("Crisp: received message from founder")

            Task { @MainActor in
                // Only notify if the app is not focused on the Help page
                let isAppActive = NSApp.isActive
                let isHelpVisible = NSApp.keyWindow?.contentView?
                    .subviews.first(where: { String(describing: type(of: $0)).contains("WKWebView") }) != nil

                if !isAppActive || !isHelpVisible {
                    NotificationService.shared.sendNotification(
                        title: "Help from Founder",
                        message: preview,
                        assistantId: "crisp"
                    )
                }
            }
        }
    }
}
