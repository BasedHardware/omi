import AppKit
import SwiftUI

enum ConnectorBrand: String, Sendable {
  case calendar
  case gmail
  case localFiles
  case appleNotes
  case notion
  case obsidian
  case chatgpt
  case claude
  case gemini

  fileprivate var appPath: String? {
    switch self {
    case .appleNotes:
      return "/System/Applications/Notes.app"
    case .notion:
      return "/Applications/Notion.app"
    case .obsidian:
      return "/Applications/Obsidian.app"
    case .chatgpt:
      return "/Applications/ChatGPT.app"
    case .claude:
      return "/Applications/Claude.app"
    case .calendar, .gmail, .localFiles, .gemini:
      return nil
    }
  }

  var installedApplicationURL: URL? {
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
    case .obsidian:
      return "obsidian_logo"
    case .gemini:
      return "gemini_logo"
    default:
      return nil
    }
  }

  fileprivate var fallbackSymbol: String {
    switch self {
    case .calendar:
      return "calendar"
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
    }
  }
}

private enum ConnectorBrandImageLoader {
  private static var cache: [ConnectorBrand: NSImage] = [:]
  private static var resourceBundle: Bundle? = {
    let candidates = Bundle.allBundles + Bundle.allFrameworks + [Bundle.main]

    for bundle in candidates {
      if bundle.url(forResource: "gmail_logo", withExtension: "png") != nil {
        return bundle
      }
    }

    if let resourcesURL = Bundle.main.resourceURL,
      let bundleURLs = try? FileManager.default.contentsOfDirectory(
        at: resourcesURL,
        includingPropertiesForKeys: nil
      )
    {
      for url in bundleURLs where url.pathExtension == "bundle" {
        if let bundle = Bundle(url: url),
          bundle.url(forResource: "gmail_logo", withExtension: "png") != nil
        {
          return bundle
        }
      }
    }

    return nil
  }()

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
    guard let appPath = brand.appPath, FileManager.default.fileExists(atPath: appPath) else {
      return nil
    }
    return NSWorkspace.shared.icon(forFile: appPath)
  }

  private static func bundledImage(for brand: ConnectorBrand) -> NSImage? {
    guard let resourceName = brand.bundledResourceName,
      let bundle = resourceBundle,
      let url = bundle.url(forResource: resourceName, withExtension: "png")
    else {
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

      if let image = ConnectorBrandImageLoader.image(for: brand) {
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
