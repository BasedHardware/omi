import Foundation

@main
struct NativeSurfaceTests {
    static func main() throws {
        let row: [String: Any] = ["id": "appearance", "title": "Appearance", "kind": "choice", "subtitle": "",
            "value": "system", "options": [["id": "system", "title": "System"]], "destructive": false, "enabled": true]
        var input: [String: Any] = ["version": 1, "revision": 0, "title": "Settings", "appearance": "system",
            "locale": "en", "direction": "ltr", "loading": false, "failed": false, "empty": "",
            "sections": [["id": "settings", "title": "", "footer": "", "rows": [row]]], "toolbar": [],
            "searchEnabled": true, "searchValue": "private search", "searchPlaceholder": "Search", "refreshEnabled": false,
            "error": "Error", "retry": "Retry", "loadingLabel": "Loading"]
        let snapshot = try NativeSurfaceSnapshot.decode(input)
        var tabs = input
        tabs["sections"] = []
        tabs["searchEnabled"] = false
        var destinations: [String: Any] = ["id": "main_destination", "title": "", "kind": "segmented", "subtitle": "",
            "value": "home", "enabled": true, "destructive": false,
            "options": ["home", "tasks", "memories", "apps", "settings"].map { ["id": $0, "title": $0.capitalized] }]
        tabs["navigation"] = destinations
        let bar = try NativeSurfaceSnapshot.decode(tabs)
        precondition(bar.replacingValue(id: "main_destination", value: .text("settings")).navigation?.value?.text == "settings")
        precondition(bar.withoutContent().navigation == nil && bar.withoutContent().allRows.isEmpty)
        destinations["value"] = "arbitrary_route"
        tabs["navigation"] = destinations
        rejects(tabs)
        destinations["value"] = "home"
        destinations["options"] = [["id": "home", "title": "Home"]]
        tabs["navigation"] = destinations
        rejects(tabs)
        var keypad: [String: Any] = ["id": "keys", "title": "Keypad", "kind": "keypad", "subtitle": "",
            "value": "123", "keypadMode": "dtmf", "options": "0123456789*#".map { ["id": String($0), "title": ""] },
            "destructive": false, "enabled": true]
        var dialer = input
        dialer["sections"] = [["id": "keys", "title": "", "footer": "", "rows": [keypad]]]
        let keys = try NativeSurfaceSnapshot.decode(dialer)
        precondition(keys.replacingValue(id: "keys", value: .text("1234")).sections[0].rows[0].keypadMode == "dtmf")
        keypad["keypadMode"] = "dialer"
        dialer["sections"] = [["id": "keys", "title": "", "footer": "", "rows": [keypad]]]
        rejects(dialer)
        keypad["eraseLabel"] = "Delete"
        keypad["clearLabel"] = "Clear All"
        dialer["sections"] = [["id": "keys", "title": "", "footer": "", "rows": [keypad]]]
        _ = try NativeSurfaceSnapshot.decode(dialer)
        keypad["options"] = [["id": "1", "title": ""]]
        dialer["sections"] = [["id": "keys", "title": "", "footer": "", "rows": [keypad]]]
        rejects(dialer)
        var literal = row
        literal["kind"] = "message_ai"
        literal.removeValue(forKey: "value")
        literal["plainText"] = true
        dialer["sections"] = [["id": "literal", "title": "", "footer": "", "rows": [literal]]]
        _ = try NativeSurfaceSnapshot.decode(dialer)
        literal["kind"] = "button"
        dialer["sections"] = [["id": "literal", "title": "", "footer": "", "rows": [literal]]]
        rejects(dialer)
        precondition(snapshot.sections[0].rows[0].value?.text == "system")
        precondition(snapshot.largeTitle == nil)
        var searchable = row
        searchable["optionSearch"] = "Search countries"
        searchable["optionClose"] = "Close"
        var countries = input
        countries["sections"] = [["id": "country", "title": "", "footer": "", "rows": [searchable]]]
        let country = try NativeSurfaceSnapshot.decode(countries)
        precondition(country.replacingValue(id: "appearance", value: .text("system")).sections[0].rows[0].optionSearch == "Search countries")
        searchable.removeValue(forKey: "optionClose")
        countries["sections"] = [["id": "country", "title": "", "footer": "", "rows": [searchable]]]
        rejects(countries)
        var color = row
        color["kind"] = "color"
        color["value"] = "#3B82F6"
        color["options"] = [["id": "#3B82F6", "title": "Color 1"]]
        var palette = input
        palette["sections"] = [["id": "palette", "title": "", "footer": "", "rows": [color]]]
        _ = try NativeSurfaceSnapshot.decode(palette)
        color["options"] = [["id": "invalid", "title": "Color"]]
        palette["sections"] = [["id": "palette", "title": "", "footer": "", "rows": [color]]]
        rejects(palette)
        var meter = row
        meter["level"] = 4
        palette["sections"] = [["id": "meter", "title": "", "footer": "", "rows": [meter]]]
        rejects(palette)
        meter["level"] = 2
        meter["visibilityEnabled"] = true
        palette["sections"] = [["id": "meter", "title": "", "footer": "", "rows": [meter]]]
        let levels = try NativeSurfaceSnapshot.decode(palette)
        let revised = levels.replacingValue(id: "appearance", value: .text("system"))
        precondition(revised.revision == 1 && revised.sections[0].rows[0].level == 2)
        precondition(revised.sections[0].rows[0].visibilityEnabled == true)
        var navigation = row
        navigation["kind"] = "navigation"
        navigation.removeValue(forKey: "value")
        var settings = input
        settings["largeTitle"] = true
        settings["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [navigation]]]
        let nativeSettings = try NativeSurfaceSnapshot.decode(settings)
        precondition(nativeSettings.largeTitle == true)
        navigation["value"] = "arbitrary mutation"
        settings["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [navigation]]]
        rejects(settings)
        var playback = input
        let line: [String: Any] = ["id": "segment:1", "title": "Words", "kind": "transcript", "subtitle": "Speaker 1", "options": [], "enabled": true, "destructive": false]
        var slider: [String: Any] = ["id": "position", "title": "Audio", "kind": "slider", "subtitle": "", "value": 25.5, "maximumValue": 100, "options": [], "enabled": true, "destructive": false]
        playback["sections"] = [["id": "transcript", "title": "", "footer": "", "rows": [line]]]
        playback["reader"] = ["currentId": "segment:1", "targetId": "segment:1", "request": 1, "following": true, "footer": [slider]]
        let reader = try NativeSurfaceSnapshot.decode(playback)
        precondition(reader.reader?.footer.first?.value?.number == 25.5)
        precondition(reader.replacingValue(id: "position", value: .number(40)).reader?.footer.first?.value?.number == 40)
        precondition(reader.withoutContent().reader == nil)
        for value in [-1.0, 101.0] {
            slider["value"] = value
            playback["reader"] = ["request": 0, "following": false, "footer": [slider]]
            rejects(playback)
        }
        playback["reader"] = ["targetId": "foreign", "request": 0, "following": false, "footer": []]
        rejects(playback)
        var date = row; date["kind"] = "date"; date["value"] = true
        playback.removeValue(forKey: "reader")
        playback["sections"] = [["id": "date", "title": "", "footer": "", "rows": [date]]]
        rejects(playback)
        date["value"] = 10
        playback["sections"] = [["id": "date", "title": "", "footer": "", "rows": [date]]]
        rejects(playback)
        let cleared = snapshot.withoutContent()
        precondition(cleared.sections.isEmpty && cleared.toolbar.isEmpty && cleared.searchValue.isEmpty && cleared.title.isEmpty)
        var invalid = row
        for value: Any in [true, "missing"] {
            invalid["value"] = value
            input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [invalid]]]
            rejects(input)
        }
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [row, row]]]
        rejects(input)
        invalid = row
        invalid["id"] = "_refresh"
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [invalid]]]
        rejects(input)
        invalid = row
        invalid["kind"] = "date"
        invalid["value"] = "nan"
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [invalid]]]
        rejects(input)
        invalid["kind"] = "chart"
        invalid.removeValue(forKey: "value")
        invalid["points"] = [["x": 1, "y": 50, "label": "50%"], ["x": 1, "y": 60, "label": "60%"]]
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [invalid]]]
        rejects(input)
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [row]]]
        input["chat"] = ["draft": "private message", "placeholder": "Ask Omi", "followup": "", "streaming": false, "actions": []]
        let chatSnapshot = try NativeSurfaceSnapshot.decode(input)
        precondition(chatSnapshot.withoutContent().chat == nil)
        var text = row
        text["kind"] = "text"
        text["keyboard"] = "phone"
        text["value"] = ""
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [text]]]
        let phone = try NativeSurfaceSnapshot.decode(input)
        precondition(phone.sections[0].rows[0].keyboard == "phone")
        text["keyboard"] = "unknown"
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [text]]]
        rejects(input)
        text.removeValue(forKey: "keyboard")
        text["maximumLength"] = 2
        text["value"] = "👨‍👩‍👧‍👦a"
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [text]]]
        _ = try NativeSurfaceSnapshot.decode(input)
        text["value"] = "👨‍👩‍👧‍👦ab"
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [text]]]
        rejects(input)
        text["value"] = ""
        text["maximumLength"] = 0
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [text]]]
        rejects(input)
        var image = row
        for uri in ["https://example.com/a.jpg", "file:///sandbox/a.jpg"] {
            image["imageUri"] = uri
            input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [image]]]
            _ = try NativeSurfaceSnapshot.decode(input)
        }
        for uri in ["http://example.com/a", "file://other-host/a", "https://user:password@example.com/a", "javascript:alert(1)"] {
            image["imageUri"] = uri
            input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [image]]]
            rejects(input)
        }
        var wave = row
        wave["kind"] = "waveform"
        wave.removeValue(forKey: "value")
        wave["points"] = [["x": 0, "y": 0.5, "label": ""]]
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [wave]]]
        _ = try NativeSurfaceSnapshot.decode(input)
        wave["points"] = [["x": 0, "y": 2, "label": ""]]
        input["sections"] = [["id": "settings", "title": "", "footer": "", "rows": [wave]]]
        rejects(input)
        try activityRequests()
        try toastRequests()
        try secrets()
        try listInteractions()
        try richMessagesAndCategoricalCharts(input)
        print("Native surface contract: typed values, command IDs, uniqueness and invalidation passed")
    }

    static func toastRequests() throws {
        let undo: [String: Any] = ["requestId": 3, "session": "process-a", "kind": "undo", "message": "Task deleted",
            "actionLabel": "Undo", "durationMs": 5000, "symbol": "trash", "bottomClearance": 128.0,
            "appearance": "dark", "locale": "en", "direction": "ltr"]
        let request = try NativeToastRequest.decode(undo)
        precondition(request.kind == "undo" && request.actionLabel == "Undo" && request.closeLabel == nil)
        var error = undo
        error["kind"] = "error"; error["durationMs"] = 8000; error["symbol"] = "exclamationmark.circle.fill"
        error["closeLabel"] = "Close"
        _ = try NativeToastRequest.decode(error)
        error.removeValue(forKey: "actionLabel")
        _ = try NativeToastRequest.decode(error)
        error.removeValue(forKey: "closeLabel")
        rejectsToast(error)
        var progress = undo
        progress["kind"] = "progress"; progress["durationMs"] = 60000; progress["symbol"] = "progress"
        progress.removeValue(forKey: "actionLabel")
        _ = try NativeToastRequest.decode(progress)
        progress["symbol"] = "info.circle"
        rejectsToast(progress)
        for (kind, duration, symbol) in [("confirm", 1500, "checkmark.circle.fill"), ("info", 4000, "info.circle"),
                                         ("progress", 60000, "progress")] {
            var plain = undo
            plain["kind"] = kind; plain["durationMs"] = duration; plain["symbol"] = symbol
            plain.removeValue(forKey: "actionLabel")
            _ = try NativeToastRequest.decode(plain)
            plain["actionLabel"] = "Undo"
            rejectsToast(plain)
            plain.removeValue(forKey: "actionLabel")
            plain["durationMs"] = duration == 1500 ? 4000 : 1500
            rejectsToast(plain)
        }
        var invalid = undo
        invalid["kind"] = "celebrate"
        rejectsToast(invalid)
        invalid = undo
        invalid["durationMs"] = 4000
        rejectsToast(invalid)
        invalid = undo
        invalid.removeValue(forKey: "actionLabel")
        rejectsToast(invalid)
        invalid = undo
        invalid["closeLabel"] = "Close"
        rejectsToast(invalid)
        invalid = undo
        invalid["actionLabel"] = String(repeating: "a", count: 41)
        rejectsToast(invalid)
        for clearance in [Double.nan, .infinity, -1, 240.5] {
            invalid = undo
            invalid["bottomClearance"] = clearance
            rejectsToast(invalid)
        }
        for message in ["", String(repeating: "👨‍👩‍👧‍👦", count: 1001), "a\u{0}b"] {
            invalid = undo
            invalid["message"] = message
            rejectsToast(invalid)
        }
        invalid = undo
        invalid["message"] = String(repeating: "👨‍👩‍👧‍👦", count: 1000)
        _ = try NativeToastRequest.decode(invalid)
        for (key, value) in [("symbol", "star"), ("appearance", "sepia"), ("direction", "up"), ("locale", ""),
                             ("session", "")] {
            invalid = undo
            invalid[key] = value
            rejectsToast(invalid)
        }
        invalid = undo
        invalid["requestId"] = -1
        rejectsToast(invalid)
        func toast(_ id: Int, _ session: String) throws -> NativeToastRequest {
            var input = undo
            input["requestId"] = id; input["session"] = session
            return try NativeToastRequest.decode(input)
        }
        var order = NativeToastOrder()
        // A restarted engine (process-b) starts a new sequence instead of being refused for good.
        let sequence: [(NativeToastRequest, Bool)] = try [
            (toast(5, "process-a"), true), (toast(5, "process-a"), false), (toast(4, "process-a"), false),
            (toast(6, "process-a"), true), (toast(0, "process-b"), true), (toast(0, "process-b"), false),
            (toast(1, "process-b"), true),
        ]
        for (index, (request, accepted)) in sequence.enumerated() {
            let result = order.accept(request)
            precondition(result == accepted, "Toast order step \(index)")
        }
    }

    static func rejectsToast(_ input: Any) {
        do { _ = try NativeToastRequest.decode(input) }
        catch { return }
        preconditionFailure("Invalid native toast accepted")
    }
    /// The activity overlay accepts exactly the request Dart validates: a label of 1...200 characters.
    static func activityRequests() throws {
        let request: [String: Any] = ["requestId": 3, "label": "Saving", "appearance": "system",
            "locale": "en", "direction": "rtl"]
        let decoded = try NativeActivityRequest.decode(request)
        precondition(decoded == NativeActivityRequest(id: 3, label: "Saving", appearance: "system", locale: "en", direction: "rtl"))
        var longest = request
        longest["label"] = String(repeating: "👨‍👩‍👧‍👦", count: 200)
        _ = try NativeActivityRequest.decode(longest)
        let invalid: [(String, Any)] = [("requestId", -1), ("requestId", "3"), ("label", ""),
            ("label", String(repeating: "a", count: 201)), ("label", 7), ("appearance", "sepia"),
            ("locale", ""), ("direction", "up")]
        for (key, value) in invalid {
            var refused = request
            refused[key] = value
            rejectsActivity(refused)
            refused.removeValue(forKey: key)
            rejectsActivity(refused)
        }
        rejectsActivity(nil)
        rejectsActivity("Saving")
    }
    static func rejectsActivity(_ input: Any?) {
        do { _ = try NativeActivityRequest.decode(input) }
        catch { return }
        preconditionFailure("Invalid native activity accepted")
    }
    /// A one-time secret: printable ASCII, one 'copy' command, one section row of a sensitive snapshot.
    static func secrets() throws {
        let key = "omi_dev_0123456789abcdef"
        let secret: [String: Any] = ["id": "secret_value", "title": "API Key", "kind": "secret", "subtitle": "",
            "value": key, "options": [["id": "copy", "title": "Copy"]], "destructive": false, "enabled": true]
        let done: [String: Any] = ["id": "secret_done", "title": "Done", "kind": "button", "symbol": "checkmark",
            "subtitle": "", "options": [], "destructive": false, "enabled": true]
        let base: [String: Any] = ["version": 1, "revision": 0, "title": "Key Created", "appearance": "system",
            "locale": "en", "direction": "ltr", "loading": false, "failed": false, "empty": "",
            "toolbar": [done], "searchEnabled": false, "searchValue": "", "searchPlaceholder": "",
            "refreshEnabled": false, "error": "Error", "retry": "Retry", "loadingLabel": "Loading", "sensitive": true]
        func reveal(_ rows: [[String: Any]], _ change: (inout [String: Any]) -> Void = { _ in }) -> [String: Any] {
            var snapshot = base
            snapshot["sections"] = [["id": "secret", "title": "", "footer": "", "rows": rows]]
            change(&snapshot)
            return snapshot
        }
        func with(_ field: String, _ value: Any) -> [String: Any] {
            var row = secret
            row[field] = value
            return row
        }
        let accepted = try NativeSurfaceSnapshot.decode(reveal([secret]))
        precondition(accepted.sensitive == true && accepted.sections[0].rows[0].value?.text == key)
        precondition(accepted.replacingValue(id: "secret_done", value: .text("")).sensitive == true)
        let cleared = accepted.withoutContent()
        precondition(cleared.sensitive == false && cleared.allRows.isEmpty)
        _ = try NativeSurfaceSnapshot.decode(reveal([with("value", String(repeating: "~", count: 4096))]))
        rejects(reveal([secret]) { $0["sensitive"] = false })
        rejects(reveal([secret]) { $0.removeValue(forKey: "sensitive") })
        for value in ["", String(repeating: "a", count: 4097), "omi\nkey", "omi key", "omi\tkey", "omi\u{7F}key", "omi_kéy", "omi_🔑"] {
            rejects(reveal([with("value", value)]))
        }
        rejects(reveal([with("value", true)]))
        rejects(reveal([with("options", [["id": "reveal", "title": "Reveal"]])]))
        rejects(reveal([with("options", [["id": "copy", "title": "Copy"], ["id": "share", "title": "Share"]])]))
        rejects(reveal([with("options", [["id": "copy", "title": ""]])]))
        rejects(reveal([with("imageUri", "https://example.com/key.png")]))
        rejects(reveal([]) { $0["toolbar"] = [done, secret] })
        rejects(reveal([secret, with("id", "secret_again")]))
        rejects(reveal([secret]) {
            $0["chat"] = ["draft": "", "placeholder": "Ask Omi", "followup": "", "streaming": false, "actions": []]
        })
        // A sensitive snapshot is never a selection, and a secret never sits in the bottom bar.
        rejects(reveal([secret]) { $0["selection"] = ["selected": [], "selectable": ["secret_value"]] })
        rejects(reveal([]) { $0["bottomBar"] = [secret] })
    }

    /// Selection, bottom bar, reorderable and collapsible sections, indent and swipes mirror Dart.
    static func listInteractions() throws {
        func row(_ id: String, _ kind: String = "label", value: Any? = nil, options: [String] = []) -> [String: Any] {
            var result: [String: Any] = ["id": id, "title": id, "kind": kind, "subtitle": "", "destructive": false,
                "enabled": true, "options": options.map { ["id": $0, "title": $0] }]
            if let value { result["value"] = value }
            return result
        }
        func surface(_ rows: [[String: Any]], section: [String: Any] = [:], extra: [String: Any] = [:]) -> [String: Any] {
            var input: [String: Any] = ["version": 1, "revision": 0, "title": "Library", "appearance": "system",
                "locale": "en", "direction": "ltr", "loading": false, "failed": false, "empty": "",
                "sections": [["id": "today", "title": "Today", "footer": "", "rows": rows].merging(section) { $1 }],
                "toolbar": [], "searchEnabled": false, "searchValue": "", "searchPlaceholder": "", "refreshEnabled": false,
                "error": "Error", "retry": "Retry", "loadingLabel": "Loading", "expandLabel": "Expand", "collapseLabel": "Collapse"]
            input.merge(extra) { $1 }
            return input
        }
        let conversations = [row("a", "navigation"), row("b", "navigation"), row("more", "button")]
        let bar = [row("count"), row("bulk_delete", "button"), row("bulk_more", "menu", options: ["move"])]
        let selection: [String: Any] = ["selected": ["a"], "selectable": ["a", "b"]]
        let selecting = try NativeSurfaceSnapshot.decode(surface(conversations, extra: ["selection": selection, "bottomBar": bar]))
        precondition(selecting.selection?.selectable == ["a", "b"] && selecting.expandLabel == "Expand")
        precondition(selecting.allRows.map(\.id).suffix(3) == ["count", "bulk_delete", "bulk_more"])
        let replaced = selecting.replacingValue(id: "a", value: .text("unused"))
        precondition(replaced.selection == selecting.selection && replaced.bottomBar == selecting.bottomBar)
        precondition(replaced.collapseLabel == "Collapse")
        let cleared = selecting.withoutContent()
        precondition(cleared.selection == nil && cleared.bottomBar == nil && cleared.expandLabel == nil && cleared.allRows.isEmpty)
        precondition(selecting.offersListCommand("_selection") && !selecting.offersListCommand("_reorder:today"))
        for invalid: [String: Any] in [["selected": [], "selectable": ["a", "foreign"]], ["selected": ["more"], "selectable": ["a"]],
                                      ["selected": [], "selectable": ["a", "a"]], ["selected": ["a", "a"], "selectable": ["a"]]] {
            rejects(surface(conversations, extra: ["selection": invalid]))
        }
        let many = (0...10000).map { row("row_\($0)") }
        rejects(surface(many, extra: ["selection": ["selected": [], "selectable": many.map { $0["id"] as? String ?? "" }]]))
        _ = try NativeSurfaceSnapshot.decode(surface(many, extra: ["selection": ["selected": [],
            "selectable": many.dropFirst().map { $0["id"] as? String ?? "" }]]))
        let chat: [String: Any] = ["draft": "", "placeholder": "Ask", "followup": "", "streaming": false, "actions": []]
        let reader: [String: Any] = ["request": 0, "following": false, "footer": []]
        rejects(surface(conversations, extra: ["selection": selection, "chat": chat]))
        rejects(surface(conversations, extra: ["selection": selection, "reader": reader]))
        rejects(surface(conversations, section: ["reorderable": true], extra: ["selection": selection]))

        _ = try NativeSurfaceSnapshot.decode(surface(conversations, extra: ["bottomBar": [row("count")] + (1...5).map { row("action_\($0)", "button") }]))
        rejects(surface(conversations, extra: ["bottomBar": [row("count")] + (1...6).map { row("action_\($0)", "button") }]))
        rejects(surface(conversations, extra: ["bottomBar": [row("count"), row("other")]]))
        rejects(surface(conversations, extra: ["bottomBar": [row("switch", "toggle", value: false)]]))
        rejects(surface(conversations, extra: ["bottomBar": [row("a", "button")]]))
        rejects(surface(conversations, extra: ["bottomBar": [row("send", "button")], "chat": chat]))
        rejects(surface(conversations, extra: ["bottomBar": [row("play", "button")], "reader": reader]))
        var shell = surface([], extra: ["navigation": row("main_destination", "segmented", value: "home",
                                                          options: ["home", "tasks", "memories", "apps", "settings"])])
        shell["sections"] = []
        _ = try NativeSurfaceSnapshot.decode(shell)
        shell["bottomBar"] = [row("count")]
        rejects(shell)

        let tasks = ["x", "y", "z"].map { row($0, "task", value: false) }
        let ordered = try NativeSurfaceSnapshot.decode(surface(tasks, section: ["reorderable": true, "collapsible": true]))
        precondition(ordered.sections[0].reorderable == true && ordered.sections[0].collapsible == true)
        let toggled = ordered.replacingValue(id: "x", value: .bool(true)).sections[0]
        precondition(toggled.reorderable == true && toggled.collapsible == true && toggled.rows[0].value == .bool(true))
        precondition(ordered.offersListCommand("_reorder:today") && !ordered.offersListCommand("_reorder:later"))
        rejects(surface([row("choice", "choice", value: "a", options: ["a"])], section: ["reorderable": true]))
        rejects(surface(tasks, section: ["title": "", "collapsible": true]))
        _ = try NativeSurfaceSnapshot.decode(surface(tasks, section: ["title": "", "collapsible": false]))

        let listRows: [(String, Any?)] = [("task", false), ("navigation", nil), ("label", nil), ("toggle", false), ("menu", nil)]
        for (kind, value) in listRows {
            var indented = row("indented", kind, value: value)
            for level in [0, 3] {
                indented["indent"] = level
                let decoded = try NativeSurfaceSnapshot.decode(surface([indented]))
                precondition(decoded.replacingValue(id: "indented", value: .bool(true)).sections[0].rows[0].indent == level)
            }
            for level in [-1, 4] {
                indented["indent"] = level
                rejects(surface([indented]))
            }
        }
        var button = row("button", "button")
        button["indent"] = 1
        rejects(surface([button]))

        var swiped = row("person", "navigation", options: ["pin", "star", "open", "delete", "rename"])
        swiped["swipeLeading"] = ["pin", "star", "open"]
        swiped["swipeTrailing"] = ["delete"]
        let swipes = try NativeSurfaceSnapshot.decode(surface([swiped]))
        precondition(swipes.replacingValue(id: "person", value: .text("x")).sections[0].rows[0].swipeTrailing == ["delete"])
        for (leading, trailing) in [(["pin", "star", "open", "rename"], ["delete"]), (["pin"], ["pin"]),
                                    (["archive"], []), (["pin", "pin"], [])] {
            swiped["swipeLeading"] = leading
            swiped["swipeTrailing"] = trailing
            rejects(surface([swiped]))
        }
        var label = row("note", options: ["delete"])
        label["swipeTrailing"] = ["delete"]
        rejects(surface([label]))
    }

    /// Rich AI bodies share the reader's block rules; categorical charts are index-ordered and labelled.
    static func richMessagesAndCategoricalCharts(_ base: [String: Any]) throws {
        var input = base
        input.removeValue(forKey: "chat")
        func section(_ row: [String: Any]) -> [[String: Any]] { [["id": "rows", "title": "", "footer": "", "rows": [row]]] }
        func block(_ kind: String, _ text: String) -> [String: Any] { ["kind": kind, "text": text, "indent": 0, "prefix": ""] }
        var heading = block("heading", "Plan"); heading["level"] = 2
        var table = block("table", ""); table["cells"] = [["Owner", "State"], ["Dart", "Opens links"]]
        var message: [String: Any] = ["id": "reply", "title": "Plan", "kind": "message_ai", "subtitle": "",
            "options": [["id": "https://omi.me/docs", "title": "https://omi.me/docs"]], "enabled": true, "destructive": false,
            "blocks": [heading, block("text", "Read [docs](https://omi.me/docs)"), block("quote", "Quote"), block("code", "let x = 1"), table]]
        input["sections"] = section(message)
        let reply = try NativeSurfaceSnapshot.decode(input)
        precondition(reply.sections[0].rows[0].blocks?.count == 5 && reply.sections[0].rows[0].options.count == 1)
        message["plainText"] = true
        input["sections"] = section(message)
        rejects(input)
        message.removeValue(forKey: "plainText")
        message["blocks"] = Array(repeating: block("text", "Line"), count: 2000)
        input["sections"] = section(message)
        _ = try NativeSurfaceSnapshot.decode(input)
        message["blocks"] = Array(repeating: block("text", "Line"), count: 2001)
        input["sections"] = section(message)
        rejects(input)
        var reader = message
        reader["kind"] = "rich_text"
        input["sections"] = section(reader)
        _ = try NativeSurfaceSnapshot.decode(input)
        for kind in ["message_user", "label"] {
            message["kind"] = kind
            message["blocks"] = [block("text", "Line")]
            input["sections"] = section(message)
            rejects(input)
        }
        message["kind"] = "message_ai"
        message["blocks"] = [block("script", "alert(1)")]
        input["sections"] = section(message)
        rejects(input)

        func categories(_ count: Int, label: String = "Day") -> [[String: Any]] {
            (0..<count).map { ["x": $0, "y": Double($0) * 2, "label": "\(label) \($0)"] as [String: Any] }
        }
        var chart: [String: Any] = ["id": "chart", "title": "Messages", "kind": "chart", "subtitle": "Day",
            "options": [], "enabled": false, "destructive": false]
        for style in ["line", "bar"] {
            for count in [1, 12] {
                chart["chartStyle"] = style
                chart["points"] = categories(count)
                input["sections"] = section(chart)
                let decoded = try NativeSurfaceSnapshot.decode(input)
                precondition(decoded.sections[0].rows[0].chartStyle == style)
                precondition(decoded.replacingValue(id: "other", value: .text("")).sections[0].rows[0].chartStyle == style)
            }
        }
        chart["points"] = [["x": 0, "y": 1, "label": String(repeating: "👩‍👩‍👧", count: 64)]]
        input["sections"] = section(chart)
        _ = try NativeSurfaceSnapshot.decode(input)
        let invalidPoints: [[[String: Any]]] = [
            [],
            [["x": 1, "y": 1, "label": "Day 1"]],
            [["x": 1, "y": 1, "label": "Day 1"], ["x": 0, "y": 1, "label": "Day 0"]],
            [["x": 0, "y": 1, "label": "Day 0"], ["x": 2, "y": 1, "label": "Day 2"]],
            [["x": 0.5, "y": 1, "label": "Half"]],
            // SafeJSON already refuses a non-finite y before the chart rule sees it.
            [["x": 0, "y": Double.nan, "label": "Day 0"]],
            [["x": 0, "y": 1]],
            [["x": 0, "y": 1, "label": String(repeating: "a", count: 65)]],
            categories(10001),
        ]
        for points in invalidPoints {
            chart["points"] = points
            input["sections"] = section(chart)
            rejects(input)
        }
        chart["points"] = categories(10000)
        chart["chartStyle"] = "bar"
        input["sections"] = section(chart)
        _ = try NativeSurfaceSnapshot.decode(input)
        chart["points"] = categories(3)
        for style in ["pie", ""] {
            chart["chartStyle"] = style
            input["sections"] = section(chart)
            rejects(input)
        }
        for kind in ["waveform", "message_ai"] {
            var other = chart
            other["kind"] = kind
            other["chartStyle"] = "bar"
            other["points"] = [["x": 0, "y": 0.5, "label": "Day 0"]]
            input["sections"] = section(other)
            rejects(input)
        }
        var label: [String: Any] = ["id": "label", "title": "Label", "kind": "label", "subtitle": "", "options": [],
            "enabled": false, "destructive": false, "chartStyle": "bar", "points": categories(3)]
        input["sections"] = section(label)
        rejects(input)
        label.removeValue(forKey: "chartStyle")
        input["sections"] = section(label)
        _ = try NativeSurfaceSnapshot.decode(input)
        // Without a style the existing quantitative chart keeps its rules: gaps and long labels stay valid.
        chart.removeValue(forKey: "chartStyle")
        chart["points"] = [["x": 0, "y": 1, "label": "Mon"], ["x": 3, "y": 2, "label": String(repeating: "a", count: 65)]]
        input["sections"] = section(chart)
        let usage = try NativeSurfaceSnapshot.decode(input)
        precondition(usage.sections[0].rows[0].chartStyle == nil)
    }

    static func rejects(_ input: Any) {
        do { _ = try NativeSurfaceSnapshot.decode(input) }
        catch { return }
        preconditionFailure("Invalid native form accepted")
    }
}
