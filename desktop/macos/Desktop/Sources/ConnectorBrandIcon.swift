import AppKit
import OmiTheme
import SwiftUI

enum ConnectorBrand: String, Sendable {
  case calendar
  case appleCalendar
  case appleReminders
  case gmail
  case localFiles
  case appleNotes
  case notion
  case obsidian
  case chatgpt
  case claude
  case gemini
  case agents
  case claudeCode
  case codex
  case openclaw
  case hermes
  case x

  fileprivate var appPath: String? {
    switch self {
    case .appleCalendar:
      return "/System/Applications/Calendar.app"
    case .appleReminders:
      return "/System/Applications/Reminders.app"
    case .appleNotes:
      return "/System/Applications/Notes.app"
    case .notion:
      return "/Applications/Notion.app"
    case .obsidian:
      return "/Applications/Obsidian.app"
    case .chatgpt:
      return "/Applications/ChatGPT.app"
    case .claude, .claudeCode:
      // Claude Code is Anthropic's CLI — reuse the Claude app icon as the brand mark.
      return "/Applications/Claude.app"
    case .codex:
      // Codex is OpenAI's CLI — reuse the ChatGPT app icon as the brand mark.
      return "/Applications/ChatGPT.app"
    case .calendar, .gmail, .localFiles, .gemini, .agents, .openclaw, .hermes, .x:
      return nil
    }
  }

  fileprivate var appBundleIdentifier: String? {
    switch self {
    case .appleCalendar:
      return "com.apple.iCal"
    case .appleReminders:
      return "com.apple.reminders"
    case .appleNotes:
      return "com.apple.Notes"
    case .notion:
      return "notion.id"
    case .obsidian:
      return "md.obsidian"
    case .chatgpt, .codex:
      return "com.openai.chat"
    case .claude, .claudeCode:
      return "com.anthropic.claudefordesktop"
    case .calendar, .gmail, .localFiles, .gemini, .agents, .openclaw, .hermes, .x:
      return nil
    }
  }

  var installedApplicationURL: URL? {
    // LaunchServices finds the app wherever it lives (~/Applications, Setapp, renamed);
    // the fixed /Applications path stays as a fallback for unregistered copies.
    if let appBundleIdentifier,
      let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: appBundleIdentifier)
    {
      return url
    }
    guard let appPath, FileManager.default.fileExists(atPath: appPath) else {
      return nil
    }
    return URL(fileURLWithPath: appPath)
  }

  fileprivate var bundledResourceName: String? {
    switch self {
    case .calendar:
      return "google_calendar_logo"
    case .gmail:
      return "gmail_logo"
    case .notion:
      return "notion_logo"
    case .obsidian:
      return "obsidian_logo"
    case .chatgpt, .codex:
      return "chatgpt_logo"
    case .claude, .claudeCode:
      return "claude_logo"
    case .gemini:
      return "gemini_logo"
    case .hermes:
      return "hermes_logo"
    case .openclaw:
      return "openclaw_logo"
    default:
      return nil
    }
  }

  fileprivate var fallbackSymbol: String {
    switch self {
    case .calendar:
      return "calendar"
    case .appleCalendar:
      return "calendar"
    case .appleReminders:
      return "checklist"
    case .gmail:
      return "envelope.fill"
    case .localFiles:
      return "folder.fill"
    case .appleNotes:
      return "note.text"
    case .notion:
      return "square.text.square"
    case .obsidian:
      return "mountain.2.fill"
    case .chatgpt:
      return "bubble.left.and.bubble.right.fill"
    case .claude:
      return "sparkles"
    case .gemini:
      return "sparkles.rectangle.stack"
    case .agents:
      return "point.3.connected.trianglepath.dotted"
    case .claudeCode:
      return "terminal.fill"
    case .codex:
      return "chevron.left.forwardslash.chevron.right"
    case .openclaw:
      return "pawprint.fill"
    case .hermes:
      return "bolt.horizontal.circle.fill"
    case .x:
      // SF Symbols has no X/Twitter mark — rendered as the 𝕏 glyph in the view.
      return "at"
    }
  }
}

enum ConnectorBrandImageLoader {
  private nonisolated(unsafe) static var cache: [ConnectorBrand: NSImage] = [:]
  private nonisolated(unsafe) static var resourceBundle: Bundle? = {
    let candidates = Bundle.allBundles + Bundle.allFrameworks + [Bundle.main]

    for bundle in candidates {
      if bundle.url(forResource: "gmail_logo", withExtension: "png") != nil {
        return bundle
      }
    }

    // SwiftPM copies the target's resources into "<pkg>_<target>.bundle", placed
    // inside the enclosing bundle's Resources (app in production) or next to the
    // build products (.xctest in `swift test`), so scan one level of nested
    // bundles under both locations for every candidate.
    for parent in candidates {
      var scanRoots = [parent.bundleURL.deletingLastPathComponent()]
      if let resourcesURL = parent.resourceURL {
        scanRoots.insert(resourcesURL, at: 0)
      }
      for root in scanRoots {
        guard
          let bundleURLs = try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: nil
          )
        else { continue }
        for url in bundleURLs where url.pathExtension == "bundle" {
          if let bundle = Bundle(url: url),
            bundle.url(forResource: "gmail_logo", withExtension: "png") != nil
          {
            return bundle
          }
        }
      }
    }

    return nil
  }()

  static func bundledImageURL(for brand: ConnectorBrand) -> URL? {
    guard let resourceName = brand.bundledResourceName, let bundle = resourceBundle else {
      return nil
    }
    return bundle.url(forResource: resourceName, withExtension: "png")
  }

  static func image(for brand: ConnectorBrand) -> NSImage? {
    if let cached = cache[brand] {
      return cached
    }

    let image =
      appImage(for: brand)
      ?? bundledImage(for: brand)
      ?? localFilesImage(for: brand)

    if let image {
      image.isTemplate = false
      cache[brand] = image
    }

    return image
  }

  private static func appImage(for brand: ConnectorBrand) -> NSImage? {
    guard let appURL = brand.installedApplicationURL else {
      return nil
    }
    return NSWorkspace.shared.icon(forFile: appURL.path)
  }

  private static func bundledImage(for brand: ConnectorBrand) -> NSImage? {
    guard let url = bundledImageURL(for: brand) else {
      return nil
    }
    return NSImage(contentsOf: url)
  }

  private static func localFilesImage(for brand: ConnectorBrand) -> NSImage? {
    guard brand == .localFiles else { return nil }

    let fm = FileManager.default
    let documentsPath = fm.homeDirectoryForCurrentUser.appendingPathComponent("Documents").path
    let path =
      fm.fileExists(atPath: documentsPath)
      ? documentsPath : fm.homeDirectoryForCurrentUser.path
    return NSWorkspace.shared.icon(forFile: path)
  }
}

struct ConnectorBrandIcon: View {
  let brand: ConnectorBrand
  var size: CGFloat = 38
  var cornerRadius: CGFloat = 11

  var body: some View {
    ZStack {
      RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        .fill(OmiColors.backgroundSecondary)
        .overlay(
          RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )

      if brand == .agents {
        Text("🤖")
          .font(.system(size: size * 0.46))
      } else if brand == .x {
        // X's wordmark glyph — no SF Symbol or app icon exists for it.
        Text("𝕏")
          .font(.system(size: size * 0.5, weight: .bold))
          .foregroundColor(OmiColors.textPrimary)
      } else if let image = ConnectorBrandImageLoader.image(for: brand) {
        Image(nsImage: image)
          .resizable()
          .interpolation(.high)
          .aspectRatio(contentMode: .fit)
          .padding(size * 0.18)
      } else {
        Image(systemName: brand.fallbackSymbol)
          .font(.system(size: size * 0.38, weight: .semibold))
          .foregroundColor(OmiColors.textSecondary)
      }
    }
    .frame(width: size, height: size)
  }
}
