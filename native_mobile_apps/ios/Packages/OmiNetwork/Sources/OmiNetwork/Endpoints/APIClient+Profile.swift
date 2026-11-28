import Foundation

/// Account and data: export, usage, fair use, cancel subscription, referral, Wrapped, app data
/// access. Contracts from `backend/routers/users.py`, `payment.py`, `fair_use_admin.py`,
/// `referrals.py` and `wrapped.py`.
public extension APIClient {
    /// `GET v1/users/export` (not streamed, so a failure is a real HTTP error): one JSON object with
    /// profile, conversations, memories, people, tasks and chat. Saved as `omi-export.json` in a new
    /// temporary folder; returns its URL.
    func exportAllData() async throws -> URL {
        var exportRequest = try await request(.get, "v1/users/export")
        exportRequest.timeoutInterval = 300
        let (file, response): (URL, URLResponse)
        do {
            (file, response) = try await session.download(for: exportRequest)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            let body = (try? Data(contentsOf: file)).flatMap { String(bytes: $0.prefix(500), encoding: .utf8) } ?? ""
            throw APIError.http(status: status, body: body)
        }
        let folder = FileManager.default.temporaryDirectory.appending(path: "omi-export-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let destination = folder.appending(path: "omi-export.json")
        try FileManager.default.moveItem(at: file, to: destination)
        return destination
    }

    /// `GET v1/users/me/usage?period=&time_zone=`: only the requested period is filled, plus history.
    func usage(period: UsageStats.Period, timeZone: String) async throws -> UsageStats {
        let data = try await data(.get, "v1/users/me/usage", query: [
            URLQueryItem(name: "period", value: period.rawValue), URLQueryItem(name: "time_zone", value: timeZone),
        ])
        let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        func totals(_ json: [String: Any]?) -> UsageStats.Totals {
            UsageStats.Totals(
                transcriptionSeconds: json?["transcription_seconds"] as? Int ?? 0, words: json?["words_transcribed"] as? Int ?? 0,
                insights: json?["insights_gained"] as? Int ?? 0, memories: json?["memories_created"] as? Int ?? 0
            )
        }
        let history = (root["history"] as? [[String: Any]] ?? []).compactMap { item -> (date: String, totals: UsageStats.Totals)? in
            (item["date"] as? String).map { ($0, totals(item)) }
        }
        return UsageStats(totals: totals(root[period.rawValue] as? [String: Any]), history: history)
    }

    /// `GET v1/fair-use/status`. Missing limits fall back to Flutter's 2 / 8 / 10 hours.
    func fairUseStatus() async throws -> FairUseStatus {
        let root = try await JSONSerialization.jsonObject(with: data(.get, "v1/fair-use/status")) as? [String: Any] ?? [:]
        let limits = root["limits"] as? [String: Any] ?? [:]
        func number(_ value: Any?) -> Double? { (value as? NSNumber)?.doubleValue }
        let reference = root["case_ref"] as? String
        return FairUseStatus(
            stage: root["stage"] as? String ?? "none",
            caseReference: reference?.isEmpty == false ? reference : nil,
            today: .init(used: number(root["speech_hours_today"]) ?? 0, limit: number(limits["daily_hours"]) ?? 2),
            threeDays: .init(used: number(root["speech_hours_3day"]) ?? 0, limit: number(limits["three_day_hours"]) ?? 8),
            week: .init(used: number(root["speech_hours_weekly"]) ?? 0, limit: number(limits["weekly_hours"]) ?? 10),
            message: root["message"] as? String ?? ""
        )
    }

    /// `DELETE v1/payments/subscription` with `{reason, reason_details}`: Stripe cancels at the end of
    /// the billing period; the plan stays active until then.
    func cancelSubscription(reason: String?, details: String?) async throws {
        var fields: [String: String] = [:]
        if let reason { fields["reason"] = reason }
        if let details, !details.isEmpty { fields["reason_details"] = details }
        let body: Body = fields.isEmpty ? .none : try .json(JSONSerialization.data(withJSONObject: fields))
        let data = try await data(.delete, "v1/payments/subscription", body: body)
        let status = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["status"] as? String
        guard status == "ok" else { throw APIError.http(status: 200, body: String(bytes: data.prefix(300), encoding: .utf8) ?? "") }
    }

    /// `GET v1/users/profile` → the account's name and email (empty strings read as unknown).
    func userProfile() async throws -> UserProfile {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/profile")) as? [String: Any] ?? [:]
        func text(_ key: String) -> String? {
            guard let value = (object[key] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
                return nil
            }
            return value
        }
        return UserProfile(name: text("name"), email: text("email"))
    }

    /// `GET v1/users/me/referral` → the user's invite link.
    func referralURL() async throws -> URL? {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/users/me/referral")) as? [String: Any]
        return (object?["referral_url"] as? String).flatMap(URL.init(string:))
    }

    /// `GET v1/wrapped/{year}`; 400 for a year the backend does not serve.
    func wrapped(year: Int) async throws -> Wrapped {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/wrapped/\(year)")) as? [String: Any] ?? [:]
        return WrappedMapper.map(object, year: year)
    }

    /// `POST v1/wrapped/{year}/generate`: starts building it (a push says when it is ready).
    func generateWrapped(year: Int) async throws {
        _ = try await data(.post, "v1/wrapped/\(year)/generate")
    }

    /// Installed apps with an external integration, and what they read and when they run.
    func appsWithDataAccess() async throws -> [AppDataAccess] {
        let query = [
            URLQueryItem(name: "offset", value: "0"), URLQueryItem(name: "limit", value: "100"),
            URLQueryItem(name: "installed_apps", value: "true"),
        ]
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v2/apps/search", query: query)) as? [String: Any]
        return (object?["data"] as? [[String: Any]] ?? []).compactMap { app -> AppDataAccess? in
            guard let id = app["id"] as? String, app["enabled"] as? Bool ?? false,
                  (app["capabilities"] as? [String] ?? []).contains("external_integration") else { return nil }
            let integration = app["external_integration"] as? [String: Any]
            let actions = Set((integration?["actions"] as? [[String: Any]] ?? []).compactMap { $0["action"] as? String })
            return AppDataAccess(
                id: id, name: app["name"] as? String ?? id, imageURL: (app["image"] as? String).flatMap(URL.init(string:)),
                readsConversations: !actions.isDisjoint(with: ["create_conversation", "read_conversations"]),
                readsMemories: !actions.isDisjoint(with: ["create_facts", "read_memories"]),
                trigger: integration?["triggers_on"] as? String
            )
        }
    }
}

enum WrappedMapper {
    static func map(_ json: [String: Any], year: Int) -> Wrapped {
        let status = (json["status"] as? String).flatMap(Wrapped.Status.init(rawValue:)) ?? .error
        let progress = (json["progress"] as? [String: Any])?["step"] as? String
        guard let result = json["result"] as? [String: Any] else { return Wrapped(year: year, status: status, progress: progress) }
        func card(_ value: Any?, title: String? = nil, text: String = "description") -> Wrapped.Highlight? {
            guard let item = value as? [String: Any], let heading = title ?? item["title"] as? String else { return nil }
            return .init(emoji: item["emoji"] as? String, title: heading, text: item[text] as? String ?? "")
        }
        let days = result["memorable_days"] as? [String: Any] ?? [:]
        let highlights = [
            card(days["most_fun_day"]), card(days["most_productive_day"]), card(days["most_stressful_day"]),
            card(result["funniest_event"], text: "story"), card(result["most_embarrassing_event"], text: "story"),
            card(result["struggle"]), card(result["personal_win"]),
        ].compactMap(\.self)
        let buddies = (result["top_buddies"] as? [[String: Any]] ?? []).compactMap { buddy -> Wrapped.Highlight? in
            guard let name = buddy["name"] as? String else { return nil }
            let text = buddy["context"] as? String ?? buddy["relationship"] as? String ?? ""
            return .init(emoji: buddy["emoji"] as? String, title: name, text: text)
        }
        let phrases = (result["top_phrases"] as? [Any] ?? []).compactMap { $0 as? String ?? ($0 as? [String: Any])?["phrase"] as? String }
        return Wrapped(
            year: year, status: status, progress: progress,
            conversations: result["total_conversations"] as? Int ?? 0,
            daysActive: result["days_active"] as? Int ?? 0,
            hours: (result["total_time_hours"] as? NSNumber)?.doubleValue ?? 0,
            topCategories: result["top_categories"] as? [String] ?? [],
            tasksDone: result["completed_action_items"] as? Int ?? 0,
            tasks: result["total_action_items"] as? Int ?? 0,
            topPhrases: phrases, buddies: buddies, highlights: highlights
        )
    }
}
