#if canImport(UIKit)
    import SwiftUI
    import UIKit

    /// A sideways drag in one direction only (a chat bubble's reply swipe, a Home card's "Later"):
    /// it begins only for a move that is clearly sideways in `direction`, and the scroll views
    /// around it (a thread, the tab pages) wait for it to fail first, so scrolling and paging keep
    /// working as before.
    public struct SidewaysPan: UIGestureRecognizerRepresentable {
        /// -1: leftward; 1: rightward.
        let direction: CGFloat
        let onChange: (CGFloat) -> Void
        /// The final translation and velocity along x.
        let onEnd: (_ translation: CGFloat, _ velocity: CGFloat) -> Void

        public init(
            direction: CGFloat, onChange: @escaping (CGFloat) -> Void,
            onEnd: @escaping (_ translation: CGFloat, _ velocity: CGFloat) -> Void
        ) {
            self.direction = direction
            self.onChange = onChange
            self.onEnd = onEnd
        }

        public func makeCoordinator(converter _: CoordinateSpaceConverter) -> Coordinator {
            Coordinator()
        }

        public func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
            let pan = UIPanGestureRecognizer()
            pan.delegate = context.coordinator
            context.coordinator.direction = direction
            return pan
        }

        public func updateUIGestureRecognizer(_: UIPanGestureRecognizer, context: Context) {
            context.coordinator.direction = direction
        }

        public func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context _: Context) {
            switch recognizer.state {
            case .began, .changed: onChange(recognizer.translation(in: recognizer.view).x)
            case .ended: onEnd(recognizer.translation(in: recognizer.view).x, recognizer.velocity(in: recognizer.view).x)
            case .cancelled, .failed: onEnd(0, 0)
            default: break
            }
        }

        @MainActor
        public final class Coordinator: NSObject, UIGestureRecognizerDelegate {
            var direction: CGFloat = 1

            public func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
                guard let pan = recognizer as? UIPanGestureRecognizer else { return false }
                let move = pan.translation(in: pan.view)
                let velocity = pan.velocity(in: pan.view)
                let dx = move.x == 0 ? velocity.x : move.x
                let dy = move.y == 0 ? velocity.y : move.y
                return dx * direction > 0 && abs(dx) > abs(dy) * 1.5
            }

            public func gestureRecognizer(_: UIGestureRecognizer, shouldBeRequiredToFailBy other: UIGestureRecognizer) -> Bool {
                other.view is UIScrollView && other is UIPanGestureRecognizer
            }
        }
    }
#endif
