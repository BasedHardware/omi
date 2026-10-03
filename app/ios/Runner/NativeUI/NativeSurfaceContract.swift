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
    struct Point: Decodable, Equatable, Identifiable {
        let x: Double; let y: Double; let label: String
        var id: Double { x }
    }
    let points: [Point]?


    var hasValidValue: Bool {
        switch kind {
        case "toggle", "task": if case .bool = value { return true }; return false
        case "choice": return options.contains { $0.id == value?.text }
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

    func withoutContent() -> Self {
        Self(chat: nil, version: version, revision: revision, title: "", appearance: appearance, locale: locale,
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
                  ["label", "button", "toggle", "task", "choice", "text", "menu", "date", "message_user", "message_ai", "chart"].contains(row.kind)
                      && Set(row.options.map(\.id)).count == row.options.count
                      && row.options.allSatisfy({ !$0.id.isEmpty })
                      && row.hasValidValue
                      && (row.maximumLength == nil || (row.kind == "text" && (1...10000).contains(row.maximumLength ?? 0)))
                      && (row.minimumDate == nil || Double(row.minimumDate ?? "").map { $0.isFinite && abs($0) <= 8640000000000000 } == true)
                      && (row.points ?? []).count <= 10000
                      && (row.points ?? []).allSatisfy { $0.x.isFinite && $0.y.isFinite }
                      && Set((row.points ?? []).map(\.x)).count == (row.points ?? []).count
              }) else { throw ContractError.invalidSnapshot }
        return snapshot
    }
    enum ContractError: Error { case invalidSnapshot }
}
