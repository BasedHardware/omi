import OmiTheme
import SwiftUI
import WebKit

struct BillingWebFlow: Identifiable {
  let id = UUID()
  let title: String
  let url: URL
  let completionURLs: [String]
  var purchase: PurchaseCheckoutObservation? = nil
}

enum BillingWebFlowOutcome {
  case completed
  case cancelled
  case dismissed
}

struct BillingWebFlowSheet: View {
  let flow: BillingWebFlow
  let onComplete: (BillingWebFlowOutcome) -> Void

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: OmiSpacing.md) {
        Text(flow.title)
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Spacer()

        Button("Close") {
          flow.purchase?.finish(success: false)
          onComplete(.dismissed)
        }
        .buttonStyle(OmiButtonStyle(.primary, size: .compact))
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.lg)
      .background(Ink.rowFill)

      GlassSeparator()

      BillingWebView(flow: flow, onComplete: onComplete)
        .frame(minWidth: 860, minHeight: 680)
        .onAppear { flow.purchase?.opened() }
    }
    .background(Ink.surface)
    .onDisappear { flow.purchase?.finish(success: false) }
  }
}

struct BillingWebView: NSViewRepresentable {
  let flow: BillingWebFlow
  let onComplete: (BillingWebFlowOutcome) -> Void

  func makeCoordinator() -> Coordinator {
    Coordinator(flow: flow, onComplete: onComplete)
  }

  func makeNSView(context: Context) -> WKWebView {
    let configuration = WKWebViewConfiguration()
    configuration.defaultWebpagePreferences.allowsContentJavaScript = true

    let webView = WKWebView(frame: .zero, configuration: configuration)
    webView.navigationDelegate = context.coordinator
    webView.uiDelegate = context.coordinator
    webView.setValue(false, forKey: "drawsBackground")
    webView.load(URLRequest(url: flow.url))
    return webView
  }

  func updateNSView(_ nsView: WKWebView, context: Context) {}

  final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
    let flow: BillingWebFlow
    let onComplete: (BillingWebFlowOutcome) -> Void
    var completionHandled = false
    let purchase: PurchaseCheckoutObservation?

    init(flow: BillingWebFlow, onComplete: @escaping (BillingWebFlowOutcome) -> Void) {
      self.purchase = flow.purchase
      self.flow = flow
      self.onComplete = onComplete
    }

    @MainActor
    func webView(
      _ webView: WKWebView,
      decidePolicyFor navigationAction: WKNavigationAction,
      decisionHandler: @escaping @MainActor @Sendable (WKNavigationActionPolicy) -> Void
    ) {
      guard let url = navigationAction.request.url else {
        decisionHandler(.allow)
        return
      }

      if let matchedCompletionURL = flow.completionURLs.compactMap(URL.init(string:)).first(where: {
        PurchaseCheckoutObservation.matches(url, completionURL: $0)
      }) {
        if matchedCompletionURL.pathComponents.last == "cancel" {
          finish(.cancelled)
        } else {
          finish(.completed)
        }
        decisionHandler(.cancel)
        return
      }

      decisionHandler(.allow)
    }

    func webView(
      _ webView: WKWebView,
      createWebViewWith configuration: WKWebViewConfiguration,
      for navigationAction: WKNavigationAction,
      windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
      if navigationAction.targetFrame == nil, let requestURL = navigationAction.request.url {
        webView.load(URLRequest(url: requestURL))
      }
      return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
      purchase?.finish(success: false)
    }
    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
      purchase?.finish(success: false)
    }

    func finish(_ outcome: BillingWebFlowOutcome) {
      guard !completionHandled else { return }
      completionHandled = true
      if case .completed = outcome { purchase?.finish(success: true) } else { purchase?.finish(success: false) }
      DispatchQueue.main.async {
        self.onComplete(outcome)
      }
    }
  }
}
