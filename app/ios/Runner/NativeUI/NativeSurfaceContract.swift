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
    let visibilityEnabled: Bool?
    struct Point: Decodable, Equatable, Identifiable {
        let x: Double; let y: Double; let label: String
        var id: Double { x }
    }
    let points: [Point]?

    func replacingValue(_ value: Value?) -> Self {
        Self(id: id, title: title, kind: kind, subtitle: subtitle, value: value,
             options: options, destructive: destructive, enabled: enabled, symbol: symbol,
             minimumDate: minimumDate, maximumLength: maximumLength, keyboard: keyboard,
             optionSearch: optionSearch, optionClose: optionClose, keypadMode: keypadMode,
             eraseLabel: eraseLabel, clearLabel: clearLabel, plainText: plainText, imageUri: imageUri,
             level: level, visibilityEnabled: visibilityEnabled, points: points)
    }


    var hasValidValue: Bool {
        switch kind {
        case "keypad":
            guard case let .text(text) = value else { return false }
            return text.count <= 10000 && ["dialer", "dtmf"].contains(keypadMode ?? "")
                && Set(options.map(\.id)) == Set("0123456789*#".map(String.init))
                && (keypadMode == "dtmf" || (!(eraseLabel ?? "").isEmpty && !(clearLabel ?? "").isEmpty))
        case "toggle", "task": if case .bool = value { return true }; return false
        case "choice", "segmented": return options.contains { $0.id == value?.text }
        case "color": return options.contains { $0.id == value?.text }
            && options.allSatisfy { $0.id.range(of: "^#[0-9A-Fa-f]{6}$", options: .regularExpression) != nil }
        case "date": return value?.text == "" || value.flatMap { Double($0.text) }.map { $0.isFinite && abs($0) <= 8640000000000000 } == true
        case "text": if case let .text(text) = value { return text.count <= (maximumLength ?? 10000) }; return false
        default: return value == nil
        }
    }

    enum Value: Decodable, Equatable {
        case text(String), bool(Bool)
        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let flag = try? container.decode(Bool.self) { self = .bool(flag) }
            else { self = .text(try container.decode(String.self)) }
        }
        var text: String { if case let .text(text) = self { return text }; return "" }
        var bool: Bool { if case let .bool(flag) = self { return flag }; return false }
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

    var allRows: [NativeSurfaceRow] { toolbar + sections.flatMap(\.rows) + (chat?.actions ?? []) }

    func replacingValue(id: String, value: NativeSurfaceRow.Value) -> Self {
        let sections = sections.map { section in
            Section(id: section.id, title: section.title, footer: section.footer,
                    rows: section.rows.map { $0.id == id ? $0.replacingValue(value) : $0 })
        }
        return Self(chat: chat, version: version, revision: revision + 1, title: title,
                    appearance: appearance, largeTitle: largeTitle, locale: locale, direction: direction,
                    loading: loading, failed: failed, empty: empty, sections: sections, toolbar: toolbar,
                    searchEnabled: searchEnabled, searchValue: searchValue, searchPlaceholder: searchPlaceholder,
                    refreshEnabled: refreshEnabled, error: error, retry: retry, loadingLabel: loadingLabel)
    }

    func withoutContent() -> Self {
        Self(chat: nil, version: version, revision: revision, title: "", appearance: appearance, largeTitle: false, locale: locale,
             direction: direction, loading: false, failed: false, empty: "", sections: [], toolbar: [],
             searchEnabled: false, searchValue: "", searchPlaceholder: "", refreshEnabled: false,
             error: error, retry: retry, loadingLabel: loadingLabel)
    }

    static func decode(_ input: Any) throws -> Self {
        let snapshot = try JSONDecoder().decode(Self.self, from: SafeJSON.data(withJSONObject: input))
        let rows = snapshot.toolbar + snapshot.sections.flatMap(\.rows) + (snapshot.chat?.actions ?? [])
        let ids = rows.map(\.id)
        guard snapshot.version == 1, snapshot.revision >= 0, (snapshot.chat?.draft.count ?? 0) <= 10000,
              ["system", "light", "dark"].contains(snapshot.appearance),
              ["ltr", "rtl"].contains(snapshot.direction), !snapshot.locale.isEmpty,
              Set(snapshot.sections.map(\.id)).count == snapshot.sections.count,
              Set(ids).count == ids.count, !ids.contains(where: { $0.isEmpty || $0.hasPrefix("_") }),
              rows.allSatisfy({ row in
                  ["label", "button", "navigation", "toggle", "task", "choice", "segmented", "color", "text", "menu", "date", "message_user", "message_ai", "chart", "waveform", "keypad"].contains(row.kind)
                      && Set(row.options.map(\.id)).count == row.options.count
                      && row.options.allSatisfy({ !$0.id.isEmpty })
                      && row.hasValidValue
                      && (row.plainText != true || ["message_ai", "message_user"].contains(row.kind))
                      && (row.kind == "keypad" || (row.keypadMode == nil && row.eraseLabel == nil && row.clearLabel == nil))
                      && row.hasValidImageURI
                      && (row.level == nil || (0...3).contains(row.level ?? -1))
                      && (row.maximumLength == nil || (row.kind == "text" && (1...10000).contains(row.maximumLength ?? 0)))
                      && (row.keyboard == nil || (row.kind == "text" && ["default", "phone", "email", "url", "decimal"].contains(row.keyboard ?? "")))
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
