import AppKit
import ApplicationServices
import Foundation

/// Resolves a label to a screen coordinate by walking the frontmost app's AX tree.
/// Returns CG screen coordinates (top-left origin) so callers can post CGEvents
/// directly without a coordinate-space round-trip.
///
/// Does NOT gate on AXIsProcessTrusted() — it returns stale `false` on macOS 26
/// and after app re-signs even when permission is granted (see
/// AppState.checkAccessibilityPermission for the workaround).
final class OmiElementResolver: @unchecked Sendable {
    static let shared = OmiElementResolver()
    private init() {}

    func resolve(label: String) async -> (point: CGPoint, app: NSRunningApplication)? {
        guard let frontmostApp = await MainActor.run(body: { NSWorkspace.shared.frontmostApplication }) else {
            log("OmiElementResolver: no frontmost application found")
            return nil
        }

        let pid = frontmostApp.processIdentifier
        let bundleId = frontmostApp.bundleIdentifier ?? frontmostApp.localizedName ?? "unknown"

        let frame: CGRect? = await Task.detached(priority: .userInitiated) {
            let appElement = AXUIElementCreateApplication(pid)
            AXUIElementSetMessagingTimeout(appElement, 0.4)

            // Electron apps (Spotify, Slack, VS Code, Discord, Cursor, Notion,
            // Figma) only expose their full AX tree when this is set. Native
            // apps return kAXErrorAttributeUnsupported — ignore.
            _ = AXUIElementSetAttributeValue(appElement, "AXManualAccessibility" as CFString, kCFBooleanTrue)

            return Self.findBestMatch(in: appElement, query: label)
        }.value

        guard let frame else {
            log("OmiElementResolver: no matching element found for label '\(label)' in app \(bundleId)")
            return nil
        }

        let centerPoint = CGPoint(x: frame.midX, y: frame.midY)
        log("OmiElementResolver: resolved '\(label)' to point \(centerPoint) in app \(bundleId)")
        return (point: centerPoint, app: frontmostApp)
    }

    private static func findBestMatch(in appElement: AXUIElement, query: String) -> CGRect? {
        let queryNormalized = normalizeLabel(query)
        guard !queryNormalized.isEmpty else { return nil }
        let queryWords = meaningfulWords(from: queryNormalized)

        var bestScore = 0
        var bestFrame: CGRect?

        let deadline = Date().addingTimeInterval(0.5)
        var nodesVisited = 0
        let nodeBudget = 3000
        // Anything ≥ 110 means exact label match with role boost — no chance
        // a deeper node beats it, so we stop walking.
        let earlyExitScore = 110

        func walk(_ node: AXUIElement, depth: Int) {
            guard depth < 14,
                  nodesVisited < nodeBudget,
                  Date() < deadline,
                  bestScore < earlyExitScore
            else { return }
            nodesVisited += 1

            if let attrs = batchReadAttributes(node) {
                let role = attrs.role
                let roleMatters = role.isEmpty || pointableRoles.contains(role) || role == "AXStaticText"
                if roleMatters,
                   let score = scoreCandidate(
                       queryNormalized: queryNormalized,
                       queryWords: queryWords,
                       role: role,
                       title: attrs.title,
                       description: attrs.description,
                       value: attrs.value,
                       help: attrs.help
                   ),
                   score > bestScore,
                   let frame = attrs.frame,
                   frame.width > 0, frame.height > 0,
                   frame.width <= 800, frame.height <= 800,
                   !isDisabled(node)
                {
                    bestScore = score
                    bestFrame = frame
                    if bestScore >= earlyExitScore { return }
                }
            }

            var childrenRef: AnyObject?
            if AXUIElementCopyAttributeValue(node, kAXChildrenAttribute as CFString, &childrenRef) == .success,
               let children = childrenRef as? [AXUIElement] {
                for child in children {
                    if Date() > deadline || nodesVisited >= nodeBudget || bestScore >= earlyExitScore { return }
                    walk(child, depth: depth + 1)
                }
            }
        }

        walk(appElement, depth: 0)

        // Menu bar items aren't reachable from the focused window tree but
        // are highly relevant ("click File menu"). Skip if budget exhausted.
        if bestScore < earlyExitScore, Date() < deadline, nodesVisited < nodeBudget {
            var menuBarRef: AnyObject?
            if AXUIElementCopyAttributeValue(appElement, kAXMenuBarAttribute as CFString, &menuBarRef) == .success,
               let menuBar = menuBarRef {
                walk(menuBar as! AXUIElement, depth: 0)
            }
        }

        return bestFrame
    }

    private static let pointableRoles: Set<String> = [
        "AXButton", "AXMenuItem", "AXMenuBarItem", "AXPopUpButton",
        "AXCheckBox", "AXRadioButton", "AXLink", "AXTabGroup",
        "AXTextField", "AXTextArea", "AXComboBox", "AXSlider",
        "AXMenuButton", "AXToolbar", "AXImage", "AXCell", "AXRow"
    ]

    private static let roleHintKeywords: [String: Set<String>] = [
        "menu": ["AXMenu", "AXMenuItem", "AXMenuBarItem", "AXMenuButton", "AXPopUpButton"],
        "button": ["AXButton", "AXMenuButton", "AXPopUpButton"],
        "tab": ["AXTabGroup"],
        "field": ["AXTextField", "AXTextArea", "AXComboBox"],
        "input": ["AXTextField", "AXTextArea", "AXComboBox"],
        "search": ["AXTextField", "AXSearchField", "AXComboBox"],
        "textbox": ["AXTextField", "AXTextArea"],
        "checkbox": ["AXCheckBox"],
        "radio": ["AXRadioButton"],
        "link": ["AXLink"],
        "slider": ["AXSlider"],
        "cell": ["AXCell", "AXRow"],
        "row": ["AXRow", "AXCell"],
        "image": ["AXImage"],
        "icon": ["AXImage", "AXButton"],
        "toolbar": ["AXToolbar"]
    ]

    private static func scoreCandidate(
        queryNormalized: String,
        queryWords: Set<String>,
        role: String,
        title: String,
        description: String,
        value: String,
        help: String
    ) -> Int? {
        let isPointable = pointableRoles.contains(role)
        var roleBoost = isPointable ? 10 : 0
        for (keyword, matchingRoles) in roleHintKeywords {
            if queryNormalized.contains(keyword) && matchingRoles.contains(role) {
                roleBoost += 8
                break
            }
        }

        let candidateTexts = [title, description, value, help].filter { !$0.isEmpty }
        guard !candidateTexts.isEmpty else { return nil }

        var bestScore = 0
        for text in candidateTexts {
            let normalized = normalizeLabel(text)
            if normalized.isEmpty { continue }

            if normalized == queryNormalized {
                bestScore = max(bestScore, 100)
                continue
            }
            if normalized.hasPrefix(queryNormalized) || normalized.hasSuffix(queryNormalized) {
                bestScore = max(bestScore, 80)
                continue
            }
            if normalized.contains(queryNormalized) || queryNormalized.contains(normalized) {
                bestScore = max(bestScore, 60)
                continue
            }
            let textWords = meaningfulWords(from: normalized)
            let overlap = textWords.intersection(queryWords)
            if !overlap.isEmpty {
                let coverage = Double(overlap.count) / Double(max(queryWords.count, 1))
                bestScore = max(bestScore, Int(coverage * 40))
            }
            if bestScore < 30, jaroWinklerSimilarity(normalized, queryNormalized) >= 0.85 {
                let similarity = jaroWinklerSimilarity(normalized, queryNormalized)
                bestScore = max(bestScore, Int(similarity * 35))
            }
        }

        guard bestScore > 0 else { return nil }
        return bestScore + roleBoost
    }

    private static func normalizeLabel(_ raw: String) -> String {
        var s = raw.lowercased()
        s = s.replacingOccurrences(of: "&", with: "")
        s = s.replacingOccurrences(of: "…", with: "")
        s = s.replacingOccurrences(of: "...", with: "")
        if let parenIndex = s.firstIndex(of: "(") {
            s = String(s[..<parenIndex])
        }
        let collapsed = s
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
        return collapsed.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static let stopWords: Set<String> = [
        "the", "a", "an", "this", "that", "these", "those",
        "button", "icon", "menu", "bar", "tab", "panel", "item", "option",
        "link", "field", "input", "box", "area", "section", "row", "cell",
        "on", "in", "at", "of", "to", "for", "with"
    ]

    private static func meaningfulWords(from text: String) -> Set<String> {
        let rawWords = text.split { !$0.isLetter && !$0.isNumber }.map(String.init)
        let filtered = rawWords.filter { !stopWords.contains($0) && $0.count > 1 }
        return Set(filtered.isEmpty ? rawWords : filtered)
    }

    private static func jaroWinklerSimilarity(_ s1: String, _ s2: String) -> Double {
        let a = Array(s1)
        let b = Array(s2)
        if a.isEmpty && b.isEmpty { return 1.0 }
        if a.isEmpty || b.isEmpty { return 0.0 }

        let matchDistance = max(a.count, b.count) / 2 - 1
        var aMatches = [Bool](repeating: false, count: a.count)
        var bMatches = [Bool](repeating: false, count: b.count)
        var matches = 0

        for i in 0..<a.count {
            let start = max(0, i - matchDistance)
            let end = min(i + matchDistance + 1, b.count)
            guard start < end else { continue }
            for j in start..<end {
                if bMatches[j] { continue }
                if a[i] != b[j] { continue }
                aMatches[i] = true
                bMatches[j] = true
                matches += 1
                break
            }
        }

        if matches == 0 { return 0.0 }

        var transpositions = 0
        var k = 0
        for i in 0..<a.count where aMatches[i] {
            while !bMatches[k] { k += 1 }
            if a[i] != b[k] { transpositions += 1 }
            k += 1
        }

        let m = Double(matches)
        let jaro = (m / Double(a.count)
                    + m / Double(b.count)
                    + (m - Double(transpositions) / 2.0) / m) / 3.0

        var prefixLength = 0
        for i in 0..<min(4, min(a.count, b.count)) {
            if a[i] == b[i] { prefixLength += 1 } else { break }
        }
        return jaro + Double(prefixLength) * 0.1 * (1.0 - jaro)
    }

    private struct BatchedAttributes {
        let role: String
        let title: String
        let description: String
        let value: String
        let help: String
        let frame: CGRect?
    }

    private static let batchedAttributeNames: [CFString] = [
        kAXRoleAttribute as CFString,
        kAXTitleAttribute as CFString,
        kAXDescriptionAttribute as CFString,
        kAXValueAttribute as CFString,
        kAXHelpAttribute as CFString,
        kAXPositionAttribute as CFString,
        kAXSizeAttribute as CFString
    ]

    private static func batchReadAttributes(_ node: AXUIElement) -> BatchedAttributes? {
        var rawValues: CFArray?
        let status = AXUIElementCopyMultipleAttributeValues(
            node,
            batchedAttributeNames as CFArray,
            AXCopyMultipleAttributeOptions(rawValue: 0),
            &rawValues
        )
        guard status == .success,
              let rawValues = rawValues as [AnyObject]?,
              rawValues.count == batchedAttributeNames.count
        else {
            return nil
        }

        func stringAt(_ index: Int) -> String {
            if let s = rawValues[index] as? String { return s }
            return ""
        }

        var frame: CGRect?
        let positionRaw = rawValues[5]
        let sizeRaw = rawValues[6]
        if CFGetTypeID(positionRaw) == AXValueGetTypeID(),
           CFGetTypeID(sizeRaw) == AXValueGetTypeID() {
            var position = CGPoint.zero
            var size = CGSize.zero
            AXValueGetValue(positionRaw as! AXValue, .cgPoint, &position)
            AXValueGetValue(sizeRaw as! AXValue, .cgSize, &size)
            frame = CGRect(origin: position, size: size)
        }

        return BatchedAttributes(
            role: stringAt(0),
            title: stringAt(1),
            description: stringAt(2),
            value: stringAt(3),
            help: stringAt(4),
            frame: frame
        )
    }

    private static func isDisabled(_ node: AXUIElement) -> Bool {
        var valueRef: AnyObject?
        guard AXUIElementCopyAttributeValue(node, kAXEnabledAttribute as CFString, &valueRef) == .success else {
            return false
        }
        return (valueRef as? Bool) == false
    }
}
