import Foundation

/// Selects honest Home copy from the amount of context Omi can actually use.
/// The dashboard must never imply that a new or temporarily-offline account
/// already has personal history.
struct HomeValueSnapshot: Equatable, Sendable {
  enum Experience: String, Equatable, Sendable {
    case loading
    case gettingStarted = "getting_started"
    case building
    case established
  }

  let experience: Experience
  let title: String
  let subtitle: String
  let askHeading: String
  let askPlaceholder: String
  let availableContextSourceCount: Int

  static func metricValue(for count: Int?) -> String {
    count?.formatted() ?? "—"
  }

  static func make(
    conversationCount: Int?,
    memoryCount: Int?,
    screenshotCount: Int?
  ) -> HomeValueSnapshot {
    let counts = [conversationCount, memoryCount, screenshotCount]
    let availableContextSourceCount = counts.compactMap { $0 }.filter { $0 > 0 }.count

    let experience: Experience
    if counts.allSatisfy({ $0 == nil }) {
      experience = .loading
    } else if counts.compactMap({ $0 }).allSatisfy({ $0 == 0 }) {
      experience = .gettingStarted
    } else if (conversationCount ?? 0) >= 5
      || (memoryCount ?? 0) >= 10
      || (screenshotCount ?? 0) >= 100
      || availableContextSourceCount >= 2
    {
      experience = .established
    } else {
      experience = .building
    }

    switch experience {
    case .loading:
      return HomeValueSnapshot(
        experience: experience,
        title: "Your context is coming together.",
        subtitle:
          "Omi connects what happens on your computer with what you say in real life, then makes it useful in one conversation.",
        askHeading: "Ask your second brain",
        askPlaceholder: "Ask about your work or life",
        availableContextSourceCount: availableContextSourceCount
      )
    case .gettingStarted:
      return HomeValueSnapshot(
        experience: experience,
        title: "Ask one question only your Omi could answer.",
        subtitle:
          "Omi learns from your computer and real-life conversations, then remembers the details you shouldn't have to.",
        askHeading: "Start with what's happening now",
        askPlaceholder: "What on my screen matters most right now?",
        availableContextSourceCount: availableContextSourceCount
      )
    case .building:
      return HomeValueSnapshot(
        experience: experience,
        title: "Your second brain is taking shape.",
        subtitle:
          "Omi is connecting your computer, conversations, and memories so every answer gets more personal.",
        askHeading: "Try Omi with your context",
        askPlaceholder: "Ask what Omi remembers",
        availableContextSourceCount: availableContextSourceCount
      )
    case .established:
      return HomeValueSnapshot(
        experience: experience,
        title: "Omi already knows the backstory.",
        subtitle:
          "Ask about your work or life. Omi answers from your computer, conversations, and memories, not a blank chat.",
        askHeading: "Ask with your context",
        askPlaceholder: "Ask about something you saw, said, or promised",
        availableContextSourceCount: availableContextSourceCount
      )
    }
  }
}
