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

        // Inject a MutationObserver that watches for new operator messages in the DOM.
        // The Crisp embed renders operator messages with data-from="operator".
        // We also try the $crisp JS SDK as a fallback.
        let script = WKUserScript(source: """
            (function() {
                var notified = {};

                // Approach 1: MutationObserver on the DOM for operator messages
                function watchDOM() {
                    var observer = new MutationObserver(function(mutations) {
                        mutations.forEach(function(m) {
                            m.addedNodes.forEach(function(node) {
                                if (node.nodeType !== 1) return;
                                // Look for operator messages (Crisp uses data-from="operator")
                                var msgs = [];
                                if (node.getAttribute && node.getAttribute("data-from") === "operator") {
                                    msgs.push(node);
                                }
                                msgs = msgs.concat(Array.from(node.querySelectorAll ? node.querySelectorAll("[data-from='operator']") : []));
                                msgs.forEach(function(el) {
                                    var text = (el.textContent || "").trim();
                                    var key = text.substring(0, 80);
                                    if (text && !notified[key]) {
                                        notified[key] = true;
                                        try {
                                            window.webkit.messageHandlers.crispMessage.postMessage(text);
                                        } catch(e) {}
                                    }
                                });
                            });
                        });
                    });
                    observer.observe(document.body || document.documentElement, { childList: true, subtree: true });
                }

                // Approach 2: $crisp SDK events (if available)
                function watchCrispSDK() {
                    var attempts = 0;
                    var check = setInterval(function() {
                        attempts++;
                        if (attempts > 60) { clearInterval(check); return; }
                        if (window.$crisp) {
                            clearInterval(check);
                            try {
                                $crisp.push(["on", "message:received", function(data) {
                                    var text = "";
                                    if (data && data.content) text = data.content;
                                    else if (typeof data === "string") text = data;
                                    if (text) {
                                        try {
                                            window.webkit.messageHandlers.crispMessage.postMessage(text);
                                        } catch(e) {}
                                    }
                                }]);
                            } catch(e) {}
                        }
                    }, 500);
                }

                if (document.body) {
                    watchDOM();
                } else {
                    document.addEventListener("DOMContentLoaded", watchDOM);
                }
                watchCrispSDK();
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
        /// Track recent messages to avoid duplicate notifications
        private var recentMessages = Set<String>()

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard message.name == "crispMessage" else { return }

            let text = (message.body as? String) ?? "New message"
            let key = String(text.prefix(80))

            // Deduplicate
            guard !recentMessages.contains(key) else { return }
            recentMessages.insert(key)

            let preview = text.count > 100 ? String(text.prefix(100)) + "..." : text

            log("Crisp: received operator message: \(preview)")

            Task { @MainActor in
                log("Crisp: sending macOS notification for: \(preview)")
                NotificationService.shared.sendNotification(
                    title: "Help from Founder",
                    message: preview,
                    assistantId: "crisp"
                )
            }
        }
    }
}
