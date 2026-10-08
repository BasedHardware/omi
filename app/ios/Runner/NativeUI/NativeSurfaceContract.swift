import Foundation

struct NativeSurfaceRow: Decodable, Equatable, Identifiable {
    struct Option: Decodable, Equatable, Identifiable { let id: String; let title: String }
    let id: String
    let title: String
    let kind: String
    let subtitle: String
    let value: Value?
    let options: [Option]
    let destructive: Bool
    let enabled: Bool
    let symbol: String?
    let minimumDate: String?
    let maximumLength: Int?
    let keyboard: String?
    let optionSearch: String?
    let optionClose: String?
    let keypadMode: String?
    let eraseLabel: String?
    let clearLabel: String?
    let plainText: Bool?
    let imageUri: String?
    let level: Int?
    let maximumValue: Double?
    let visibilityEnabled: Bool?
    let visibilityHiddenEnabled: Bool?
    struct Point: Decodable, Equatable, Identifiable {
        let x: Double; let y: Double; let label: String
        var id: Double { x }
    }
    let points: [Point]?
    struct RichBlock: Decodable, Equatable {
        let kind: String; let text: String; let indent: Int; let prefix: String
        let level: Int?; let uri: String?; let cells: [[String]]?
        var valid: Bool {
            guard ["text", "heading", "quote", "code", "table", "image", "rule"].contains(kind),
                  (0...32).contains(indent) else { return false }
            if kind == "heading" && !(1...6).contains(level ?? 0) { return false }
            if kind == "table" && (cells == nil || cells?.contains(where: \.isEmpty) == true) { return false }
            if kind == "image" {
                guard let uri, uri.count <= 4096, let url = URL(string: uri), url.user == nil, url.password == nil,
                      (url.scheme == "https" && !(url.host ?? "").isEmpty) ||
                      (url.isFileURL && (url.host ?? "").isEmpty && url.path.hasPrefix("/")) else { return false }
            }
            return true
        }
    }
    let blocks: [RichBlock]?

    func replacingValue(_ value: Value?) -> Self {
        Self(id: id, title: title, kind: kind, subtitle: subtitle, value: value,
             options: options, destructive: destructive, enabled: enabled, symbol: symbol,
             minimumDate: minimumDate, maximumLength: maximumLength, keyboard: keyboard,
             optionSearch: optionSearch, optionClose: optionClose, keypadMode: keypadMode,
             eraseLabel: eraseLabel, clearLabel: clearLabel, plainText: plainText, imageUri: imageUri,
             level: level, maximumValue: maximumValue, visibilityEnabled: visibilityEnabled,
             visibilityHiddenEnabled: visibilityHiddenEnabled, points: points, blocks: blocks)
    }


    var hasValidValue: Bool {
        switch kind {
        case "image": return value == nil && URL(string: imageUri ?? "")?.isFileURL == true && (1...16).contains(maximumValue ?? 0)
        case "slider", "progress":
            guard case let .number(number) = value, let maximumValue else { return false }
            return number.isFinite && maximumValue.isFinite && maximumValue > 0 && (0...maximumValue).contains(number)
        case "keypad":
            guard case let .text(text) = value else { return false }
            return text.count <= 10000 && ["dialer", "dtmf"].contains(keypadMode ?? "")
                && Set(options.map(\.id)) == Set("0123456789*#".map(String.init))
                && (keypadMode == "dtmf" || (!(eraseLabel ?? "").isEmpty && !(clearLabel ?? "").isEmpty))
        case "toggle", "task": if case .bool = value { return true }; return false
        case "choice", "segmented": return options.contains { $0.id == value?.text }
        case "color": return options.contains { $0.id == value?.text }
            && options.allSatisfy { $0.id.range(of: "^#[0-9A-Fa-f]{6}$", options: .regularExpression) != nil }
        case "date":
            guard case let .text(text) = value else { return false }
            return text.isEmpty || Double(text).map { $0.isFinite && abs($0) <= 8640000000000000 } == true
        case "text": if case let .text(text) = value { return text.count <= (maximumLength ?? 10000) }; return false
        default: return value == nil
        }
    }

    enum Value: Decodable, Equatable {
        case text(String), bool(Bool), number(Double)
        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let flag = try? container.decode(Bool.self) { self = .bool(flag) }
            else if let number = try? container.decode(Double.self) { self = .number(number) }
            else { self = .text(try container.decode(String.self)) }
        }
        var text: String { if case let .text(text) = self { return text }; return "" }
        var bool: Bool { if case let .bool(flag) = self { return flag }; return false }
        var number: Double { if case let .number(number) = self { return number }; return 0 }
    }
}

struct NativeSurfaceSnapshot: Decodable, Equatable {
    struct Section: Decodable, Equatable, Identifiable {
        let id: String
        let title: String
        let footer: String
        let rows: [NativeSurfaceRow]
    }
    struct Chat: Decodable, Equatable {
        let draft: String; let placeholder: String; let followup: String
        let streaming: Bool; let actions: [NativeSurfaceRow]
    }
    struct Reader: Decodable, Equatable {
        let currentId: String?
        let targetId: String?
        let request: Int
        let following: Bool
        let footer: [NativeSurfaceRow]
        let scroll: NativeSurfaceRow?
        var actions: [NativeSurfaceRow] { footer + (scroll.map { [$0] } ?? []) }
    }
    let reader: Reader?
    let navigation: NativeSurfaceRow?
    let chat: Chat?
    let version: Int
    let revision: Int
    let title: String
    let appearance: String
    let largeTitle: Bool?
    let locale: String
    let direction: String
    let loading: Bool
    let failed: Bool
    let empty: String
    let sections: [Section]
    let toolbar: [NativeSurfaceRow]
    let searchEnabled: Bool
    let searchValue: String
    let searchPlaceholder: String
    let refreshEnabled: Bool
    let error: String
    let retry: String
    let loadingLabel: String

    var allRows: [NativeSurfaceRow] {
        toolbar + sections.flatMap(\.rows) + (chat?.actions ?? []) + (reader?.actions ?? []) + (navigation.map { [$0] } ?? [])
    }

    func replacingValue(id: String, value: NativeSurfaceRow.Value) -> Self {
        let sections = sections.map { section in
            Section(id: section.id, title: section.title, footer: section.footer,
                    rows: section.rows.map { $0.id == id ? $0.replacingValue(value) : $0 })
        }
        let reader = reader.map { reader in
            Reader(currentId: reader.currentId, targetId: reader.targetId, request: reader.request,
                   following: reader.following,
                   footer: reader.footer.map { $0.id == id ? $0.replacingValue(value) : $0 },
                   scroll: reader.scroll)
        }
        return Self(reader: reader, navigation: navigation.map { $0.id == id ? $0.replacingValue(value) : $0 },
                    chat: chat, version: version, revision: revision + 1, title: title,
                    appearance: appearance, largeTitle: largeTitle, locale: locale, direction: direction,
                    loading: loading, failed: failed, empty: empty, sections: sections, toolbar: toolbar,
                    searchEnabled: searchEnabled, searchValue: searchValue, searchPlaceholder: searchPlaceholder,
                    refreshEnabled: refreshEnabled, error: error, retry: retry, loadingLabel: loadingLabel)
    }

    func withoutContent() -> Self {
        Self(reader: nil, navigation: nil, chat: nil, version: version, revision: revision, title: "", appearance: appearance, largeTitle: false, locale: locale,
             direction: direction, loading: false, failed: false, empty: "", sections: [], toolbar: [],
             searchEnabled: false, searchValue: "", searchPlaceholder: "", refreshEnabled: false,
             error: error, retry: retry, loadingLabel: loadingLabel)
    }

    static func decode(_ input: Any) throws -> Self {
        let snapshot = try JSONDecoder().decode(Self.self, from: SafeJSON.data(withJSONObject: input))
        let rows = snapshot.allRows
        let ids = rows.map(\.id)
        guard snapshot.version == 1, snapshot.revision >= 0, (snapshot.chat?.draft.count ?? 0) <= 10000,
              snapshot.navigation.map({ row in
                  row.id == "main_destination" && row.kind == "segmented"
                      && Set(row.options.map(\.id)) == Set(["home", "tasks", "memories", "apps", "settings"])
                      && snapshot.chat == nil && snapshot.reader == nil
                      && snapshot.sections.isEmpty && snapshot.toolbar.isEmpty
                      && !snapshot.searchEnabled && !snapshot.refreshEnabled
              }) != false,
              snapshot.reader == nil || snapshot.chat == nil,
              snapshot.reader.map({ reader in
                  let contentIds = Set(snapshot.sections.flatMap(\.rows).map(\.id))
                  return reader.request >= 0
                      && reader.currentId.map { contentIds.contains($0) } != false
                      && reader.targetId.map { contentIds.contains($0) } != false
                      && (reader.scroll == nil || (reader.scroll?.kind == "menu"
                          && reader.scroll?.options.allSatisfy { $0.id == "suspend" || contentIds.contains($0.id) } == true))
              }) != false,
              ["system", "light", "dark"].contains(snapshot.appearance),
              ["ltr", "rtl"].contains(snapshot.direction), !snapshot.locale.isEmpty,
              Set(snapshot.sections.map(\.id)).count == snapshot.sections.count,
              Set(ids).count == ids.count, !ids.contains(where: { $0.isEmpty || $0.hasPrefix("_") }),
              rows.allSatisfy({ row in
                  ["label", "button", "navigation", "transcript", "rich_text", "image", "toggle", "task", "choice", "segmented", "color", "text", "menu", "date", "message_user", "message_ai", "chart", "waveform", "keypad", "slider", "progress"].contains(row.kind)
                      && Set(row.options.map(\.id)).count == row.options.count
                      && row.options.allSatisfy({ !$0.id.isEmpty })
                      && row.hasValidValue
                      && ((row.blocks ?? []).isEmpty || (row.kind == "rich_text" && row.blocks?.allSatisfy(\.valid) == true))
                      && (row.maximumValue == nil || ["slider", "progress", "image"].contains(row.kind))
                      && (row.plainText != true || ["message_ai", "message_user"].contains(row.kind))
                      && (row.kind == "keypad" || (row.keypadMode == nil && row.eraseLabel == nil && row.clearLabel == nil))
                      && row.hasValidImageURI
                      && (row.level == nil || (0...3).contains(row.level ?? -1))
                      && (row.maximumLength == nil || (row.kind == "text" && (1...262144).contains(row.maximumLength ?? 0)))
                      && (row.keyboard == nil || (row.kind == "text" && ["default", "phone", "email", "url", "decimal", "password"].contains(row.keyboard ?? "")))
                      && ((row.optionSearch == nil && row.optionClose == nil)
                          || (row.kind == "choice" && !(row.optionSearch ?? "").isEmpty && !(row.optionClose ?? "").isEmpty))
                      && (row.minimumDate == nil || Double(row.minimumDate ?? "").map { $0.isFinite && abs($0) <= 8640000000000000 } == true)
                      && (row.points ?? []).count <= 10000
                      && (row.points ?? []).allSatisfy { $0.x.isFinite && $0.y.isFinite }
                      && (row.kind != "waveform" || (row.points ?? []).allSatisfy { abs($0.y) <= 1 })
                      && Set((row.points ?? []).map(\.x)).count == (row.points ?? []).count
              }) else { throw ContractError.invalidSnapshot }
        return snapshot
    }
    enum ContractError: Error { case invalidSnapshot }
}

private extension NativeSurfaceRow {
    var hasValidImageURI: Bool {
        guard let imageUri else { return true }
        guard imageUri.count <= 4096, let url = URL(string: imageUri),
              url.user == nil, url.password == nil else { return false }
        return (url.scheme == "https" && !(url.host ?? "").isEmpty)
            || (url.isFileURL && (url.host ?? "").isEmpty && url.path.hasPrefix("/"))
    }
}

/// A blocking activity overlay request from the config channel. Dart applies the same label rule
/// before it sends one; the presenter refuses anything else and shows nothing.
struct NativeActivityRequest: Equatable {
    let id: Int
    let label: String
    let appearance: String
    let locale: String
    let direction: String

    static func decode(_ input: Any?) throws -> Self {
        guard let args = input as? [String: Any],
              let id = args["requestId"] as? Int, id >= 0,
              let label = args["label"] as? String, !label.isEmpty, label.count <= 200,
              let appearance = args["appearance"] as? String, ["system", "light", "dark"].contains(appearance),
              let locale = args["locale"] as? String, !locale.isEmpty,
              let direction = args["direction"] as? String, ["ltr", "rtl"].contains(direction)
        else { throw ContractError.invalidRequest }
        return Self(id: id, label: label, appearance: appearance, locale: locale, direction: direction)
    }
    enum ContractError: Error { case invalidRequest }
}

/// One OmiFeedback toast, as presentation values only. Dart keeps the callbacks; Swift reports how it ended.
struct NativeToastRequest: Decodable, Equatable {
    /// Each kind's only duration, matching OmiFeedbackTiming.
    static let durations = ["confirm": 1500, "info": 4000, "error": 8000, "undo": 5000, "progress": 60000]
    static let symbols: Set<String> = ["checkmark.circle.fill", "info.circle", "exclamationmark.circle.fill",
                                       "trash", "person", "tv", "progress"]
    let requestId: Int
    let session: String
    let kind: String
    let message: String
    let actionLabel: String?
    let closeLabel: String?
    let durationMs: Int
    let symbol: String
    let bottomClearance: Double
    let appearance: String
    let locale: String
    let direction: String

    /// The same rules as Dart's NativeToastRequest.valid.
    func validate() throws {
        func label(_ value: String?) -> Bool { value.map { (1...40).contains($0.count) } ?? true }
        guard requestId >= 0, (1...64).contains(session.count),
              let duration = Self.durations[kind], durationMs == duration,
              (1...1000).contains(message.count), !message.unicodeScalars.contains("\u{0}"),
              Self.symbols.contains(symbol), (symbol == "progress") == (kind == "progress"),
              kind == "undo" ? actionLabel != nil : (kind == "error" || actionLabel == nil),
              (closeLabel != nil) == (kind == "error"), label(actionLabel), label(closeLabel),
              bottomClearance.isFinite, (0.0...240.0).contains(bottomClearance),
              ["system", "light", "dark"].contains(appearance), !locale.isEmpty,
              ["ltr", "rtl"].contains(direction) else { throw ContractError.invalidToast }
    }

    static func decode(_ input: Any) throws -> Self {
        let request = try JSONDecoder().decode(Self.self, from: SafeJSON.data(withJSONObject: input))
        try request.validate()
        return request
    }
    enum ContractError: Error { case invalidToast }
}

/// Request ids strictly increase within one Dart process. A request carrying another session token (the
/// engine restarted) starts a new sequence, so a restarted counter is never refused for good.
struct NativeToastOrder {
    private var session: String?
    private var last = -1

    mutating func accept(_ request: NativeToastRequest) -> Bool {
        if request.session == session && request.requestId <= last { return false }
        session = request.session
        last = request.requestId
        return true
    }
}
