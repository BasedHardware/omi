import SwiftUI
#if canImport(UIKit)
    import UIKit

    /// Lets the edge swipe back win over the detail's pager: placed inside a page, it finds the
    /// pager's scroll view and makes its pan wait for the navigation controller's edge gesture.
    /// A swipe that starts away from the edge still pages at once.
    struct EdgeSwipeBackFirst: UIViewRepresentable {
        func makeUIView(context _: Context) -> BridgeView {
            BridgeView()
        }

        func updateUIView(_: BridgeView, context _: Context) {}

        final class BridgeView: UIView {
            override func didMoveToWindow() {
                super.didMoveToWindow()
                guard window != nil else { return }
                // The pager and the navigation controller are in place one turn later.
                Task { @MainActor [weak self] in self?.link() }
            }

            private func link() {
                var view = superview
                var pager: UIScrollView?
                while let current = view {
                    // The pager: paging, or at least clearly wider than it is shown (two pages side by side).
                    if let scroll = current as? UIScrollView,
                       scroll.isPagingEnabled || scroll.contentSize.width > scroll.bounds.width * 1.5
                    {
                        pager = scroll
                        break
                    }
                    view = current.superview
                }
                var responder: UIResponder? = self
                var navigation: UINavigationController?
                while let current = responder {
                    if let found = current as? UINavigationController {
                        navigation = found
                        break
                    }
                    responder = current.next
                }
                guard let pager, let edge = navigation?.interactivePopGestureRecognizer else { return }
                pager.panGestureRecognizer.require(toFail: edge)
            }
        }
    }
#else
    struct EdgeSwipeBackFirst: View {
        var body: some View {
            EmptyView()
        }
    }
#endif
