import SwiftUI

@main
struct PreviewApp: App {
    @StateObject private var harness = PreviewHarness()
    var body: some Scene {
        WindowGroup {
            Group {
                if ProcessInfo.processInfo.arguments.contains("navigation") {
                    VStack(spacing: 0) {
                        NativeHomeView(state: harness.state)
                        NativeSurfaceView(state: harness.surface).frame(height: 98)
                    }.ignoresSafeArea(edges: .bottom)
                } else if ProcessInfo.processInfo.arguments.contains("modal") {
                    ModalFixture()
                } else if ProcessInfo.processInfo.arguments.contains("toast") {
                    ToastFixture()
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
                .environment(\.nativeGraphReduceMotion, ProcessInfo.processInfo.arguments.contains("reduce-motion"))
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
                        if ProcessInfo.processInfo.arguments.contains("secret") {
                            Button("Resign") {
                                NotificationCenter.default.post(name: UIApplication.willResignActiveNotification, object: nil)
                            }.accessibilityIdentifier("preview-resign-active")
                            Button("Activate") {
                                NotificationCenter.default.post(name: UIApplication.didBecomeActiveNotification, object: nil)
                            }.accessibilityIdentifier("preview-become-active")
                        }
                        if ProcessInfo.processInfo.arguments.contains("selection") || ProcessInfo.processInfo.arguments.contains("reorder") {
                            Button("Burst list") { harness.burstListCommand() }.accessibilityIdentifier("preview-burst-list")
                        }
                        if ProcessInfo.processInfo.arguments.contains("graph-fill") {
                            Button("Zoom +") { harness.lastSaved = PreviewVoiceOver.adjust("graph_canvas_zoom", increment: true) }
                                .accessibilityIdentifier("preview-voiceover-increment")
                            Button("Zoom -") { harness.lastSaved = PreviewVoiceOver.adjust("graph_canvas_zoom", increment: false) }
                                .accessibilityIdentifier("preview-voiceover-decrement")
                        }
                    }.font(.caption).padding()
                    }
                }
        }
    }
}

/// Stands in for VoiceOver's swipe up and down, which XCUITest on iOS can neither send nor detect: it
/// finds the element in the app's own accessibility tree and adjusts it as VoiceOver does, only when
/// the element carries the adjustable trait.
@MainActor
enum PreviewVoiceOver {
    static func adjust(_ identifier: String, increment: Bool) -> String {
        var visited = Set<ObjectIdentifier>()
        for window in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).flatMap(\.windows) {
            guard let element = find(identifier, in: window, visited: &visited) else { continue }
            guard element.accessibilityTraits.contains(.adjustable) else { return "\(identifier):not-adjustable" }
            if increment { element.accessibilityIncrement() } else { element.accessibilityDecrement() }
            return "\(identifier):\(increment ? "incremented" : "decremented")"
        }
        return "\(identifier):missing"
    }

    private static func find(_ identifier: String, in element: NSObject, visited: inout Set<ObjectIdentifier>) -> NSObject? {
        guard visited.insert(ObjectIdentifier(element)).inserted else { return nil }
        if element.responds(to: NSSelectorFromString("accessibilityIdentifier")),
           element.value(forKey: "accessibilityIdentifier") as? String == identifier { return element }
        var children = element.accessibilityElements as? [NSObject] ?? []
        let count = element.accessibilityElementCount()
        if children.isEmpty, count != NSNotFound, count > 0 {
            children = (0..<count).compactMap { element.accessibilityElement(at: $0) as? NSObject }
        }
        if let view = element as? UIView { children += view.subviews }
        for child in children {
            if let found = find(identifier, in: child, visited: &visited) { return found }
        }
        return nil
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
    @Published var reason = ""
    @Published var beneath = 0
    var activity: () -> Void = {}
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
        model.activity = { [weak self] in self?.showActivity() }
    }

    /// The production activity overlay, which only a programmatic dismissal ends.
    private func showActivity() {
        let label = ProcessInfo.processInfo.arguments.contains("large")
            ? "Saving your changes to this conversation summary" : "Saving"
        var request: [String: Any] = ["requestId": 2, "label": label, "appearance": "dark", "locale": "en", "direction": "ltr"]
        do {
            try presenter.presentActivity(request) { [weak self] response in
                self?.model.reason = "reason:\((response as? [String: Any])?["reason"] as? String ?? "")"
            }
        } catch { model.receipt = "Presentation failed"; return }
        // The single slot refuses a second presentation while the activity is up.
        request["requestId"] = 3
        do {
            try presenter.presentActivity(request) { _ in }
            model.receipt = "Second presentation shown"
        } catch { model.receipt = "Second presentation refused" }
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            self?.presenter.dismiss(id: 2)
        }
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
            "alert": alert, "dismissible": !ProcessInfo.processInfo.arguments.contains("locked"), "guardEdits": true,
            "discard": ["title": "Discard Changes?", "message": "Your changes have not been saved.",
                "confirm": "Discard", "cancel": "Keep Editing"]]
        do {
            try presenter.present(args) { [weak self] response in
                guard let self else { return }
                if let response = response as? [String: Any], response["action"] as? String == "save",
                   let values = response["values"] as? [String: Any] {
                    self.model.receipt = "saved:\(values["draft"] as? String ?? ""):\(values["opt_out"] as? Bool ?? false)"
                } else { self.model.receipt = "Cancelled without saving" }
                self.model.reason = "reason:\((response as? [String: Any])?["reason"] as? String ?? "")"
            }
            if ProcessInfo.processInfo.arguments.contains("expire") {
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    self?.presenter.dismiss(id: 1)
                }
            }
            if ProcessInfo.processInfo.arguments.contains("foreign-dismiss") {
                // Another owner dismisses the sheet without telling the presenter.
                Task { [weak self] in
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                    self?.view.window?.rootViewController?.dismiss(animated: true)
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
            Text(model.reason).accessibilityIdentifier("modal-reason")
            Button("Show Activity", action: model.activity).accessibilityIdentifier("activity-open")
            Button("Content Beneath") { model.beneath += 1 }.accessibilityIdentifier("activity-beneath")
            Text("beneath:\(model.beneath)").accessibilityIdentifier("activity-beneath-count")
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Drives the production toast presenter and window above the fixture, a page sheet and a blocking overlay.
private struct ToastFixture: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> ToastFixtureController { ToastFixtureController() }
    func updateUIViewController(_ controller: ToastFixtureController, context: Context) {}
}

@MainActor
private final class ToastFixtureModel: ObservableObject {
    @Published var outcomes: [String] = []
    @Published var announcement = ""
    @Published var backgroundTaps = 0
    @Published var field = ""
    var show: (String) -> Void = { _ in }
    var dismiss: () -> Void = {}
    var presentSheet: () -> Void = {}
    var presentOverlay: () -> Void = {}
}

@MainActor
private final class ToastFixtureController: UIViewController {
    private let model = ToastFixtureModel()
    private var nextId = 0
    private lazy var presenter = NativeToastPresenter { [weak self] message in
        self?.model.announcement = message
        UIAccessibility.post(notification: .announcement, argument: message)
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        _ = presenter // Observe keyboard frames before any field can focus, as AppDelegate does at launch.
        let child = UIHostingController(rootView: ToastFixtureControls(model: model, prefix: "toast"))
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(child.view)
        child.didMove(toParent: self)
        model.show = { [weak self] kind in self?.show(kind) }
        model.dismiss = { [weak self] in self?.presenter.dismiss() }
        model.presentSheet = { [weak self] in
            guard let self else { return }
            self.present(ToastFixtureControls(model: self.model, prefix: "sheet"), style: .pageSheet)
        }
        model.presentOverlay = { [weak self] in
            guard let self else { return }
            self.present(ToastFixtureOverlay(model: self.model), style: .overFullScreen)
            self.show("undo")
        }
    }

    private func present<Content: View>(_ content: Content, style: UIModalPresentationStyle) {
        let controller = UIHostingController(rootView: content)
        controller.modalPresentationStyle = style
        if style == .overFullScreen { controller.view.backgroundColor = .clear }
        var parent: UIViewController = self
        while let presented = parent.presentedViewController { parent = presented }
        parent.present(controller, animated: false)
    }

    private func show(_ kind: String) {
        let arguments = ProcessInfo.processInfo.arguments
        let rtl = arguments.contains("rtl")
        nextId += 1
        var request: [String: Any] = ["requestId": nextId, "session": "preview", "kind": kind,
            "durationMs": NativeToastRequest.durations[kind] ?? 0, "bottomClearance": 64.0, "appearance": "dark",
            "locale": rtl ? "ar" : "en", "direction": rtl ? "rtl" : "ltr"]
        switch kind {
        case "undo":
            request["message"] = arguments.contains("long") ? String(repeating: "Conversation deleted with its transcript. ", count: 8) : "Conversation deleted"
            request["actionLabel"] = "Undo"
            request["symbol"] = "trash"
        case "error":
            request["message"] = "Could not save"
            request["actionLabel"] = "Try Again"
            request["closeLabel"] = "Close"
            request["symbol"] = "exclamationmark.circle.fill"
        case "progress":
            request["message"] = "Exporting…"
            request["symbol"] = "progress"
        default:
            request["message"] = "Saved"
            request["symbol"] = "checkmark.circle.fill"
        }
        let id = nextId
        do {
            try presenter.show(request) { [weak self] outcome in
                self?.model.outcomes.append("\(id):\(outcome as? String ?? "nil")")
            }
        } catch { model.outcomes.append("\(id):refused") }
    }
}

private struct ToastFixtureControls: View {
    @ObservedObject var model: ToastFixtureModel
    let prefix: String
    var body: some View {
        VStack(spacing: 12) {
            Button("Background \(model.backgroundTaps)") { model.backgroundTaps += 1 }
                .accessibilityIdentifier("\(prefix)-background")
            HStack {
                Button("Undo") { model.show("undo") }.accessibilityIdentifier("\(prefix)-undo")
                Button("Error") { model.show("error") }.accessibilityIdentifier("\(prefix)-error")
                Button("Saved") { model.show("confirm") }.accessibilityIdentifier("\(prefix)-confirm")
                Button("Progress") { model.show("progress") }.accessibilityIdentifier("\(prefix)-progress")
            }
            HStack {
                Button("Dismiss") { model.dismiss() }.accessibilityIdentifier("\(prefix)-dismiss")
                if prefix == "toast" {
                    Button("Sheet") { model.presentSheet() }.accessibilityIdentifier("toast-sheet")
                    Button("Overlay") { model.presentOverlay() }.accessibilityIdentifier("toast-overlay")
                }
            }
            TextField("Draft", text: $model.field).textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("\(prefix)-field")
            Text(model.outcomes.isEmpty ? "none" : model.outcomes.joined(separator: ","))
                .accessibilityIdentifier("\(prefix)-outcomes")
            Text(model.announcement.isEmpty ? "none" : model.announcement)
                .accessibilityIdentifier("\(prefix)-announcement")
            Spacer()
        }.padding()
    }
}

/// Stands in for a blocking activity overlay: it covers the screen and takes every touch beneath the toast.
private struct ToastFixtureOverlay: View {
    @ObservedObject var model: ToastFixtureModel
    var body: some View {
        ZStack {
            Color.black.opacity(0.4).ignoresSafeArea()
            VStack(spacing: 12) {
                ProgressView()
                Text(model.outcomes.isEmpty ? "none" : model.outcomes.joined(separator: ","))
                    .accessibilityIdentifier("overlay-outcomes")
            }.padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
        }.contentShape(Rectangle()).onTapGesture { model.backgroundTaps += 1 }
    }
}

@MainActor
final class PreviewHarness: ObservableObject {
    @Published var lastAction = "Preview fixture"
    @Published var lastSaved = ""
    var raw: [String: Any]
    var lastDraft = ""
    var keysSent = ""
    var listCommandsSent = ""
    /// Sends a list command, queues a newer one while it is pending and delivers an unrelated newer
    /// snapshot meanwhile: the queued desired state must still reach the owner.
    func burstListCommand() {
        let reorder = ProcessInfo.processInfo.arguments.contains("reorder")
        let id = reorder ? "_reorder:tasks" : "_selection"
        let first = reorder ? ["task_b", "task_a", "task_c"] : ["conv_1", "conv_2"]
        let second = reorder ? ["task_c", "task_b", "task_a"] : ["conv_1", "conv_2", "conv_3"]
        Task {
            let sending = Task { await surface.send(id, value: first) }
            while !surface.pending.contains(id) { await Task.yield() }
            await surface.send(id, value: second)
            surfaceRaw["revision"] = (surfaceRaw["revision"] as? Int ?? 0) + 1
            if ProcessInfo.processInfo.arguments.contains("stale-selection") {
                surfaceRaw["selection"] = ["selected": ["conv_1"], "selectable": ["conv_1", "conv_2"]]
            }
            surface.update(try! NativeSurfaceSnapshot.decode(surfaceRaw))
            await sending.value
        }
    }
    var levelSends = 0
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
        // Every commit that reaches the owner is counted, so a test proves dragging sent nothing.
        if id == "led_brightness" { self.levelSends += 1; self.lastSaved = "level-sends:\(self.levelSends)" }
        try await Task.sleep(nanoseconds: 200_000_000)
        if ProcessInfo.processInfo.arguments.contains("failed-level") && id == "led_brightness" {
            throw NSError(domain: "Fixture", code: 3)
        }
        if ProcessInfo.processInfo.arguments.contains("failed-key") && id == "keypad" {
            throw NSError(domain: "Fixture", code: 2)
        }
        if ProcessInfo.processInfo.arguments.contains("failed-edit") && id == "draft" {
            throw NSError(domain: "Fixture", code: 1)
        }
        if id == "_selection" && ProcessInfo.processInfo.arguments.contains("slow-selection") {
            try await Task.sleep(nanoseconds: 4_000_000_000)
        }
        if id == "_selection" && ProcessInfo.processInfo.arguments.contains("failed-selection") {
            throw NSError(domain: "Fixture", code: 4)
        }
        if id == "_reorder:tasks" && ProcessInfo.processInfo.arguments.contains("failed-reorder") {
            throw NSError(domain: "Fixture", code: 3)
        }
        if id == "draft" || id == "chat_draft" { self.lastDraft = value as? String ?? "" }
        self.lastAction = "\(id):\(value ?? "")"
        if let ids = value as? [String] {
            self.lastAction = "\(id):\(ids.joined(separator: ","))"
            self.listCommandsSent += ids.joined(separator: ",") + "|"
            self.lastSaved = "list:\(self.listCommandsSent)"
        }
        if id == "bulk_delete", let selection = self.surfaceRaw["selection"] as? [String: Any] {
            self.lastAction = "bulk_delete:\((selection["selected"] as? [String] ?? []).joined(separator: ","))"
        }
        if id == "keypad", let key = value as? String { self.keysSent += key + "," }
        if id == "save" && ProcessInfo.processInfo.arguments.contains("keypad") {
            self.lastSaved = "keys:\(self.keysSent)"
        }
        else if id == "save" || id == "chat_send" { self.lastSaved = "saved:\(self.lastDraft)" }
        var next = self.surfaceRaw
        next["revision"] = (next["revision"] as! Int) + 1
        if id == "main_destination", var navigation = next["navigation"] as? [String: Any] {
            navigation["value"] = value
            next["navigation"] = navigation
        }
        if var sections = next["sections"] as? [[String: Any]] {
            for index in sections.indices {
                var rows = sections[index]["rows"] as! [[String: Any]]
                for rowIndex in rows.indices where rows[rowIndex]["id"] as? String == id {
                    if id == "keypad", let key = value as? String {
                        let previous = rows[rowIndex]["value"] as? String ?? ""
                        rows[rowIndex]["value"] = key == "clear" ? "" : key == "erase" ? String(previous.dropLast()) : previous + key
                    } else if ["text", "toggle", "choice", "slider"].contains(rows[rowIndex]["kind"] as? String ?? "") { rows[rowIndex]["value"] = value }
                    else if rows[rowIndex]["kind"] as? String == "level", let level = value as? Double {
                        rows[rowIndex]["value"] = level
                        rows[rowIndex]["subtitle"] = "\(Int(level))%"
                    }
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
        if id == "_selection", let ids = value as? [String], var selection = next["selection"] as? [String: Any] {
            selection["selected"] = ids
            next["selection"] = selection
            if var bar = next["bottomBar"] as? [[String: Any]] {
                bar[0]["title"] = "\(ids.count) selected"
                next["bottomBar"] = bar
            }
        }
        if id.hasPrefix("_reorder:"), let ids = value as? [String], var sections = next["sections"] as? [[String: Any]] {
            for index in sections.indices where "_reorder:\(sections[index]["id"] as? String ?? "")" == id {
                let rows = sections[index]["rows"] as? [[String: Any]] ?? []
                sections[index]["rows"] = ids.compactMap { rowID in rows.first { $0["id"] as? String == rowID } }
            }
            next["sections"] = sections
        }
        if id == "graph_canvas" || id == "graph_card" {
            // Distinguish a background tap ('') from a card tap (nil).
            self.lastAction = "\(id):\(value.map { "'\($0)'" } ?? "nil")"
        }
        if id == "graph_canvas", let node = value as? String, var sections = next["sections"] as? [[String: Any]] {
            // The fixture owner selects the tapped node, as the Dart graph controller does.
            for index in sections.indices {
                var rows = sections[index]["rows"] as! [[String: Any]]
                for rowIndex in rows.indices where rows[rowIndex]["id"] as? String == id {
                    var graph = rows[rowIndex]["graph"] as! [String: Any]
                    graph["highlighted"] = node.isEmpty ? [] : [node]
                    rows[rowIndex]["graph"] = graph
                    rows[rowIndex]["value"] = node
                }
                sections[index]["rows"] = rows
            }
            next["sections"] = sections
        }
        if id == "reset_key" {
            self.lastDraft = ""
            var sections = next["sections"] as! [[String: Any]]
            var rows = sections[0]["rows"] as! [[String: Any]]
            rows[0]["id"] = "replacement_key"
            rows[0]["value"] = ""
            sections[0]["rows"] = rows
            next["sections"] = sections
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
        if ProcessInfo.processInfo.arguments.contains("navigation") {
            surfaceRaw["sections"] = []
            surfaceRaw["toolbar"] = []
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["navigation"] = ["id": "main_destination", "title": "", "kind": "segmented", "subtitle": "",
                "value": "home", "enabled": true, "destructive": false,
                "options": ["home", "tasks", "memories", "apps", "settings"].map { ["id": $0, "title": $0.capitalized] }]
        }
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
        if ProcessInfo.processInfo.arguments.contains("secure-input") {
            surfaceRaw["title"] = "Transcription"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "credential", "title": "", "footer": "", "rows": [
                ["id": "draft", "title": "API key", "kind": "text", "keyboard": "password", "subtitle": "",
                 "value": "", "options": [], "enabled": true, "destructive": false],
                ["id": "reset_key", "title": "Clear key", "kind": "button", "subtitle": "",
                 "options": [], "enabled": true, "destructive": false]
            ]]]
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
        if ProcessInfo.processInfo.arguments.contains("rows") {
            func row(_ id: String, _ title: String, _ kind: String, symbol: String? = nil, destructive: Bool = false,
                     value: Any? = nil, options: [String] = []) -> [String: Any] {
                var result: [String: Any] = ["id": id, "title": title, "kind": kind, "subtitle": "", "enabled": true,
                    "destructive": destructive, "options": options.map { ["id": $0, "title": $0.capitalized] }]
                if let symbol { result["symbol"] = symbol }
                if let value { result["value"] = value }
                return result
            }
            surfaceRaw["title"] = "Device"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [
                ["id": "status", "title": "Status", "footer": "", "rows": [
                    row("label_plain", "Firmware 3.0.1", "label"),
                    row("label_symbol", "Bluetooth connected", "label", symbol: "antenna.radiowaves.left.and.right"),
                    row("label_warning", "Pairing lost", "label", symbol: "exclamationmark.triangle", destructive: true),
                ]],
                ["id": "tasks", "title": "Tasks", "footer": "", "rows": [
                    row("task_static", "Water the plants", "task", value: false, options: ["delete"]),
                    row("task_open", "Review the native screens", "task", value: false, options: ["open", "delete"]),
                ]],
            ]
        }
        addListInteractionFixtures()
        if ProcessInfo.processInfo.arguments.contains("level") {
            surfaceRaw["title"] = "Device"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "device", "title": "Light", "footer": "", "rows": [
                ["id": "led_brightness", "title": "LED Brightness", "kind": "level", "subtitle": "50%", "value": 50.0,
                 "maximumValue": 100.0, "step": 25.0, "options": [], "enabled": true, "destructive": false]
            ]]]
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
        if ProcessInfo.processInfo.arguments.contains("secret") {
            // A synthetic one-time key; its narrow letters make a proportional font measurably shorter.
            surfaceRaw["title"] = "Key Created"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sensitive"] = true
            surfaceRaw["toolbar"] = [["id": "secret_done", "title": "Done", "kind": "button", "symbol": "checkmark",
                "subtitle": "", "options": [], "enabled": true, "destructive": false]]
            surfaceRaw["sections"] = [["id": "secret", "title": "", "footer": "", "rows": [
                ["id": "secret_message", "title": "Your new key", "kind": "label", "subtitle": "", "options": [],
                 "enabled": false, "destructive": false],
                ["id": "secret_warning", "title": "Copy it now. You will not see it again.", "kind": "label",
                 "symbol": "exclamationmark.triangle", "subtitle": "", "options": [], "enabled": false, "destructive": false],
                ["id": "secret_value", "title": "API Key", "kind": "secret", "subtitle": "", "value": "omi_dev_iiiiiiiiiiiiiiii",
                 "options": [["id": "copy", "title": "Copy"]], "enabled": true, "destructive": false],
            ]]]
        }
        if ["graph-fill", "graph-card", "graph-placeholder"].contains(where: ProcessInfo.processInfo.arguments.contains) {
            func row(_ id: String, _ title: String, _ kind: String) -> [String: Any] {
                ["id": id, "title": title, "kind": kind, "subtitle": "", "options": [], "enabled": true, "destructive": false]
            }
            func node(_ id: String, _ label: String, _ type: String, _ x: Double, _ y: Double, _ z: Double) -> [String: Any] {
                ["id": id, "label": label, "type": type, "x": x, "y": y, "z": z, "fixed": id == "me"]
            }
            let nodes = [node("me", "You", "user", 0, 0, 0), node("ada", "Ada", "person", -110, -150, 0),
                         node("paris", "Paris", "place", 120, -120, 300), node("omi", "Omi", "organization", 130, 140, -400),
                         node("pendant", "Pendant", "thing", -120, 150, 200), node("memory", "Memory", "concept", 0, -230, -600)]
            let edges: [[String: Any]] = [["me", "ada", "knows"], ["me", "paris", "visited"], ["me", "omi", "works at"],
                                          ["ada", "paris", ""], ["omi", "pendant", "makes"], ["me", "pendant", "wears"],
                                          ["me", "memory", ""]].map { ["source": $0[0], "target": $0[1], "label": $0[2]] }
            surfaceRaw["searchEnabled"] = false
            var back = row("graph_back", "Back", "button"); back["symbol"] = "chevron.left"
            var share = row("graph_share", "Share", "button"); share["symbol"] = "square.and.arrow.up"
            surfaceRaw["toolbar"] = [back, share]
            if ProcessInfo.processInfo.arguments.contains("graph-card") {
                surfaceRaw["title"] = "Memories"
                var card = row("graph_card", "Memory Graph", "graph")
                card["graph"] = ["nodes": nodes, "edges": edges, "highlighted": [], "zoom": 0.6, "interactive": false,
                                 "layout": "card", "height": 140.0, "placeholder": false, "accent": "#FFFFFF"]
                surfaceRaw["sections"] = [["id": "mind_map", "title": "", "footer": "", "rows": [card]],
                    ["id": "memories", "title": "Memories", "footer": "", "rows": (0..<30).map { index -> [String: Any] in
                        row("memory_\(index)", "Memory \(index): the pendant syncs overnight", "navigation")
                    }]]
            } else {
                surfaceRaw["title"] = "Memory Graph"
                var canvas = row("graph_canvas", "Memory Graph", "graph")
                if ProcessInfo.processInfo.arguments.contains("graph-placeholder") {
                    surfaceRaw["loading"] = true
                    surfaceRaw["loadingLabel"] = "Loading knowledge graph"
                    canvas["graph"] = ["nodes": [], "edges": [], "highlighted": [], "zoom": 1.0, "interactive": false,
                                       "layout": "fill", "placeholder": true, "accent": "#FFFFFF"]
                } else {
                    canvas["value"] = ""
                    canvas["graph"] = ["nodes": nodes, "edges": edges, "highlighted": [], "zoom": 1.0, "interactive": true,
                                       "layout": "fill", "placeholder": false, "accent": "#FFFFFF"]
                }
                surfaceRaw["sections"] = [["id": "graph", "title": "", "footer": "", "rows": [
                    row("graph_hint", "Tap a node to see what connects to it.", "label"), canvas,
                    row("graph_continue", "Continue", "button"),
                ]]]
            }
        }
        if ProcessInfo.processInfo.arguments.contains("light") { raw["appearance"] = "light" }
        else { raw["appearance"] = "dark" }
        if ProcessInfo.processInfo.arguments.contains("error") || ProcessInfo.processInfo.arguments.contains("empty") {
            raw["groups"] = []
            raw["localRecordingCount"] = 0
            raw["hasMore"] = false
            raw["failed"] = ProcessInfo.processInfo.arguments.contains("error")
        }
        if ProcessInfo.processInfo.arguments.contains("chat-rich") {
            func block(_ kind: String, _ text: String, prefix: String = "", indent: Int = 0) -> [String: Any] {
                ["kind": kind, "text": text, "indent": indent, "prefix": prefix]
            }
            var heading = block("heading", "Launch plan"); heading["level"] = 2
            var table = block("table", ""); table["cells"] = [["Owner", "Status"], ["Dart", "Opens links"]]
            let blocks: [[String: Any]] = [heading,
                block("text", "Read the [allowed guide](https://omi.me/allowed) or [another site](https://example.com/blocked)."),
                block("text", "Ship the **native** body", prefix: "1."), block("text", "Keep the owner", prefix: "•", indent: 1),
                block("quote", "Links stay with Dart"), block("code", "let owner = \"Dart\""), table]
            // Like the chat page, each reply has an action and an "Open" subtitle; only a symbol adds a button.
            func message(_ id: String, _ blocks: [[String: Any]], subtitle: String, symbol: String? = nil) -> [String: Any] {
                var row: [String: Any] = ["id": id, "title": "Launch plan", "kind": "message_ai", "subtitle": subtitle, "blocks": blocks,
                    "options": [["id": "https://omi.me/allowed", "title": "https://omi.me/allowed"]], "enabled": true, "destructive": false]
                if let symbol { row["symbol"] = symbol }
                return row
            }
            surfaceRaw["sections"] = [["id": "messages", "title": "", "footer": "", "rows": [
                ["id": "chat_rich_user", "title": "Plan the **launch**", "kind": "message_user", "plainText": true, "subtitle": "", "options": [], "enabled": false, "destructive": false],
                message("chat_rich_ai", blocks, subtitle: "Open"),
                message("chat_rich_retry", [block("text", "The reply could not finish.")], subtitle: "Try again", symbol: "arrow.clockwise"),
                // A reader row without a whitelist: its link is discarded rather than opened by the system.
                ["id": "chat_rich_note", "title": "Note", "kind": "rich_text", "subtitle": "", "options": [], "enabled": false, "destructive": false,
                 "blocks": [block("text", "See the [unlisted note](https://example.com/note).")]]]]]
        }
        for style in ["bar", "line"] where ProcessInfo.processInfo.arguments.contains("chart-\(style)") {
            // Labels at the 64-character limit, a single category and the unchanged quantitative chart.
            let long = "Planning review with the native migration team, morning slots"
            func chart(_ id: String, _ title: String, _ count: Int, style: String?, subtitle: String = "Day") -> [String: Any] {
                let points: [[String: Any]] = (0..<count).map { index in
                    ["x": Double(index), "y": Double((index * 7) % 11 + 1), "label": "\(long) \(String(format: "%02d", index))"]
                }
                var row: [String: Any] = ["id": id, "title": title, "kind": "chart", "subtitle": subtitle, "options": [], "enabled": false, "destructive": false,
                    "points": points]
                if let style { row["chartStyle"] = style }
                return row
            }
            surfaceRaw["title"] = "Charts"
            surfaceRaw["searchEnabled"] = false
            surfaceRaw["sections"] = [["id": "charts", "title": "", "footer": "", "rows": [
                chart("chart_many", "Messages per day", 14, style: style), chart("chart_single", "Single day", 1, style: style),
                chart("chart_legacy", "Signal strength", 1, style: nil, subtitle: "Collecting data")]]]
        }
    }

    /// Selection with a bottom bar, reorder, collapsible sections, swipes and indent.
    private func addListInteractionFixtures() {
        let arguments = ProcessInfo.processInfo.arguments
        func row(_ id: String, _ title: String, _ kind: String, value: Any? = nil, options: [(String, String)] = [],
                 symbol: String? = nil, destructive: Bool = false) -> [String: Any] {
            var result: [String: Any] = ["id": id, "title": title, "kind": kind, "subtitle": "", "enabled": true,
                "destructive": destructive, "options": options.map { ["id": $0.0, "title": $0.1] }]
            if let value { result["value"] = value }
            if let symbol { result["symbol"] = symbol }
            return result
        }
        guard ["selection", "reorder", "collapsible", "swipe", "indent"].contains(where: arguments.contains) else { return }
        surfaceRaw["searchEnabled"] = false
        surfaceRaw["toolbar"] = []
        surfaceRaw["expandLabel"] = "Expand"
        surfaceRaw["collapseLabel"] = "Collapse"
        if arguments.contains("selection") {
            surfaceRaw["title"] = "Conversations"
            surfaceRaw["toolbar"] = [row("selection_cancel", "Cancel", "button", symbol: "xmark")]
            func conversation(_ id: String, _ title: String) -> [String: Any] {
                var result = row(id, title, "navigation", options: [("open", "Open"), ("delete", "Delete")])
                result["swipeTrailing"] = ["delete"]
                return result
            }
            surfaceRaw["sections"] = [["id": "today", "title": "Today", "footer": "", "rows": [
                conversation("conv_1", "Design review"), conversation("conv_2", "Product sync"),
                conversation("conv_3", "Weekly planning"), conversation("conv_locked", "Merging call"),
                row("more", "Show more", "button"),
            ]]]
            surfaceRaw["selection"] = ["selected": ["conv_1"], "selectable": ["conv_1", "conv_2", "conv_3"]]
            surfaceRaw["bottomBar"] = [row("selection_count", "1 selected", "label"),
                row("bulk_move", "Move to Folder", "button", symbol: "folder"),
                row("bulk_delete", "Delete", "button", symbol: "trash", destructive: true)]
        }
        if arguments.contains("reorder") {
            surfaceRaw["title"] = "Tasks"
            surfaceRaw["toolbar"] = [row("reorder_done", "Done", "button", symbol: "checkmark")]
            surfaceRaw["sections"] = [["id": "tasks", "title": "Today", "footer": "", "reorderable": true, "rows": [
                row("task_a", "Buy oat milk", "task", value: false), row("task_b", "Call Avery", "task", value: false),
                row("task_c", "Ship the release", "task", value: false),
            ]]]
        }
        if arguments.contains("collapsible") {
            surfaceRaw["title"] = "Tasks"
            surfaceRaw["sections"] = [
                ["id": "overdue", "title": "Overdue", "footer": "2 tasks", "collapsible": true, "rows": [
                    row("late_1", "Renew passport", "label"), row("late_2", "Pay the invoice", "label")]],
                ["id": "today", "title": "Today", "footer": "", "rows": [row("today_1", "Stand-up notes", "label")]],
            ]
        }
        if arguments.contains("swipe") {
            surfaceRaw["title"] = "Tasks"
            var task = row("swipe_task", "Water the plants", "task", value: false,
                           options: [("complete", "Complete"), ("open", "Open"), ("delete", "Delete")])
            task["swipeLeading"] = ["complete"]
            task["swipeTrailing"] = ["delete"]
            var person = row("swipe_person", "Avery", "navigation", options: [("pin", "Pin"), ("rename", "Rename")])
            person["swipeTrailing"] = ["pin", "rename"]
            surfaceRaw["sections"] = [["id": "swipes", "title": "Today", "footer": "", "rows": [task, person]]]
        }
        if arguments.contains("indent") {
            surfaceRaw["title"] = "Tasks"
            var rows = [row("indent_0", "Plan the launch", "label"), row("indent_1", "Draft the post", "label"),
                        row("indent_2", "Pick a title", "label")]
            for index in rows.indices { rows[index]["indent"] = index }
            surfaceRaw["sections"] = [["id": "outline", "title": "Outline", "footer": "", "rows": rows]]
        }
    }
}
