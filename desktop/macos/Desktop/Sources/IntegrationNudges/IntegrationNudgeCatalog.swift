import Foundation

/// Where a nudge sends the user when they accept it.
///
/// Both cases already exist as automation presentation targets, so accepting a
/// nudge opens exactly the sheet the Apps tab would — there is no second,
/// nudge-only connect path that could drift from the real one.
enum IntegrationNudgeRoute: Equatable, Hashable {
  /// An `ImportConnector.id` — data flowing *into* Omi.
  case importConnector(String)
  /// A `MemoryExportDestination.rawValue` — Omi's memory flowing *out* to a tool.
  case exportDestination(String)

  /// The connector/destination identifier, as the sheet APIs expect it.
  var identifier: String {
    switch self {
    case .importConnector(let id), .exportDestination(let id): return id
    }
  }

  /// Which half of the catalog this is, as a bounded telemetry value.
  var telemetryPrefix: String {
    switch self {
    case .importConnector: return "import"
    case .exportDestination: return "export"
    }
  }

  /// A globally unique, bounded telemetry value. ChatGPT and Claude exist on
  /// both sides of the catalog, so the bare identifier would collide.
  var telemetryID: String {
    switch self {
    case .importConnector(let id): return "import:\(id)"
    case .exportDestination(let id): return "export:\(id)"
    }
  }
}

/// How an integration is recognized from the frontmost window.
enum IntegrationNudgeTriggerMatch: Equatable {
  /// The frontmost application is one of these bundle identifiers.
  case application(bundleIdentifiers: [String])
  /// The frontmost application is a browser and its window *title* ends with one
  /// of these suffixes, case-insensitively.
  ///
  /// A window title is the page's `document.title`, never its URL, so a domain
  /// keyword matches nothing real. What is reliable is where sites put their own
  /// name: at the end. X renders "Home / X", Gmail "Inbox (12) - you@corp.com -
  /// Gmail", ChatGPT just "ChatGPT". Anchoring to the end is what separates
  /// those from "ChatGPT vs Claude — a comparison", which is the false positive
  /// that matters — a wrong nudge is worse than a missing one.
  ///
  /// An integration whose real titles carry no site name gets no browser trigger
  /// at all rather than a guess. Notion web titles are the page name alone, and
  /// Google Calendar leads with its name ("Google Calendar - Week of…") exactly
  /// as an article about it would, so both rely on their desktop apps.
  ///
  /// Title matching rather than URL reading is deliberate: the title comes from
  /// the same active-window lookup the proactive assistants already use, and
  /// reading the address bar would mean driving the Accessibility API across
  /// every browser.
  case browserTitleSuffix(suffixes: [String])
}

struct IntegrationNudgeTrigger: Equatable {
  /// Bounded telemetry value naming *what was recognized*. Never the raw app
  /// name or window title.
  let id: String
  let match: IntegrationNudgeTriggerMatch

  var kind: IntegrationNudgeTelemetry.TriggerKind {
    switch match {
    case .application: return .nativeApp
    case .browserTitleSuffix: return .browserSite
    }
  }
}

/// One integration, its pitch, and what recognizes it.
///
/// This is the single source of truth for integration value propositions. The
/// proactive nudge and the connector sheet's "What you get" section read the
/// same `pitch`/`useCases`/`dataScope`, so a user who is nudged and a user who
/// browses the Apps tab are told the same thing.
struct IntegrationNudgeCatalogEntry: Equatable {
  let route: IntegrationNudgeRoute
  /// Human display name. Matches the cross-platform `integration_name`
  /// telemetry dimension where one already exists.
  let displayName: String
  let brand: ConnectorBrand
  /// One sentence, concrete, second person. This is the notification body.
  let pitch: String
  /// Three specific things the user can do once connected. Vague benefits
  /// ("better context") are worse than nothing — each of these names a thing
  /// the user could not do a minute ago.
  let useCases: [String]
  /// Plainly what Omi reads or is given. A nudge that asks for access without
  /// saying what it touches is a dark pattern, so this is not optional.
  let dataScope: String
  /// Empty for integrations that have no reliable foreground signal. Those
  /// entries still supply onboarding copy; they simply never nudge.
  let triggers: [IntegrationNudgeTrigger]

  var connectorID: String { route.identifier }
  var telemetryID: String { route.telemetryID }
  var canNudge: Bool { !triggers.isEmpty }
}

enum IntegrationNudgeCatalog {
  /// Browsers whose window title is treated as a site signal. A browser not on
  /// this list simply never produces a site trigger — the failure mode is a
  /// missed nudge, never a wrong one.
  static let browserBundleIdentifiers: Set<String> = [
    "com.apple.Safari",
    "com.apple.SafariTechnologyPreview",
    "com.google.Chrome",
    "com.google.Chrome.beta",
    "com.google.Chrome.canary",
    "com.microsoft.edgemac",
    "com.microsoft.edgemac.Beta",
    "com.microsoft.edgemac.Dev",
    "com.microsoft.edgemac.Canary",
    "com.brave.Browser",
    "com.brave.Browser.beta",
    "com.brave.Browser.nightly",
    "org.mozilla.firefox",
    "org.mozilla.firefoxdeveloperedition",
    "company.thebrowser.Browser",
    "company.thebrowser.dia",
    "com.vivaldi.Vivaldi",
    "com.operasoftware.Opera",
    "com.operasoftware.OperaGX",
    "com.openai.atlas",
    "com.kagi.kagimacOS",
    "app.zen-browser.zen",
    "ai.perplexity.comet",
  ]

  static let all: [IntegrationNudgeCatalogEntry] = [
    // MARK: Imports — data flowing into Omi

    IntegrationNudgeCatalogEntry(
      route: .importConnector("calendar"),
      displayName: "Google Calendar",
      brand: .calendar,
      pitch: "Omi can see your meetings before they happen, and remember what came out of them.",
      useCases: [
        "Walk into a call already briefed on who you're meeting and what you last discussed.",
        "Ask \"what did I agree to in Monday's standup?\" and get the answer with the meeting attached.",
        "Let Omi plan around the day you actually have, not the one you described.",
      ],
      dataScope: "Reads event titles, times, and attendees from your calendar.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "calendar_app",
          match: .application(bundleIdentifiers: [
            "com.apple.iCal",
            "com.flexibits.fantastical2.mac",
            "com.cron.electron",
          ])
        )
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .importConnector("email"),
      displayName: "Gmail",
      brand: .gmail,
      pitch: "Omi can read your inbox, so it knows what you owe people and what they owe you.",
      useCases: [
        "Ask \"what am I waiting on from Sarah?\" and get the thread, not a search box.",
        "Surface follow-ups you promised in an email and never wrote down anywhere else.",
        "Give Omi the history behind a name so a new thread doesn't start from zero.",
      ],
      dataScope: "Reads your Gmail messages. Omi never sends mail on your behalf.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "gmail_web",
          match: .browserTitleSuffix(suffixes: ["Gmail"])
        ),
        IntegrationNudgeTrigger(
          id: "gmail_client_app",
          match: .application(bundleIdentifiers: ["com.mimestream.Mimestream"])
        ),
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .importConnector("local-files"),
      displayName: "Local Files",
      brand: .localFiles,
      pitch: "Omi can index the documents and code you actually work in, without any of it leaving your Mac.",
      useCases: [
        "Find a spec or contract by what it said, not by where you filed it.",
        "Get answers that cite your own files instead of guessing at them.",
        "Keep the whole index on-device — nothing is uploaded.",
      ],
      dataScope: "Indexes the folders you pick, on-device.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "finder",
          match: .application(bundleIdentifiers: ["com.apple.finder"])
        )
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .importConnector("apple-notes"),
      displayName: "Apple Notes",
      brand: .appleNotes,
      pitch: "Half your thinking already lives in Notes. Omi can read it.",
      useCases: [
        "Recall a note by what you meant, not by the words you happened to type.",
        "Let Omi connect something you wrote in March to the conversation you're having today.",
        "Stop re-explaining context you already captured once.",
      ],
      dataScope: "Reads the text of your local Apple Notes.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "apple_notes_app",
          match: .application(bundleIdentifiers: ["com.apple.Notes"])
        )
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .importConnector("x"),
      displayName: "X",
      brand: .x,
      pitch: "Omi can learn from what you post, bookmark, and like on X.",
      useCases: [
        "Ask \"what was that thread I bookmarked about pricing?\" and get it back.",
        "Turn a year of bookmarks into something you can actually search.",
        "Let Omi use what you've publicly said as context for how you think.",
      ],
      dataScope: "Reads your own posts, bookmarks, and likes.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "x_web",
          match: .browserTitleSuffix(suffixes: ["/ X", "/ Twitter"])
        )
      ]
    ),

    // The two memory-log imports carry no triggers: opening ChatGPT is a much
    // better moment to offer the MCP connector below (which makes ChatGPT
    // smarter about you) than to ask the user to go export a memory file. They
    // exist here so the Apps-tab sheet has the same onboarding copy as
    // everything else.
    IntegrationNudgeCatalogEntry(
      route: .importConnector("chatgpt"),
      displayName: "ChatGPT",
      brand: .chatgpt,
      pitch: "Bring what ChatGPT already knows about you into Omi.",
      useCases: [
        "Start Omi with the preferences and history you spent a year teaching ChatGPT.",
        "Keep one memory instead of two that each know half of you.",
        "Import once — Omi keeps learning from there.",
      ],
      dataScope: "You paste a ChatGPT memory export. Omi never signs in to your ChatGPT account.",
      triggers: []
    ),

    IntegrationNudgeCatalogEntry(
      route: .importConnector("claude"),
      displayName: "Claude",
      brand: .claude,
      pitch: "Bring what Claude already knows about you into Omi.",
      useCases: [
        "Start Omi with the context you've already built up in Claude.",
        "Keep one memory instead of two that each know half of you.",
        "Import once — Omi keeps learning from there.",
      ],
      dataScope: "You paste a Claude memory export. Omi never signs in to your Claude account.",
      triggers: []
    ),

    // MARK: Exports — Omi's memory flowing out to a tool

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("chatgpt"),
      displayName: "ChatGPT",
      brand: .chatgpt,
      pitch: "Give ChatGPT everything Omi remembers about you.",
      useCases: [
        "Open a new ChatGPT conversation that already knows your projects and people.",
        "Stop pasting the same paragraph of background into every chat.",
        "Ask ChatGPT about something you said out loud last week.",
      ],
      dataScope: "Lets ChatGPT query your Omi memories and conversations. Revocable any time.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "chatgpt_app",
          match: .application(bundleIdentifiers: ["com.openai.chat"])
        ),
        IntegrationNudgeTrigger(
          id: "chatgpt_web",
          match: .browserTitleSuffix(suffixes: ["ChatGPT"])
        ),
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("claude"),
      displayName: "Claude",
      brand: .claude,
      pitch: "Give Claude everything Omi remembers about you.",
      useCases: [
        "Start a Claude conversation that already has your context loaded.",
        "Ask Claude to draft something in your voice, from your own history.",
        "Skip the re-briefing at the start of every new chat.",
      ],
      dataScope: "Lets Claude query your Omi memories and conversations. Revocable any time.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "claude_app",
          match: .application(bundleIdentifiers: ["com.anthropic.claudefordesktop"])
        ),
        IntegrationNudgeTrigger(
          id: "claude_web",
          match: .browserTitleSuffix(suffixes: ["Claude"])
        ),
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("gemini"),
      displayName: "Gemini",
      brand: .gemini,
      pitch: "Give Gemini everything Omi remembers about you.",
      useCases: [
        "Ask Gemini about your own week, not just the public internet.",
        "Carry your Omi context into Google's tools without copy-pasting it.",
        "Keep one memory across the assistants you actually use.",
      ],
      dataScope: "Lets Gemini query your Omi memories and conversations. Revocable any time.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "gemini_web",
          match: .browserTitleSuffix(suffixes: ["Gemini"])
        )
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("notion"),
      displayName: "Notion",
      brand: .notion,
      pitch: "Omi can write what it learns into the Notion workspace you already keep.",
      useCases: [
        "Land meeting notes and takeaways where your team already looks for them.",
        "Stop re-typing decisions from a conversation into a doc.",
        "Keep one workspace as the record instead of two half-records.",
      ],
      dataScope: "Writes Omi memories into the Notion workspace you authorize.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "notion_app",
          match: .application(bundleIdentifiers: ["notion.id"])
        )
      ]
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("obsidian"),
      displayName: "Obsidian",
      brand: .obsidian,
      pitch: "Omi can drop what it learns straight into your Obsidian vault.",
      useCases: [
        "Get conversations and memories as notes in the vault you already link from.",
        "Keep everything local and plain-text, the way the vault already is.",
        "Let your daily notes fill themselves in from what you actually did.",
      ],
      dataScope: "Writes Omi memories into the vault folder you choose, on-device.",
      triggers: [
        IntegrationNudgeTrigger(
          id: "obsidian_app",
          match: .application(bundleIdentifiers: ["md.obsidian"])
        )
      ]
    ),

    // Entries below have no reliable foreground signal: a terminal window is
    // not evidence that Claude Code or Codex is running in it, and the agent
    // runtimes have no window of their own. They carry onboarding copy for the
    // connector sheet and never nudge.

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("claudeCode"),
      displayName: "Claude Code",
      brand: .claudeCode,
      pitch: "Give Claude Code your Omi memory, so it codes with your context.",
      useCases: [
        "Let the agent read decisions you made out loud, not just what's in the repo.",
        "Skip explaining the same project background at the start of every session.",
        "Keep one memory across your editor and your assistant.",
      ],
      dataScope: "Adds Omi as an MCP server in your Claude Code config.",
      triggers: []
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("codex"),
      displayName: "Codex",
      brand: .codex,
      pitch: "Give Codex your Omi memory, so it codes with your context.",
      useCases: [
        "Let the agent read decisions you made out loud, not just what's in the repo.",
        "Skip re-describing the project at the start of every session.",
        "Keep one memory across your editor and your assistant.",
      ],
      dataScope: "Adds Omi as an MCP server in your Codex config.",
      triggers: []
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("openclaw"),
      displayName: "OpenClaw",
      brand: .openclaw,
      pitch: "Give OpenClaw your Omi memory, so its agents work from your context.",
      useCases: [
        "Let a long-running agent pick up what you already know.",
        "Hand off work without writing a brief first.",
        "Keep one memory across every agent you run.",
      ],
      dataScope: "Adds Omi as an MCP server in your OpenClaw config.",
      triggers: []
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("hermes"),
      displayName: "Hermes",
      brand: .hermes,
      pitch: "Give Hermes your Omi memory, so its agents work from your context.",
      useCases: [
        "Let a long-running agent pick up what you already know.",
        "Hand off work without writing a brief first.",
        "Keep one memory across every agent you run.",
      ],
      dataScope: "Adds Omi as an MCP server in your Hermes config.",
      triggers: []
    ),

    IntegrationNudgeCatalogEntry(
      route: .exportDestination("agents"),
      displayName: "Agents",
      brand: .agents,
      pitch: "Give your own agents the same memory Omi has.",
      useCases: [
        "Point any MCP-speaking agent at your Omi memory.",
        "Build on your own history instead of a blank context window.",
        "Revoke access from one place when you're done.",
      ],
      dataScope: "Exposes your Omi memory over MCP to the agent you authorize.",
      triggers: []
    ),
  ]

  /// Entries that can actually fire a nudge.
  static var nudgeable: [IntegrationNudgeCatalogEntry] { all.filter(\.canNudge) }

  static func entry(for route: IntegrationNudgeRoute) -> IntegrationNudgeCatalogEntry? {
    all.first { $0.route == route }
  }

  /// Resolve an entry from the value carried on a notification action.
  static func entry(telemetryID: String) -> IntegrationNudgeCatalogEntry? {
    all.first { $0.telemetryID == telemetryID }
  }

  /// Onboarding copy for an Apps-tab import connector. Returns nil for ids the
  /// catalog has no entry for, so a new connector shows its existing one-line
  /// description rather than nothing.
  static func importEntry(connectorID: String) -> IntegrationNudgeCatalogEntry? {
    entry(for: .importConnector(connectorID))
  }

  static func exportEntry(destinationID: String) -> IntegrationNudgeCatalogEntry? {
    entry(for: .exportDestination(destinationID))
  }

  /// Every telemetry id in the catalog, used by the store's reset path.
  static var allTelemetryIDs: [String] { all.map(\.telemetryID) }
}
