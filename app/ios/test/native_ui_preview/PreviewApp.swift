import SwiftUI

@main
struct PreviewApp: App {
    @StateObject private var harness = PreviewHarness()
    var body: some Scene {
        WindowGroup {
            Group {
                if ProcessInfo.processInfo.arguments.contains("modal") {
                    ModalFixture()
                } else if ProcessInfo.processInfo.arguments.contains("surface") || ProcessInfo.processInfo.arguments.contains("chat") || ProcessInfo.processInfo.arguments.contains("settings-menu") {
                    NativeSurfaceView(state: harness.surface)
                } else { NativeHomeView(state: harness.state) }
            }
                .task {
                    if ProcessInfo.processInfo.arguments.contains("late-toolbar") {
                        try? await Task.sleep(nanoseconds: 500_000_000)
                        harness.revealOnboardingChrome()
                    }
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
                        if ProcessInfo.processInfo.arguments.contains("keypad") {
                            Button("Burst 123*#") { harness.burstKeys() }.accessibilityIdentifier("preview-burst-keys")
                        }
                    }.font(.caption).padding()
                    }
                }
        }
    }
}

/// Exercises the actual UIKit presenter and production SwiftUI form without an account or API.
private struct ModalFixture: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> ModalFixtureController { ModalFixtureController() }
    func updateUIViewController(_ controller: ModalFixtureController, context: Context) {}
}

@MainActor
private final class ModalFixtureModel: ObservableObject {
    @Published var receipt = "No changes saved"
    var open: () -> Void = {}
}

@MainActor
private final class ModalFixtureController: UIViewController {
    private let model = ModalFixtureModel()
    private lazy var presenter = NativeModalPresenter(rootController: { [weak self] in self })

    override func viewDidLoad() {
        super.viewDidLoad()
        let child = UIHostingController(rootView: ModalFixtureControls(model: model))
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(child.view)
        child.didMove(toParent: self)
        model.open = { [weak self] in self?.open() }
    }

    private func open() {
        func row(_ id: String, _ title: String, _ kind: String, _ value: Any? = nil) -> [String: Any] {
            var result: [String: Any] = ["id": id, "title": title, "kind": kind,
                "subtitle": "", "options": [], "enabled": true, "destructive": false]
            if let value { result["value"] = value }
            return result
        }
        var snapshot: [String: Any] = ["version": 1, "revision": 0, "title": "Edit Person", "appearance": "dark",
            "locale": "en", "direction": "ltr", "loading": false, "failed": false, "empty": "",
            "toolbar": [row("cancel", "Cancel", "button"), row("save", "Save", "button")],
            "searchEnabled": false, "searchValue": "", "searchPlaceholder": "", "refreshEnabled": false,
            "error": "Could not save", "retry": "Retry", "loadingLabel": "Loading"]
        let alert = ProcessInfo.processInfo.arguments.contains("alert")
        snapshot["sections"] = [["id": "fields", "title": "", "footer": "", "rows": alert
            ? [row("message", "Delete the selected person?", "label")]
            : [row("draft", "Name", "text", ""), row("opt_out", "Do not ask again", "toggle", false)]]]
        let args: [String: Any] = ["requestId": 1, "cancelId": "cancel", "snapshot": snapshot,
            "alert": alert, "dismissible": true, "guardEdits": true,
            "discard": ["title": "Discard Changes?", "message": "Your changes have not been saved.",
                "confirm": "Discard", "cancel": "Keep Editing"]]
        do {
            try presenter.present(args) { [weak self] response in
                guard let self else { return }
                if let response = response as? [String: Any], response["action"] as? String == "save",
                   let values = response["values"] as? [String: Any] {
                    self.model.receipt = "saved:\(values["draft"] as? String ?? ""):\(values["opt_out"] as? Bool ?? false)"
                } else { self.model.receipt = "Cancelled without saving" }
            }
            if ProcessInfo.processInfo.arguments.contains("expire") {
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    self?.presenter.dismiss(id: 1)
                }
            }
        } catch { model.receipt = "Presentation failed" }
    }
}

private struct ModalFixtureControls: View {
    @ObservedObject var model: ModalFixtureModel
    var body: some View {
        VStack(spacing: 20) {
            Button("Open Editor", action: model.open).accessibilityIdentifier("modal-open")
            Text(model.receipt).accessibilityIdentifier("modal-receipt")
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

@MainActor
final class PreviewHarness: ObservableObject {
    @Published var lastAction = "Preview fixture"
    @Published var lastSaved = ""
    var raw: [String: Any]
    var lastDraft = ""
    var keysSent = ""
    func burstKeys() {
        Task {
            let first = Task { await surface.send("keypad", value: "1") }
            while !surface.pending.contains("keypad") { await Task.yield() }
            for key in "23*#" { await surface.send("keypad", value: String(key)) }
            await surface.send("save")
            await first.value
        }
    }
    func revealOnboardingChrome() {
        surfaceRaw["revision"] = (surfaceRaw["revision"] as? Int ?? 0) + 1
        surfaceRaw["toolbar"] = [["id": "onboarding_back", "title": "Back", "kind": "button",
            "symbol": "chevron.left", "subtitle": "", "options": [], "enabled": true, "destructive": false]]
        surface.update(try! NativeSurfaceSnapshot.decode(surfaceRaw))
    }
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
        // Visibility notifications do not change fixture content or erase a command receipt.
        if id.hasPrefix("_visible:") || id.hasPrefix("_hidden:") { return }
        try await Task.sleep(nanoseconds: 200_000_000)
        if ProcessInfo.processInfo.arguments.contains("failed-key") && id == "keypad" {
            throw NSError(domain: "Fixture", code: 2)
        }
        if ProcessInfo.processInfo.arguments.contains("failed-edit") && id == "draft" {
            throw NSError(domain: "Fixture", code: 1)
        }
        if id == "draft" || id == "chat_draft" { self.lastDraft = value as? String ?? "" }
        self.lastAction = "\(id):\(value ?? "")"
        if id == "keypad", let key = value as? String { self.keysSent += key + "," }
        if id == "save" && ProcessInfo.processInfo.arguments.contains("keypad") {
            self.lastSaved = "keys:\(self.keysSent)"
        }
        else if id == "save" || id == "chat_send" { self.lastSaved = "saved:\(self.lastDraft)" }
        var next = self.surfaceRaw
        next["revision"] = (next["revision"] as! Int) + 1
        if var sections = next["sections"] as? [[String: Any]] {
            for index in sections.indices {
                var rows = sections[index]["rows"] as! [[String: Any]]
                for rowIndex in rows.indices where rows[rowIndex]["id"] as? String == id {
                    if id == "keypad", let key = value as? String {
                        let previous = rows[rowIndex]["value"] as? String ?? ""
                        rows[rowIndex]["value"] = key == "clear" ? "" : key == "erase" ? String(previous.dropLast()) : previous + key
                    } else if ["text", "toggle", "choice", "slider"].contains(rows[rowIndex]["kind"] as? String ?? "") { rows[rowIndex]["value"] = value }
                }
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
        if var reader = next["reader"] as? [String: Any] {
            if id.hasPrefix("segment:") {
                reader["targetId"] = id
                reader["currentId"] = id
                reader["following"] = true
                reader["request"] = (reader["request"] as? Int ?? 0) + 1
            }
            if id == "reader_scroll" { reader["following"] = false }
            var footer = reader["footer"] as! [[String: Any]]
            for index in footer.indices where footer[index]["id"] as? String == id {
                if id == "position" { footer[index]["value"] = value }
                if id == "play" { footer[index]["title"] = "Pause"; footer[index]["symbol"] = "pause.fill" }
            }
            reader["footer"] = footer
            next["reader"] = reader
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
        if ProcessInfo.processInfo.arguments.contains("reader") {
            func row(_ id: String, _ title: String, _ kind: String) -> [String: Any] {
                ["id": id, "title": title, "kind": kind, "subtitle": "", "options": [], "enabled": true, "destructive": false]
            }
            surfaceRaw["title"] = "Sprint planning"
            surfaceRaw["searchEnabled"] = true
            var back = row("back", "Back", "button"); back["symbol"] = "chevron.left"
            surfaceRaw["toolbar"] = [back]
            let rows = (0..<20).map { index -> [String: Any] in
                var value = row("segment:\(index)", "Line \(index): Keep **two stars** in the transcript. A longer line lets the reader move through the conversation without clipping its words.", "transcript")
                value["subtitle"] = "Speaker 1 · \(index * 10)s"
                value["options"] = [["id": "edit", "title": "Edit"], ["id": "speaker", "title": "Name Speaker"]]
                return value
            }
            surfaceRaw["sections"] = [["id": "transcript", "title": "Transcript", "footer": "", "rows": rows]]
            var slider = row("position", "Recordings", "slider"); slider["value"] = 0.0; slider["maximumValue"] = 200.0
            slider["subtitle"] = "3m 20s left · Missing audio in the recording"
            let points: [[String: Any]] = (0..<20).map { index in
                let x = Double(index * 10 + 5)
                let label = index == 5 ? "missing" : ""
                return ["x": x, "y": 0.4, "label": label]
            }
            slider["points"] = points
            var play = row("play", "Play", "button"); play["symbol"] = "play.fill"
            var ask = row("ask", "Ask Omi", "button"); ask["symbol"] = "bubble.left"
            var scroll = row("reader_scroll", "Transcript", "menu")
            scroll["options"] = [["id": "suspend", "title": "Suspend"]] + rows.map { ["id": $0["id"] as! String, "title": "Line"] }
            surfaceRaw["reader"] = ["currentId": "segment:0", "request": 0, "following": false,
                "footer": [slider, play, ask], "scroll": scroll]
        }
        if ProcessInfo.processInfo.arguments.contains("keypad") {
            surfaceRaw["title"] = "Phone Calls"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "dialer", "title": "", "footer": "", "rows": [
                ["id": "keypad", "title": "Enter number", "kind": "keypad", "subtitle": "", "value": "",
                 "keypadMode": ProcessInfo.processInfo.arguments.contains("dtmf") ? "dtmf" : "dialer",
                 "eraseLabel": "Delete", "clearLabel": "Clear All",
                 "options": "123456789*0#".map { ["id": String($0), "title": $0 == "0" ? "+" : ""] },
                 "enabled": true, "destructive": false]
            ]]]
        }
        if ProcessInfo.processInfo.arguments.contains("photo") {
            let url = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("native-photo-fixture.png")
            if !FileManager.default.fileExists(atPath: url.path) {
                let image = UIGraphicsImageRenderer(size: CGSize(width: 640, height: 400)).image { context in
                    UIColor.systemBlue.setFill()
                    context.fill(CGRect(x: 0, y: 0, width: 640, height: 400))
                    UIColor.systemYellow.setFill()
                    context.fill(CGRect(x: 0, y: 0, width: 320, height: 200))
                    UIColor.systemRed.setFill()
                    context.fill(CGRect(x: 320, y: 200, width: 320, height: 200))
                }
                try? image.pngData()?.write(to: url)
            }
            var photo: [String: Any] = ["id": "photo", "title": "Synthetic photo", "kind": "image",
                "subtitle": "", "options": [], "enabled": true, "destructive": false]
            photo["imageUri"] = url.absoluteString
            photo["maximumValue"] = 4.0
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "photo_section", "title": "", "footer": "", "rows": [photo]]]
        }
        if ProcessInfo.processInfo.arguments.contains("plain-transcript") {
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "transcript", "title": "", "footer": "", "rows": [
                ["id": "plain_segment", "title": "Say **two stars** and [a link](https://example.com)",
                 "kind": "message_ai", "plainText": true, "subtitle": "Speaker 1", "options": [],
                 "enabled": false, "destructive": false]
            ]]]
        }
        if ProcessInfo.processInfo.arguments.contains("late-toolbar") {
            surfaceRaw["title"] = "Here is what I heard"
            surfaceRaw["toolbar"] = []
        }
        if ProcessInfo.processInfo.arguments.contains("country") {
            surfaceRaw["title"] = "Enter your number"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "phone", "title": "", "footer": "", "rows": [
                ["id": "country", "title": "Select Country", "kind": "choice", "subtitle": "", "value": "US",
                 "optionSearch": "Search countries", "optionClose": "Close",
                 "options": [["id": "US", "title": "🇺🇸 United States +1"], ["id": "EE", "title": "🇪🇪 Estonia +372"]],
                 "enabled": true, "destructive": false],
                ["id": "phone", "title": "Phone number", "kind": "text", "keyboard": "phone", "subtitle": "",
                 "value": "", "options": [], "enabled": true, "destructive": false]
            ]]]
        }
        if ProcessInfo.processInfo.arguments.contains("settings-menu") {
            surfaceRaw["largeTitle"] = true
            surfaceRaw["toolbar"] = [["id": "settings_close", "title": "Close", "kind": "button", "symbol": "xmark", "subtitle": "", "options": [], "enabled": true, "destructive": false]]
            func navigation(_ id: String, _ title: String, _ symbol: String, _ subtitle: String = "") -> [String: Any] {
                ["id": id, "title": title, "kind": "navigation", "symbol": symbol, "subtitle": subtitle, "options": [], "enabled": true, "destructive": false]
            }
            surfaceRaw["sections"] = [
                ["id": "account", "title": "", "footer": "", "rows": [navigation("account", "Ada", "person.crop.circle", "ada@example.com")]],
                ["id": "plan", "title": "", "footer": "", "rows": [navigation("plan", "Plan & Usage", "chart.xyaxis.line"), navigation("referral", "Referral Program", "gift", "NEW")]],
                ["id": "groups", "title": "", "footer": "", "rows": [navigation("device", "Device", "antenna.radiowaves.left.and.right"), navigation("integrations", "Integrations", "point.3.connected.trianglepath.dotted", "BETA")]],
            ]
        }
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
        if ProcessInfo.processInfo.arguments.contains("attachments"), var chat = surfaceRaw["chat"] as? [String: Any] {
            var actions = chat["actions"] as! [[String: Any]]
            actions.append(["id": "chat_attach", "title": "Add Attachment", "kind": "menu", "symbol": "paperclip", "subtitle": "",
                "options": [["id": "file", "title": "Choose File"], ["id": "photos", "title": "Photo Library"]], "enabled": true, "destructive": false])
            chat["actions"] = actions
            surfaceRaw["chat"] = chat
        }
        if ProcessInfo.processInfo.arguments.contains("voice"), var chat = surfaceRaw["chat"] as? [String: Any] {
            chat["actions"] = [
                ["id": "chat_voice_status", "title": "Recording", "kind": "label", "subtitle": "", "options": [], "enabled": false, "destructive": false],
                ["id": "chat_voice_waveform", "title": "Recording", "kind": "waveform", "subtitle": "", "options": [], "enabled": false, "destructive": false,
                    "points": (0..<20).map { ["x": Double($0), "y": Double(($0 % 5) + 1) / 5, "label": ""] as [String: Any] }],
                ["id": "chat_voice_stop", "title": "Stop Recording", "kind": "button", "symbol": "stop.fill", "subtitle": "", "options": [], "enabled": true, "destructive": false],
                ["id": "chat_voice_discard", "title": "Discard Recording", "kind": "button", "symbol": "xmark", "subtitle": "", "options": [], "enabled": true, "destructive": false],
            ]
            surfaceRaw["chat"] = chat
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
