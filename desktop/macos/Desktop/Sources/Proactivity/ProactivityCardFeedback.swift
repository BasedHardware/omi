import SwiftUI

struct ProactivityCardFeedback: View {
  let onInteraction: ((NotificationInteraction) -> Void)?
  @State private var feedback: NotificationInteraction?

  var body: some View {
    HStack {
      OmiIconButton("hand.thumbsup", help: "Helpful", size: .compact, isActive: feedback == .thumbsUp) {
        feedback = .thumbsUp
        onInteraction?(.thumbsUp)
      }
      OmiIconButton("hand.thumbsdown", help: "Not helpful", size: .compact, isActive: feedback == .thumbsDown) {
        feedback = .thumbsDown
        onInteraction?(.thumbsDown)
      }
    }
  }
}
