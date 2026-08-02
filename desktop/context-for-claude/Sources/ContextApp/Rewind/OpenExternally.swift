import AppKit
import ContextCore
import Foundation

/// What, if anything, a frame can actually be reopened as.
///
/// The spec asks for a button that "opens the webpage, file, or folder captured in that frame". Our
/// schema stores `appName`, `windowTitle`, `ocrText` and `axText`, and **none of them reliably
/// contains a URL**. That was measured against the real database on this machine (3,149 frames)
/// rather than assumed, and the measurement is why this file is as narrow as it is:
///
/// - Searching every field for an `http(s)` URL matches 85 frames (2.7%) — and inspecting them shows
///   every single one is a link drawn *inside* a page, not the page's own address. Arc's window title
///   is the page title, and the 73 Arc matches are all one tweet whose text quotes a `t.co` link:
///   `'Aidan Guo on X: "… Introducing @AttentionInc https://t.co/wT0pLYHt01" / X'`. Opening that
///   navigates somewhere the user never went. It is a confidently wrong answer, which is the one
///   outcome worse than a hidden button.
/// - The accessibility tree cannot rescue it either. `AXNode` stores `role`, `subrole` and `text`
///   only (`ContextCore/Accessibility.swift:67-84`) — no `AXURL`, no `AXDocument` — so a browser's
///   real address is not captured anywhere in the schema.
///
/// What *is* honest is a window title that **is** a filesystem path. That is the application stating
/// what the window's subject is, not text that happened to be on screen: Warp titles its windows with
/// the working directory (`~`, `~/Documents/Periphery`), editors and terminals commonly do the same.
/// So the rule is: the title, or one of its separator-delimited segments, must resolve to a path that
/// exists on disk right now. Existence is checked rather than inferred, because a path that has since
/// been deleted or renamed would open a Finder error.
///
/// **On this database that resolves 3 frames of 3,149 (0.10%).** The button is therefore hidden
/// almost always, and that is the correct behaviour rather than a gap to be papered over — the honest
/// rate is low because the information genuinely is not there. Recovering URLs properly needs capture
/// to record the focused window's `AXURL`, which is a change to the capture pipeline and not to this
/// window.
enum OpenExternally {

    /// Something a frame can be reopened as.
    enum Target: Equatable {
        case folder(URL)
        case file(URL)

        var url: URL {
            switch self {
            case .folder(let url), .file(let url): return url
            }
        }

        /// The SF Symbol for the button, which the spec asks to adapt to what the frame contains.
        /// Deliberately never a globe: nothing here can ever resolve to a webpage, so offering the
        /// globe icon would advertise a capability this data does not support.
        var symbolName: String {
            switch self {
            case .folder: return "folder"
            case .file: return "doc"
            }
        }

        var accessibilityDescription: String {
            switch self {
            case .folder(let url): return "Open folder \(url.lastPathComponent)"
            case .file(let url): return "Open file \(url.lastPathComponent)"
            }
        }
    }

    /// Separators applications put between a title's subject and its context — "file — project",
    /// "folder | branch". Both halves are tried, because which side carries the path varies by app.
    private static let separators = [" — ", " – ", " - ", " | ", " · ", " → "]

    /// The target for a frame, or nil when nothing can be resolved and the button must be hidden.
    static func target(for frame: RewindFrame) -> Target? {
        guard let title = frame.windowTitle else { return nil }
        for candidate in candidates(in: title) {
            guard let url = resolve(candidate) else { continue }
            return url
        }
        return nil
    }

    /// The whole title first, then each side of any separator it contains.
    ///
    /// Only whole segments — never a path-shaped substring pulled out of the middle of a sentence.
    /// That restriction is the entire difference between this and the version that opened a tweet's
    /// embedded link: a title that *mentions* a path is not a window showing that path.
    private static func candidates(in title: String) -> [String] {
        var result = [title.trimmingCharacters(in: .whitespacesAndNewlines)]
        for separator in separators where title.contains(separator) {
            let parts = title.components(separatedBy: separator)
            result.append(contentsOf: parts.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) })
        }
        // Non-empty rather than a minimum length: `~` is one character and is one of the few titles
        // that genuinely resolves — Warp names a window at the home directory exactly that. A
        // `count >= 2` floor silently dropped it. Nothing shorter is at risk of a false positive,
        // because `resolve` still requires an absolute path that exists.
        return result.filter { !$0.isEmpty }
    }

    /// A candidate that names something on disk, as a folder or a file. Nil for everything else.
    private static func resolve(_ candidate: String) -> Target? {
        var path = candidate
        // `~` and `~/…` are how shells and terminal emulators write a home-relative directory, and
        // they are the most common real hit in practice.
        if path == "~" || path.hasPrefix("~/") {
            path = (path as NSString).expandingTildeInPath
        }
        guard path.hasPrefix("/") else { return nil }

        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else {
            return nil
        }
        let url = URL(fileURLWithPath: path)
        return isDirectory.boolValue ? .folder(url) : .file(url)
    }

    /// Reveals a folder, or opens a file with its default application.
    ///
    /// A folder is *revealed* rather than opened so the user lands in a Finder window looking at it,
    /// which is what "open the folder captured in this frame" means. `activateFileViewerSelecting`
    /// also refuses gracefully if the path vanished between the resolve and the click.
    @MainActor
    static func open(_ target: Target) {
        switch target {
        case .folder(let url):
            NSWorkspace.shared.activateFileViewerSelecting([url])
        case .file(let url):
            NSWorkspace.shared.open(url)
        }
    }
}
