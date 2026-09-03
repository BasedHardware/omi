import Foundation

/// Tells the voice session what is on the panel, at the start of every turn.
///
/// The panel tools each hand their result back, so after one of them the model knows
/// what it put up. On a turn where it calls no tool it knew nothing — and measured live,
/// it said "I've updated that note for you, making it shorter and more casual" with an
/// empty screen and no tool call behind it. The instruction already forbids claiming a
/// physical action it did not take; the model cannot follow that rule about a panel it
/// cannot see.
///
/// The session's `instructions` are fixed at construction and Gemini has no session
/// update, so this rides the same per-turn text channel background agent completions
/// use. It is one short line when nothing is on screen.
@MainActor
enum RealtimeHubPanelStateContext {
  /// What to inject, or nil when the session has already been told this exact thing —
  /// a turn boundary fires often and re-sending an unchanged panel is prompt cost for
  /// no information.
  static func line(lastSent: String?) -> String? {
    let current = state()
    guard current != lastSent else { return nil }
    return current
  }

  /// One word for the log: which state the session was told about, without putting the
  /// user's panel text in a log file.
  static func label() -> String {
    switch PanelSession.presence() {
    case .none: return "none"
    case .copy: return "copy"
    case .offer: return "offer"
    case .working: return "working"
    case .draft: return "draft"
    }
  }

  static func state() -> String {
    switch PanelSession.presence() {
    case .none:
      return """
        [Omi panel] Nothing is on the user's screen right now, and this line is current: \
        answer "is anything on my screen" from it directly, with no tool call, and do \
        not try reopen_panel to find out. If they ask to change, shorten, or reword \
        something you put up earlier, it is gone: put the corrected version up with \
        update_panel rather than saying you changed it.
        """

    case .copy(let content):
      return """
        [Omi panel] A panel is on the user's screen and it reads:
        \(content)

        This is current, so you already know what is on screen: answer any question \
        about what the panel says from this text directly, with no tool call, naming \
        the actual values rather than referring to them vaguely — reopen_panel and \
        close_panel are for putting it back and taking it away, never for looking. \
        Change it with update_panel, and never say you changed it without calling that \
        tool. Do not read the whole thing aloud unprompted; say one short line about it.
        """

    case .offer(let title):
      return """
        [Omi panel] An offer titled "\(title)" is on the user's screen, waiting for them \
        to accept it with the ✓ on the card. Nothing has been filled in yet, so there is \
        nothing to read out or change. Do not put another panel up over it, and do not \
        say you already did the work — if they want it, tell them to tap the check.
        """

    case .working(let title):
      return """
        [Omi panel] A panel titled "\(title)" is on the user's screen and is still \
        filling in. Do not describe its contents — you do not have them yet — and do not \
        replace it. Tell them it is still working if they ask.
        """

    case .draft(let body):
      return """
        [Omi panel] The message-draft card is on the user's screen\
        \(body.map { " and the draft reads:\n\($0)" } ?? ", still writing").

        That card takes edits in its own box, so refining the wording is something the \
        user does on it directly. Do not claim you changed it. close_panel takes it away.
        """
    }
  }
}
