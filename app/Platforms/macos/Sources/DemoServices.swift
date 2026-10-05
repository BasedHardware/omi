import AppKit
import Foundation
import OmiKit
import OmiUI

// MARK: - Rewind history (demo `OmiRewind.listFrames` / `readFrame`)

/// In-memory rewind history serving realistic frames through the same
/// `RewindTimelineBridge` contract as the production engine. Frame previews
/// are generated demo captures (gradient + app label), clearly not real
/// screen content.
private final class DemoRewindHistory: @unchecked Sendable {
    struct Entry {
        let id: String
        let stamp: Int64
        let app: String
        let title: String
    }

    let entries: [Entry]

    init(now: Int64) {
        let minute: Int64 = 60_000
        entries = [
            Entry(id: "demo-cap-1", stamp: now - 18 * minute, app: "Xcode",
                title: "OmiHostApp.swift — omi-v5"),
            Entry(id: "demo-cap-2", stamp: now - 47 * minute, app: "Figma",
                title: "Omi v5.1 desktop — Activity IA"),
            Entry(id: "demo-cap-3", stamp: now - 82 * minute, app: "Safari",
                title: "Reading group schedule — shared doc"),
            Entry(id: "demo-cap-4", stamp: now - 126 * minute, app: "Messages",
                title: "Priya"),
            Entry(id: "demo-cap-5", stamp: now - 3 * 60 * minute, app: "Linear",
                title: "Tasting booking follow-ups"),
            Entry(id: "demo-cap-6", stamp: now - 26 * 60 * minute, app: "Xcode",
                title: "PolicyTests.swift — native-core"),
            Entry(id: "demo-cap-7", stamp: now - 27 * 60 * minute, app: "Mail",
                title: "Re: coast trip logistics"),
        ]
    }

    func framePage(query: String, cursor: String?, limit: Int) -> RewindFramePage {
        let needle = query.trimmingCharacters(in: .whitespaces).lowercased()
        var matched = entries.filter {
            needle.isEmpty || "\($0.app)\n\($0.title)".lowercased().contains(needle)
        }
        if let cursor {
            matched = matched.filter { $0.stamp < (Int64(cursor) ?? .max) }
        }
        let page = matched.prefix(limit)
        let frames = page.map { entry in
            RewindFrame(
                id: entry.id, capturedAtMs: entry.stamp, appName: entry.app,
                windowTitle: entry.title)
        }
        return RewindFramePage(
            frames: frames,
            nextCursor: frames.count == limit ? page.last.map { "\($0.stamp)" } : nil)
    }

    /// A generated demo capture bitmap: deep gradient + app label, so the
    /// preview pane shows real image rendering without real screen content.
    func frameJPEG(id: String) -> Data? {
        guard let entry = entries.first(where: { $0.id == id }) else { return nil }
        let width = 640, height = 400
        let image = NSImage(size: NSSize(width: width, height: height))
        image.lockFocus()
        let gradient = NSGradient(
            starting: NSColor(calibratedRed: 0.13, green: 0.14, blue: 0.24, alpha: 1),
            ending: NSColor(calibratedRed: 0.05, green: 0.05, blue: 0.09, alpha: 1))
        gradient?.draw(
            in: NSRect(x: 0, y: 0, width: width, height: height), angle: -60)
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 22, weight: .semibold),
            .foregroundColor: NSColor.white.withAlphaComponent(0.82),
            .paragraphStyle: paragraph,
        ]
        let label = "\(entry.app)\n\(entry.title) — demo capture"
        NSAttributedString(string: label, attributes: attrs).draw(
            in: NSRect(x: 40, y: height / 2 - 40, width: width - 80, height: 120))
        image.unlockFocus()
        let rep = NSBitmapImageRep(data: image.tiffRepresentation ?? Data())
        return rep?.representation(using: .jpeg, properties: [.compressionFactor: 0.8])
    }
}

// MARK: - Bundle assembly

enum MacDemoServices {
    static func makeServices() -> AppServices {
        let history = DemoRewindHistory(
            now: Int64(Date().timeIntervalSince1970 * 1000))
        return DemoServices.makeServices(
            rewindCapture: OmiRewindEngine.shared.bridge,
            rewindTimeline: RewindTimelineBridge { source, query, cursor, limit in
                guard source == .captured else {
                    throw RewindTimelineFailure.unavailable
                }
                return history.framePage(query: query, cursor: cursor, limit: limit)
            },
            rewindFrameImage: { history.frameJPEG(id: $0) })
    }
}
