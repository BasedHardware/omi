import Foundation

/// One upcoming meeting distilled to just what the opener greeting needs.
struct OnboardingMeetingBrief: Equatable {
  let title: String
  /// Display time already formatted for the user's locale (e.g. "2:00 PM").
  let time: String
}

/// The personalized first beat shown in the Chat tab the instant onboarding
/// finishes: a greeting addressed to the user by name + tappable starter
/// questions that fire real Omi queries.
struct OnboardingOpenerContent: Equatable {
  /// Short headline: time of day + name ("Afternoon, Nik").
  let greeting: String
  /// Muted detail line under the headline: today's meetings + listening state.
  let subline: String
  let starters: [String]
}

/// Pure, deterministic composer for the post-onboarding opener. Kept free of
/// any live service or `@MainActor` state so it renders instantly at the
/// fragile handoff moment and is fully unit-testable. The caller supplies the
/// live inputs (name, listening mode, today's meetings, base starter chips).
enum OnboardingOpenerComposer {
  enum ListeningMode: Equatable { case always, meetingsOnly }

  static let maxStarters = 3

  static func timeOfDay(_ date: Date, calendar: Calendar = .current) -> String {
    switch calendar.component(.hour, from: date) {
    case 5..<12: return "Morning"
    case 12..<17: return "Afternoon"
    default: return "Evening"
    }
  }

  static func compose(
    name: String,
    mode: ListeningMode,
    meetings: [OnboardingMeetingBrief],
    now: Date,
    baseStarters: [String],
    calendar: Calendar = .current
  ) -> OnboardingOpenerContent {
    OnboardingOpenerContent(
      greeting: greeting(name: name, now: now, calendar: calendar),
      subline: subline(mode: mode, meetings: meetings),
      starters: starters(meetings: meetings, baseStarters: baseStarters)
    )
  }

  /// Short headline only — the detail moved to `subline` so the headline can
  /// render large without wrapping into a paragraph.
  static func greeting(name: String, now: Date, calendar: Calendar = .current) -> String {
    let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
    let tod = timeOfDay(now, calendar: calendar)
    return trimmedName.isEmpty ? tod : "\(tod), \(trimmedName)"
  }

  static func subline(mode: ListeningMode, meetings: [OnboardingMeetingBrief]) -> String {
    let listen = mode == .always ? "I'll be listening." : "I'll listen during your meetings."

    if let first = meetings.first {
      let meetingPart: String
      if meetings.count == 1 {
        meetingPart = "'\(first.title)' at \(first.time) today"
      } else {
        meetingPart = "\(meetings.count) meetings today — first is '\(first.title)' at \(first.time)"
      }
      return "\(meetingPart). \(listen)"
    }

    let setup = mode == .always ? "I'm set up and listening." : "I'm set up and I'll listen during your meetings."
    return "\(setup) Ask me anything to start."
  }

  /// A calendar-aware "prep" starter (when a meeting exists) followed by the
  /// caller's base chips (universal + personalized), de-duplicated and capped.
  static func starters(meetings: [OnboardingMeetingBrief], baseStarters: [String]) -> [String] {
    var out: [String] = []
    if let first = meetings.first {
      out.append("Prep me for '\(first.title)'")
    }
    for candidate in baseStarters {
      let q = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !q.isEmpty, out.count < maxStarters else { continue }
      if !out.contains(where: { $0.lowercased() == q.lowercased() }) {
        out.append(q)
      }
    }
    return Array(out.prefix(maxStarters))
  }
}
