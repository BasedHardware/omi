import Foundation

/// Values accepted by the property-list persistence boundary. A caller cannot
/// pass an arbitrary `Any`, an optional hidden inside `Any`, or a custom model.
/// Use `setRecords` for Codable arrays instead of type-erasing model fields.
enum PlistValue {
    case string(String)
    case bool(Bool)
    case int(Int)
    case int64(Int64)
    case double(Double)
    case date(Date)
    case data(Data)
    case array([PlistValue])
    case dictionary([String: PlistValue])

    fileprivate func foundationValue() throws -> Any {
        switch self {
        case .string(let value): return value
        case .bool(let value): return value
        case .int(let value): return value
        case .int64(let value): return value
        case .double(let value):
            guard value.isFinite else { throw SafeFoundationError.nonFiniteNumber }
            return value
        case .date(let value):
            guard value.timeIntervalSinceReferenceDate.isFinite else { throw SafeFoundationError.nonFiniteNumber }
            return value
        case .data(let value): return value
        case .array(let values): return try values.map { try $0.foundationValue() }
        case .dictionary(let values): return try values.mapValues { try $0.foundationValue() }
        }
    }
}

enum SafeFoundationError: Error {
    case nonFiniteNumber
    case invalidJSONObject
}

enum SafeDefaults {
    /// Named write entry point for call sites checked by the iOS raw-set lint.
    /// Keep validation and nil-removal behavior centralized in `set`.
    static func store(_ value: PlistValue?, forKey key: String, in defaults: UserDefaults = .standard) throws {
        try set(value, forKey: key, in: defaults)
    }

    /// Nil means remove the key. A failed validation leaves its old value intact.
    static func set(_ value: PlistValue?, forKey key: String, in defaults: UserDefaults = .standard) throws {
        guard let value else {
            defaults.removeObject(forKey: key)
            return
        }
        let object = try value.foundationValue()
        defaults.set(object, forKey: key)
    }

    /// Keep legacy dictionary-array readers compatible while validating every
    /// record field through PlistValue before the write.
    static func setPlistRecords(
        _ records: [[String: PlistValue]]?, forKey key: String, in defaults: UserDefaults = .standard
    ) throws {
        try set(records.map { .array($0.map { .dictionary($0) }) }, forKey: key, in: defaults)
    }

    /// Record arrays are stored as Data, never as unchecked dictionaries.
    /// JSONEncoder rejects non-finite numeric fields before UserDefaults sees them.
    static func setRecords<Record: Encodable>(
        _ records: [Record]?, forKey key: String, in defaults: UserDefaults = .standard
    ) throws {
        guard let records else {
            defaults.removeObject(forKey: key)
            return
        }
        let data = try JSONEncoder().encode(records)
        defaults.set(data, forKey: key)
    }

    static func records<Record: Decodable>(
        _ type: Record.Type, forKey key: String, in defaults: UserDefaults = .standard
    ) throws -> [Record]? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try JSONDecoder().decode([Record].self, from: data)
    }
}

enum SafeJSON {
    /// Reject unsupported Foundation values before JSONSerialization crosses
    /// the Objective-C exception boundary. Non-finite numbers are errors.
    static func data(withJSONObject object: Any, options: JSONSerialization.WritingOptions = []) throws -> Data {
        let checked = try validated(object)
        guard JSONSerialization.isValidJSONObject(checked) else {
            throw SafeFoundationError.invalidJSONObject
        }
        return try JSONSerialization.data(withJSONObject: checked, options: options)
    }

    private static func validated(_ value: Any) throws -> Any {
        if value is NSNull { return value }
        if let value = value as? String { return value }
        if let value = value as? NSNumber {
            guard value.doubleValue.isFinite else { throw SafeFoundationError.nonFiniteNumber }
            return value
        }
        if let value = value as? [Any] { return try value.map { try validated($0) } }
        if let value = value as? [String: Any] { return try value.mapValues { try validated($0) } }
        throw SafeFoundationError.invalidJSONObject
    }
}

enum CheckedIntegerConversion {
    /// Truncates finite values toward zero, matching Swift's numeric conversion.
    static func int64(_ value: Double) -> Int64? {
        guard value.isFinite, value >= -9_223_372_036_854_775_808.0,
              value < 9_223_372_036_854_775_808.0 else { return nil }
        return Int64(value)
    }

    static func int(_ value: Double) -> Int? {
        guard value.isFinite, value >= Double(Int.min), value < -Double(Int.min) else { return nil }
        return Int(value)
    }
}
