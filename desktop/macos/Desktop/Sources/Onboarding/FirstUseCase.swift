import AppKit
import Foundation

/// One of the things new users most often do with Omi first, paired with the site that hosts it and
/// the question Omi answers well there.
///
/// The popup that closes onboarding used to list generic questions ("What should I do today?"). Those
/// answer *what could I ask*, but a new user's real blocker is *where do I go to see this work*. Each
/// case here names a concrete place, opens it, and puts the matching question in the bar, so the
/// first ask happens on a screen where the answer is visibly grounded in what is on it.
struct FirstUseCase: Identifiable, Equatable, Sendable {
  let id: String
  /// The chip label.
  let label: String
  /// SF Symbol for the chip.
  let symbol: String
  /// The place the user is sent, as it is named to them ("Minecraft", "Figma").
  let siteName: String
  let url: URL
  /// The question this place is good for; shown in the preview's bar sketch.
  let question: String

  /// Minecraft in the browser (Eaglercraft) rather than a launcher like Steam: it is the one game
  /// everyone recognises, it loads with no install or account, and the whole scene is on screen,
  /// which is exactly the input Omi grounds an answer in.
  static let game = FirstUseCase(
    id: "game",
    label: "Play a game",
    symbol: "gamecontroller",
    siteName: "Minecraft",
    url: URL(string: "https://eaglercraft.com/play?version=1.8.8")!,
    question: "How do I craft a pickaxe?")

  static let design = FirstUseCase(
    id: "design",
    label: "Get design feedback",
    symbol: "paintbrush.pointed",
    siteName: "Figma",
    url: URL(string: "https://www.figma.com/")!,
    question: "Give me honest feedback on this design.")

  static let post = FirstUseCase(
    id: "post",
    label: "Write a post",
    symbol: "text.bubble",
    siteName: "X",
    url: URL(string: "https://x.com/compose/post")!,
    question: "Help me write a post about what I'm working on.")

  static let shop = FirstUseCase(
    id: "shop",
    label: "Shop",
    symbol: "cart",
    siteName: "Amazon",
    url: URL(string: "https://www.amazon.com/")!,
    question: "Which of these should I buy, and why?")

  /// In the order the chips render.
  static let all: [FirstUseCase] = [game, design, post, shop]

  static func named(_ id: String) -> FirstUseCase? {
    all.first { $0.id == id }
  }
}

/// "Try it now": open the site. Nothing is typed anywhere on the user's behalf — the notch is not a
/// text surface, and the main chat is theirs to fill — so the case is a place to go, not a prompt.
enum FirstUseCaseLauncher {
  /// Returns `false` when the site could not be opened.
  @MainActor
  @discardableResult
  static func launch(
    _ useCase: FirstUseCase,
    open: (URL) -> Bool = { NSWorkspace.shared.open($0) }
  ) -> Bool {
    guard open(useCase.url) else {
      log("FirstUseCaseLauncher: could not open \(useCase.siteName) for '\(useCase.id)'")
      return false
    }
    log("FirstUseCaseLauncher: opened \(useCase.siteName) for '\(useCase.id)'")
    AnalyticsManager.shared.floatingBarAskOmiOpened(source: "first_use_popup")
    return true
  }
}
