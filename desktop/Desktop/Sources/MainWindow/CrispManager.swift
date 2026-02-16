import Foundation
import WebKit

/// Persistent manager that keeps a Crisp chat WKWebView alive in the background,
/// listens for incoming operator messages, fires macOS notifications, and tracks unread count.
@MainActor
class CrispManager: NSObject, ObservableObject, WKScriptMessageHandler {
    static let shared = CrispManager()

    private let websiteID = "0dcf3d1f-863d-4576-a534-31f2bb102ae5"

    /// The persistent webview — kept alive for the lifetime of the app
    private(set) var webView: WKWebView!

    /// Number of unread operator messages (shown as badge in sidebar)
    @Published private(set) var unreadCount = 0

    /// Whether the user is currently viewing the Help tab
    var isViewingHelp = false {
        didSet {
            if isViewingHelp {
                unreadCount = 0
            }
        }
    }

    /// Track message keys to avoid duplicate notifications
    private var seenMessages = Set<String>()

    /// Whether initial page load has completed (skip notifications for pre-existing messages)
    private var initialLoadComplete = false

    private override init() {
        super.init()
    }

    /// Call once after sign-in to start loading the Crisp chat in the background
    func start() {
        guard webView == nil else { return }

        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true

        // Register JS→Swift bridge
        config.userContentController.add(self, name: "crispMessage")
        config.userContentController.add(self, name: "crispReady")

        // Inject MutationObserver + $crisp SDK listener
        let script = WKUserScript(source: """
            (function() {
                var notified = {};

                // Watch DOM for new operator messages
                function watchDOM() {
                    var observer = new MutationObserver(function(mutations) {
                        mutations.forEach(function(m) {
                            m.addedNodes.forEach(function(node) {
                                if (node.nodeType !== 1) return;
                                var msgs = [];
                                if (node.getAttribute && node.getAttribute("data-from") === "operator") {
                                    msgs.push(node);
                                }
                                if (node.querySelectorAll) {
                                    var found = node.querySelectorAll("[data-from='operator']");
                                    for (var i = 0; i < found.length; i++) msgs.push(found[i]);
                                }
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

                // Also try $crisp SDK events
                function watchCrispSDK() {
                    var attempts = 0;
                    var check = setInterval(function() {
                        attempts++;
                        if (attempts > 60) { clearInterval(check); return; }
                        if (window.$crisp) {
                            clearInterval(check);
                            // Signal that Crisp SDK is ready (initial load done)
                            try {
                                window.webkit.messageHandlers.crispReady.postMessage("ready");
                            } catch(e) {}
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

        let wv = WKWebView(frame: CGRect(x: 0, y: 0, width: 1, height: 1), configuration: config)
        wv.setValue(false, forKey: "drawsBackground")
        self.webView = wv

        loadCrispPage()
        log("CrispManager: started, loading Crisp in background")
    }

    private func loadCrispPage() {
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
    }

    /// Mark messages as read (called when user opens Help tab)
    func markAsRead() {
        unreadCount = 0
    }

    // MARK: - WKScriptMessageHandler

    nonisolated func userContentController(_ userContentController: WKUserContentController,
                                           didReceive message: WKScriptMessage) {
        Task { @MainActor in
            if message.name == "crispReady" {
                // Crisp SDK fully loaded — from now on, new messages are real-time
                log("CrispManager: Crisp SDK ready, initial load complete")
                // Small delay to let any pre-existing messages render first
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    self.initialLoadComplete = true
                    log("CrispManager: now listening for new messages")
                }
                return
            }

            guard message.name == "crispMessage" else { return }

            let text = (message.body as? String) ?? "New message"
            let key = String(text.prefix(80))

            // Deduplicate
            guard !seenMessages.contains(key) else { return }
            seenMessages.insert(key)

            // Skip notifications for pre-existing messages on initial load
            guard initialLoadComplete else {
                log("CrispManager: skipping pre-existing message: \(String(text.prefix(50)))")
                return
            }

            let preview = text.count > 100 ? String(text.prefix(100)) + "..." : text
            log("CrispManager: new operator message: \(preview)")

            // Update unread count if not currently viewing help
            if !isViewingHelp {
                unreadCount += 1
            }

            // Always send macOS notification for new messages
            NotificationService.shared.sendNotification(
                title: "Help from Founder",
                message: preview,
                assistantId: "crisp"
            )
        }
    }
}
