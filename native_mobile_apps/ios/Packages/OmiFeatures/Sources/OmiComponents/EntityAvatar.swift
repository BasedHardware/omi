import OmiDesign
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// The picture at the start of a row (`EntityVisual`): a brand logo on a white plate (rounded
/// square), a person's monogram (circle), the conversation's emoji on a soft category tint, or a
/// glyph. A logo that fails to load shows `fallback` (a wrong or blank logo is worse than a
/// neutral tile).
public struct EntityAvatar: View {
    let visual: EntityVisual
    var size: CGFloat
    var fallback: EntityVisual

    public init(_ visual: EntityVisual, size: CGFloat = 40, fallback: EntityVisual = .symbol("checklist")) {
        self.visual = visual
        self.size = size
        self.fallback = fallback
    }

    public var body: some View {
        switch visual {
        case let .brand(domain, bundled):
            #if canImport(UIKit)
                BrandLogo(domain: domain, bundled: bundled, size: size, fallback: fallback)
            #else
                EntityAvatar(fallback, size: size)
            #endif
        case let .person(name, _):
            NameMonogram(name: name, size: size)
        case let .emoji(emoji, category):
            CategoryEmojiTile(emoji: emoji, category: category, size: size)
        case let .symbol(name):
            Image(systemName: name)
                .font(.system(size: size * 0.42))
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(width: size, height: size)
                .background(DS.Palette.fill, in: EntityAvatar.square(size))
        }
    }

    static func square(_ size: CGFloat) -> RoundedRectangle {
        RoundedRectangle(cornerRadius: size * 0.28, style: .continuous)
    }
}

#if canImport(UIKit)
/// A brand mark: bundled with the app, else logo.dev by domain (cached; unknown domains 404 and
/// show the fallback).
private struct BrandLogo: View {
    let domain: String
    let bundled: String?
    let size: CGFloat
    let fallback: EntityVisual
    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        if failed {
            EntityAvatar(fallback, size: size)
        } else {
            plate
                .task(id: domain) {
                    guard bundledImage == nil, image == nil else { return }
                    image = LogoCache.shared.cached(domain)
                    guard image == nil else { return }
                    if let loaded = await LogoCache.shared.load(domain) { image = loaded } else { failed = true }
                }
        }
    }

    private var bundledImage: Image? {
        bundled.flatMap(OmiMedia.logo)
    }

    private var plate: some View {
        Group {
            if let bundledImage {
                bundledImage.resizable().scaledToFit()
            } else if let image = image ?? LogoCache.shared.cached(domain) {
                Image(uiImage: image).resizable().scaledToFit()
            } else {
                Color.clear
            }
        }
        .padding(size * 0.16)
        .frame(width: size, height: size)
        .background(Color.white, in: EntityAvatar.square(size))
        .overlay { EntityAvatar.square(size).strokeBorder(DS.Palette.hairline, lineWidth: DS.Stroke.hairline) }
        .accessibilityHidden(true)
    }
}
#endif

/// Initials on a soft two-tone gradient; the hue follows the name (stable across launches).
private struct NameMonogram: View {
    let name: String
    let size: CGFloat

    var body: some View {
        let colors = Self.palette[Self.hash(name.lowercased()) % Self.palette.count]
        Text(Self.initials(name))
            .font(.system(size: size * 0.38, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(LinearGradient(colors: [colors.0, colors.1], startPoint: .topLeading, endPoint: .bottomTrailing), in: Circle())
            .accessibilityHidden(true)
    }

    static func initials(_ name: String) -> String {
        name.split(separator: " ").prefix(2).compactMap(\.first).map { $0.uppercased() }.joined()
    }

    /// Java's `String.hashCode` (UTF-16, wrapping), so Android picks the same hue for a name;
    /// `String.hashValue` changes every launch.
    static func hash(_ text: String) -> Int {
        var hash: Int32 = 0
        for unit in text.utf16 {
            hash = hash &* 31 &+ Int32(unit)
        }
        return Int(hash & 0x7FFF_FFFF)
    }

    private static let palette: [(Color, Color)] = [
        (rgb(0x60A5FA), rgb(0x2563EB)), (rgb(0xF472B6), rgb(0xDB2777)), (rgb(0x34D399), rgb(0x059669)),
        (rgb(0xFBBF24), rgb(0xD97706)), (rgb(0xA78BFA), rgb(0x7C3AED)), (rgb(0x22D3EE), rgb(0x0891B2)),
    ]
}

/// The conversation's emoji on a tint of its category, so the tiles don't all read the same.
private struct CategoryEmojiTile: View {
    let emoji: String
    let category: String?
    let size: CGFloat
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Text(emoji)
            .font(.system(size: size * 0.5))
            .frame(width: size, height: size)
            .background(tint.opacity(colorScheme == .dark ? 0.18 : 0.12), in: EntityAvatar.square(size))
            .accessibilityHidden(true)
    }

    private var tint: Color {
        switch category {
        case "health": DS.Palette.live
        case "finance", "economics", "business": DS.Palette.success
        case "work", "technology", "education": DS.Palette.agent
        case "travel", "personal", "family": DS.Palette.amber
        case "social": rgb(0xA855F7)
        default: DS.Palette.inkTertiary
        }
    }
}

private func rgb(_ hex: UInt32) -> Color {
    Color(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
}

#if canImport(UIKit)
/// Brand logos by domain from logo.dev, in memory and on disk. A 404 (an unknown domain) is
/// remembered so it is not asked again; a network error is not, so the next appearance retries.
@MainActor
public final class LogoCache {
    public static let shared = LogoCache()
    /// logo.dev publishable key (safe to ship; the same kind Iris uses).
    static let token = "pk_X-1ZO13GSgeOoUrIuJ6GMQ"

    private let memory = NSCache<NSString, UIImage>()
    private var missing: Set<String> = []
    private var loading: [String: Task<UIImage?, Never>] = [:]
    private let directory = URL.cachesDirectory.appending(path: "logos", directoryHint: .isDirectory)

    static func url(_ domain: String) -> URL? {
        URL(string: "https://img.logo.dev/\(domain)?token=\(token)&size=128&format=png&fallback=404")
    }

    func cached(_ domain: String) -> UIImage? {
        memory.object(forKey: domain as NSString)
    }

    /// The logo, or nil when there is none (or it could not load right now).
    func load(_ domain: String) async -> UIImage? {
        if let image = cached(domain) { return image }
        if missing.contains(domain) { return nil }
        if let task = loading[domain] { return await task.value }
        let file = directory.appending(path: domain + ".png")
        let marker = directory.appending(path: domain + ".404")
        let task = Task<UIImage?, Never> { [directory] in
            let stored: (data: Data?, isMissing: Bool) = await Task.detached {
                (try? Data(contentsOf: file), FileManager.default.fileExists(atPath: marker.path))
            }.value
            if stored.isMissing {
                self.missing.insert(domain)
                return nil
            }
            if let data = stored.data, let image = UIImage(data: data) { return image }
            guard let url = Self.url(domain), let (data, response) = try? await URLSession.shared.data(from: url) else { return nil }
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if status == 404 {
                await Task.detached {
                    try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                    FileManager.default.createFile(atPath: marker.path, contents: nil)
                }.value
                self.missing.insert(domain)
                return nil
            }
            guard status == 200, let image = UIImage(data: data) else { return nil }
            await Task.detached {
                try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try? data.write(to: file, options: .atomic)
            }.value
            return image
        }
        loading[domain] = task
        let image = await task.value
        loading[domain] = nil
        if let image { memory.setObject(image, forKey: domain as NSString) }
        return image
    }
}
#endif
