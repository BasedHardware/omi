import SwiftUI

@main
struct PreviewApp: App {
    @StateObject private var harness = PreviewHarness()
    var body: some Scene {
        WindowGroup {
            Group {
                if ProcessInfo.processInfo.arguments.contains("surface") || ProcessInfo.processInfo.arguments.contains("chat") {
                    NativeSurfaceView(state: harness.surface)
                } else { NativeHomeView(state: harness.state) }
            }
                .environment(\.dynamicTypeSize, ProcessInfo.processInfo.arguments.contains("large") ? .accessibility3 : .large)
                .overlay(alignment: .top) {
                    if ProcessInfo.processInfo.arguments.contains("chrome") {
                        Text(harness.lastAction).font(.caption2).allowsHitTesting(false)
                            .accessibilityIdentifier("preview-last-action")
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    if !ProcessInfo.processInfo.arguments.contains("chrome") {
                    HStack {
                        VStack {
                            Text(harness.lastAction).accessibilityIdentifier("preview-last-action")
                            Text(harness.lastSaved).accessibilityIdentifier("preview-last-saved")
                        }
                        Spacer()
                        Button("End test session") { harness.state.invalidate(); harness.surface.invalidate() }
                            .accessibilityIdentifier("preview-end-session")
                    }.font(.caption).padding()
                    }
                }
        }
    }
}

@MainActor
final class PreviewHarness: ObservableObject {
    @Published var lastAction = "Preview fixture"
    @Published var lastSaved = ""
    var raw: [String: Any]
    var lastDraft = ""
    lazy var state: NativeHomeState = NativeHomeState(snapshot: try! NativeHomeSnapshot.decode(raw)) { [weak self] method, id in
        guard let self else { return nil }
        self.lastAction = "\(method):\(id ?? "")"
        if method == "detail" {
            return try NativeHomeSnapshot.decode(self.original).conversation(id: id ?? "")
        }
        if method == "refresh" {
            var snapshot = self.original
            snapshot["revision"] = 3
            self.state.update(try NativeHomeSnapshot.decode(snapshot))
        }
        return nil
    }
    lazy var surface: NativeSurfaceState = NativeSurfaceState(snapshot: try! NativeSurfaceSnapshot.decode(surfaceRaw)) { [weak self] id, value in
        guard let self else { return }
        try await Task.sleep(nanoseconds: 200_000_000)
        if ProcessInfo.processInfo.arguments.contains("failed-edit") && id == "draft" {
            throw NSError(domain: "Fixture", code: 1)
        }
        if id == "draft" || id == "chat_draft" { self.lastDraft = value as? String ?? "" }
        self.lastAction = "\(id):\(value ?? "")"
        if id == "save" || id == "chat_send" { self.lastSaved = "saved:\(self.lastDraft)" }
        var next = self.surfaceRaw
        next["revision"] = (next["revision"] as! Int) + 1
        if var sections = next["sections"] as? [[String: Any]] {
            for index in sections.indices {
                var rows = sections[index]["rows"] as! [[String: Any]]
                for rowIndex in rows.indices where rows[rowIndex]["id"] as? String == id { rows[rowIndex]["value"] = value }
                sections[index]["rows"] = rows
            }
            next["sections"] = sections
        }
        if var chat = next["chat"] as? [String: Any], id == "chat_draft" || id == "chat_send" {
            let draft = id == "chat_send" ? "" : value as? String ?? ""
            chat["draft"] = draft
            var actions = chat["actions"] as! [[String: Any]]
            actions[0]["value"] = draft
            chat["actions"] = actions
            next["chat"] = chat
        }
        self.surfaceRaw = next
        self.surface.update(try NativeSurfaceSnapshot.decode(next))
    }
    var surfaceRaw: [String: Any] = ["version": 1, "revision": 0, "title": "Settings", "appearance": "dark", "locale": "en", "direction": "ltr",
        "loading": false, "failed": false, "empty": "", "toolbar": [["id": "save", "title": "Save", "kind": "button", "subtitle": "", "options": [], "enabled": true, "destructive": false]], "searchEnabled": true, "searchValue": "", "searchPlaceholder": "Search",
        "refreshEnabled": false, "error": "Error", "retry": "Retry", "loadingLabel": "Loading",
        "sections": [["id": "settings", "title": "Appearance", "footer": "Follow the phone or choose an appearance", "rows": [
            ["id": "draft", "title": "Draft", "kind": "text", "subtitle": "", "value": "", "options": [], "enabled": true, "destructive": false],
            ["id": "mode", "title": "Appearance", "kind": "choice", "subtitle": "", "value": "system",
                "options": [["id": "system", "title": "System"], ["id": "dark", "title": "Dark"]], "enabled": true, "destructive": false],
            ["id": "enabled", "title": "Notifications", "kind": "toggle", "subtitle": "", "value": true, "options": [], "enabled": true, "destructive": false]
        ]]]]
    let original: [String: Any]

    init() {
        let data = try! Data(contentsOf: Bundle.main.url(forResource: "native_home_v1", withExtension: "json")!)
        original = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
        raw = original
        if ProcessInfo.processInfo.arguments.contains("chat") {
            surfaceRaw["title"] = "Ask Omi"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["toolbar"] = []
            surfaceRaw["chat"] = ["draft": "", "placeholder": "Ask Omi", "streaming": false, "followup": "",
                "actions": [["id": "chat_draft", "title": "Ask Omi", "kind": "text", "subtitle": "", "value": "", "options": [], "enabled": true, "destructive": false],
                    ["id": "chat_send", "title": "Send", "kind": "button", "symbol": "arrow.up", "subtitle": "", "options": [], "enabled": true, "destructive": false]]]
            surfaceRaw["sections"] = [["id": "messages", "title": "", "footer": "", "rows": [
                ["id": "message_1", "title": "What did we discuss?", "kind": "message_user", "subtitle": "", "options": [], "enabled": false, "destructive": false],
                ["id": "message_2", "title": "We discussed the **native iOS migration**.", "kind": "message_ai", "subtitle": "", "options": [], "enabled": false, "destructive": false]]]]
        }
        if ProcessInfo.processInfo.arguments.contains("chrome") {
            raw["chrome"] = ["home": "Home", "tasks": "Tasks", "ask": "Ask Omi", "recapsTitle": "Daily Recaps",
                "header": [["id": "device", "title": "53%", "symbol": "battery.75percent", "enabled": true],
                    ["id": "calls", "title": "Phone Calls", "symbol": "phone", "enabled": true],
                    ["id": "sync", "title": "Sync", "symbol": "icloud", "enabled": true],
                    ["id": "search", "title": "Search", "symbol": "magnifyingglass", "enabled": true],
                    ["id": "settings", "title": "Settings", "symbol": "gearshape", "enabled": true]],
                "footer": [["id": "chat", "title": "Ask Omi", "symbol": "bubble.left", "enabled": true],
                    ["id": "voice", "title": "Voice", "symbol": "mic", "enabled": true],
                    ["id": "record", "title": "Record", "symbol": "record.circle", "enabled": true],
                    ["id": "tasks", "title": "Tasks", "symbol": "checklist", "enabled": true]], "alerts": [],
                "recaps": [["id": "recap-1", "title": "A Busy Day of Shopping and Omi", "date": "Tue, Sep 29", "emoji": "🛍️"]],
                "capture": ["status": "Listening", "detail": "", "elapsed": "12:04", "source": "omi", "lastLine": "Keep the pendant flow as it is.", "explanation": "",
                    "actions": [["id": "pauseCapture", "title": "Pause", "symbol": "pause.fill", "enabled": true]]]]
        }
        if ProcessInfo.processInfo.arguments.contains("light") { raw["appearance"] = "light" }
        else { raw["appearance"] = "dark" }
        if ProcessInfo.processInfo.arguments.contains("error") || ProcessInfo.processInfo.arguments.contains("empty") {
            raw["groups"] = []
            raw["localRecordingCount"] = 0
            raw["hasMore"] = false
            raw["failed"] = ProcessInfo.processInfo.arguments.contains("error")
        }
    }
}
