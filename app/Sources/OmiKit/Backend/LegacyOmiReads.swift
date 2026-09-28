import Foundation

// Port of `react-native/src/legacyOmiReads.ts` — Old-plane (api.omi.me)
// projection reads with the synthesized `omi-offset:` pagination page.

let legacyOmiReadLimit = 50

public enum LegacyOmiReadError: Error, Sendable, Equatable {
    case malformedResponse
    case malformedText
    case malformedID
    case malformedBoolean
    case malformedTimestamp
    case malformedOrder
    case malformedList
    case duplicateIDs
    case malformedCursor
    case malformedVisibility
    case malformedCreationTime
    case malformedPagination
    case malformedCompletion
    case malformedProvenance
}

func legacyObject(_ value: JSONValue?) throws -> JSONValue {
    guard let value, value.isRecord else { throw LegacyOmiReadError.malformedResponse }
    return value
}

/// Absent or JSON null (the TS `undefined || null` idiom).
func isNullValue(_ value: JSONValue?) -> Bool {
    value == nil || value!.isNull
}

func legacyText(_ value: JSONValue?, _ fallback: String? = nil) throws -> String {
    if isNullValue(value) {
        if let fallback { return fallback }
    }
    guard let text = value?.stringValue else { throw LegacyOmiReadError.malformedText }
    return text
}

func legacyID(_ value: JSONValue?) throws -> String {
    let result = try legacyText(value)
    guard !result.isEmpty else { throw LegacyOmiReadError.malformedID }
    return result
}

func legacyBool(_ value: JSONValue?, _ fallback: Bool = false) throws -> Bool {
    if isNullValue(value) { return fallback }
    guard let flag = value?.boolValue else { throw LegacyOmiReadError.malformedBoolean }
    return flag
}

func legacyDate(_ value: JSONValue?) throws -> String? {
    if isNullValue(value) { return nil }
    guard let iso = isoString(fromDate: value) else {
        throw LegacyOmiReadError.malformedTimestamp
    }
    return iso
}

func legacyMilliseconds(_ value: JSONValue?) throws -> Int64? {
    guard let parsed = try legacyDate(value) else { return nil }
    guard let seconds = ISO8601Reader.epochSeconds(parsed) else {
        throw LegacyOmiReadError.malformedTimestamp
    }
    return Int64(seconds * 1000)
}

func legacyInteger(_ value: JSONValue?, nonnegative: Bool = false) throws -> Int64 {
    if isNullValue(value) { return 0 }
    guard let integer = value?.safeIntegerValue, !(nonnegative && integer < 0) else {
        throw LegacyOmiReadError.malformedOrder
    }
    return integer
}

func legacyRows(_ value: JSONValue?) throws -> [JSONValue] {
    guard let array = value?.arrayValue, array.count <= legacyOmiReadLimit else {
        throw LegacyOmiReadError.malformedList
    }
    var seen = Set<String>()
    return try array.map { item in
        let row = try legacyObject(item)
        let key = try legacyID(row["id"])
        if seen.contains(key) { throw LegacyOmiReadError.duplicateIDs }
        seen.insert(key)
        return row
    }
}

/// Port of `offset(cursor)` from legacyOmiReads.ts.
func legacyOffset(_ cursor: String?) throws -> Int {
    guard let cursor else { return 0 }
    guard cursor.hasPrefix("omi-offset:") else { throw LegacyOmiReadError.malformedCursor }
    let digits = String(cursor.dropFirst("omi-offset:".count))
    guard !digits.isEmpty, digits.first.map({ $0 >= "1" && $0 <= "9" }) == true,
        digits.unicodeScalars.allSatisfy({ $0.value >= 0x30 && $0.value <= 0x39 })
    else { throw LegacyOmiReadError.malformedCursor }
    guard let value = Int(digits), value <= Int(Int32.max) - legacyOmiReadLimit else {
        throw LegacyOmiReadError.malformedCursor
    }
    return value
}

/// Port of `page(start, count, ...)` from legacyOmiReads.ts.
func legacyPage(
    _ start: Int, _ count: Int, hasMore: Bool = false, truncated: Bool = false,
    known: Bool = false
) -> ReadPageState {
    ReadPageState(
        windowStatus: truncated ? .incomplete : hasMore ? .more : known ? .complete : .unknown,
        complete: known && !hasMore && !truncated,
        hasMore: hasMore && count > 0 && !truncated,
        nextCursor:
            hasMore && count > 0 && !truncated ? "omi-offset:\(start + count)" : nil,
        completenessStatus: truncated ? .incomplete : known ? .complete : .unknown,
        reasons: truncated
            ? ["The service returned a partial list. Refresh to retry."]
            : known
                ? []
                : ["The Omi API does not provide snapshot completeness for this list."]
    )
}

func legacyRead(
    _ transport: BackendTransport, path: String
) async throws -> JSONValue {
    let response = try await transport.request(
        BackendRequest(
            id: "desktop-omi-read", expectedApiContract: .omi, method: .GET,
            path: path))
    if response.status != 200 {
        if response.status == 401 {
            throw ReadCopyError(desktopBackendUnauthorizedCopy)
        }
        throw ReadCopyError(
            response.status >= 500 ? desktopBackendServiceCopy : desktopReadFailureCopy)
    }
    guard let body = response.body else {
        throw ReadClientError.malformed("desktop-omi-read returned an empty response")
    }
    guard let parsed = JSON.parseOrNull(body) else {
        throw ReadClientError.malformed("desktop-omi-read returned invalid JSON")
    }
    return parsed
}

public func loadOmiConversations(
    _ transport: BackendTransport, cursor: String?
) async throws -> DomainRead<ConversationProjection> {
    let start = try legacyOffset(cursor)
    let records = try legacyRows(
        try await legacyRead(transport, path: "/v1/conversations?limit=50&offset=\(start)")
    )
    let items = try records.map { row -> ConversationProjection in
        let structured = try legacyObject(row["structured"])
        let title = try legacyText(structured["title"], "")
        let summary = try legacyText(structured["overview"], "")
        guard let createdAt = try legacyDate(row["created_at"]) else {
            throw LegacyOmiReadError.malformedCreationTime
        }
        let visibility = try legacyText(row["visibility"], "private")
        guard visibility == "private" || visibility == "public" || visibility == "shared"
        else { throw LegacyOmiReadError.malformedVisibility }
        return ConversationProjection(
            id: try legacyID(row["id"]), title: title, summary: summary,
            searchableText: "\(title)\n\(summary)", createdAt: createdAt,
            updatedAt: try legacyDate(row["updated_at"]),
            startedAt: try legacyDate(row["started_at"]),
            finishedAt: try legacyDate(row["finished_at"]),
            starred: try legacyBool(row["starred"]),
            status: try legacyText(row["status"], "completed"),
            source: try legacyText(row["source"], isNullValue(row["source"]) ? "unknown" : "omi"),
            visibility: ProjectionVisibility(rawValue: visibility) ?? .priv,
            folderId: isNullValue(row["folder_id"]) ? nil : try legacyText(row["folder_id"]),
            locked: try legacyBool(row["is_locked"]),
            discarded: try legacyBool(row["discarded"])
        )
    }
    return DomainRead(
        apiContract: .omi, items: items, page: legacyPage(start, items.count))
}

public func loadOmiMemories(
    _ transport: BackendTransport, cursor: String?
) async throws -> DomainRead<MemoryProjection> {
    let start = try legacyOffset(cursor)
    let records = try legacyRows(
        try await legacyRead(transport, path: "/v3/memories?limit=50&offset=\(start)")
    )
    let items = try records.map { row -> MemoryProjection in
        let content = try legacyText(row["content"])
        let created = try legacyMilliseconds(row["created_at"])
        let conversation =
            isNullValue(row["conversation_id"])
            ? nil : try legacyID(row["conversation_id"])
        return MemoryProjection(
            id: try legacyID(row["id"]), title: content, summary: content,
            searchableText: content,
            citations: conversation == nil ? [] : [conversation!],
            timestamp: created == nil ? nil : created! / 1000,
            provenance: MemoryProvenance(
                label: nil, synthesisVersion: nil, inputDigest: nil,
                outputDigest: nil)
        )
    }
    return DomainRead(
        apiContract: .omi, items: items, page: legacyPage(start, items.count))
}

public func loadOmiTasks(
    _ transport: BackendTransport, cursor: String?
) async throws -> TaskRead {
    let start = try legacyOffset(cursor)
    let envelope = try legacyObject(
        try await legacyRead(transport, path: "/v1/action-items?limit=50&offset=\(start)")
    )
    guard envelope["has_more"]?.boolValue != nil else {
        throw LegacyOmiReadError.malformedPagination
    }
    let records = try legacyRows(envelope["action_items"])
    let items = try records.map { row -> TaskProjection in
        let description = try legacyText(row["description"])
        let completed = try legacyBool(row["completed"])
        guard row["completed"]?.boolValue != nil else {
            throw LegacyOmiReadError.malformedCompletion
        }
        let evidenceOptional = row["provenance"]
        let evidence = isNullValue(evidenceOptional) ? JSONValue.array([]) : evidenceOptional!
        guard evidence.arrayValue != nil else {
            throw LegacyOmiReadError.malformedProvenance
        }
        let provenance = try evidence.arrayValue!.map { item -> String in
            let ref = try legacyObject(item)
            _ = try legacyID(ref["id"])
            return JSON.serialize(ref)
        }
        return TaskProjection(
            id: try legacyID(row["id"]), title: description,
            summary: completed ? "Completed" : "Pending",
            searchableText: description, completed: completed,
            completedAt: try legacyMilliseconds(row["completed_at"]),
            dueAt: try legacyMilliseconds(row["due_at"]),
            owner: isNullValue(row["owner"]) ? nil : try legacyText(row["owner"]),
            source: try legacyText(row["source"], "legacy"),
            provenance: provenance,
            sortOrder: Int(try legacyInteger(row["sort_order"])),
            indentLevel: Int(try legacyInteger(row["indent_level"], nonnegative: true)),
            createdAt: try legacyMilliseconds(row["created_at"]),
            updatedAt: try legacyMilliseconds(row["updated_at"]),
            revision: nil
        )
    }
    return TaskRead(
        apiContract: .omi, items: items,
        page: legacyPage(
            start, items.count, hasMore: envelope["has_more"]?.boolValue ?? false,
            truncated: try legacyBool(envelope["truncated"]), known: true),
        accountEpoch: nil
    )
}
