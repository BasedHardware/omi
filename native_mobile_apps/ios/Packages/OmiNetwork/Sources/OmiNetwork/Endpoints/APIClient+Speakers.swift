import Foundation
import OmiCore

/// Who said what: naming voices in a transcript, the "Who is this?" prompts, people's voice samples
/// (backend `routers/conversations.py`, `speaker_labels.py`, `speaker_tag_prompts.py`, `users.py`, `people.py`).
public extension APIClient {
    // MARK: People

    /// `GET v1/users/people?include_stats=true`: talk time, last heard and conversation counts too.
    func peopleWithStats() async throws -> [Person] {
        let data = try await data(.get, "v1/users/people", query: [
            URLQueryItem(name: "include_speech_samples", value: "true"), URLQueryItem(name: "include_stats", value: "true"),
        ])
        return try (JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []).compactMap(PersonMapper.map)
    }

    /// `POST v1/users/people` (idempotent by name): the stored person.
    func createPerson(named name: String) async throws -> Person {
        let data = try await data(.post, "v1/users/people", body: json(["name": name]))
        guard let person = try (JSONSerialization.jsonObject(with: data) as? [String: Any]).flatMap(PersonMapper.map) else {
            throw APIError.decoding("person")
        }
        return person
    }

    /// `PATCH v1/users/people/{id}/pinned?value=`.
    func setPersonPinned(_ id: String, pinned: Bool) async throws {
        _ = try await data(.patch, "v1/users/people/\(id)/pinned", query: [URLQueryItem(name: "value", value: String(pinned))])
    }

    /// `DELETE v1/users/people/{id}/speech-samples/{index}`.
    func deleteSpeechSample(personID: String, index: Int) async throws {
        _ = try await data(.delete, "v1/users/people/\(personID)/speech-samples/\(index)")
    }

    /// `POST v1/conversations/search` with `speaker_id`: conversations this person speaks in, newest first.
    func conversations(withPerson personID: String, page: Int, perPage: Int) async throws -> [Conversation] {
        let data = try await data(.post, "v1/conversations/search", body: json([
            "query": "", "page": page, "per_page": perPage, "include_discarded": false, "speaker_id": personID,
        ]))
        return try decode(PersonConversationsPage.self, from: data).items.map(ConversationMapper.map)
    }

    // MARK: Transcript labels

    /// Names lines: `PATCH …/assign-speaker/{speaker}` for every line of a voice, otherwise
    /// `PATCH …/segments/assign-bulk`. Returns the updated conversation.
    func assignSpeaker(
        conversationID: String, segmentIDs: [String], speakerID: Int?, to target: SpeakerTarget
    ) async throws -> ConversationDetail {
        let (type, value): (String, String) = switch target {
        case .user: ("is_user", "true")
        case let .person(id): ("person_id", id)
        }
        let body = try json(["segment_ids": segmentIDs, "assign_type": type, "value": value])
        let response: Data = if let speakerID {
            try await data(
                .patch, "v1/conversations/\(conversationID)/assign-speaker/\(speakerID)",
                query: [URLQueryItem(name: "assign_type", value: type), URLQueryItem(name: "value", value: value)], body: body
            )
        } else {
            try await data(.patch, "v1/conversations/\(conversationID)/segments/assign-bulk", body: body)
        }
        return try ConversationMapper.detail(decode(OmiAPI.Conversation.self, from: response))
    }

    /// `POST v1/conversations/{id}/speakers/{speaker}/reject`: the label on this voice is wrong.
    func rejectSpeaker(
        conversationID: String, speakerID: Int, kind: SpeakerRejection, personID: String?, segmentIDs: [String]?
    ) async throws -> ConversationDetail {
        var fields: [String: Any] = ["kind": kind.rawValue]
        if let personID { fields["person_id"] = personID }
        if let segmentIDs { fields["segment_ids"] = segmentIDs }
        let data = try await data(.post, "v1/conversations/\(conversationID)/speakers/\(speakerID)/reject", body: json(fields))
        return try ConversationMapper.detail(decode(OmiAPI.Conversation.self, from: data))
    }

    /// `GET v1/users/people/{id}/voice-matches`: unnamed voices in recent conversations that sound like them.
    func voiceMatches(personID: String) async throws -> [VoiceMatch] {
        let object = try await jsonObject(.get, "v1/users/people/\(personID)/voice-matches")
        return (object["matches"] as? [[String: Any]] ?? []).compactMap(SpeakerMapper.voiceMatch)
    }

    // MARK: "Who is this?" prompts

    /// `GET v1/speaker-tag-prompts`: today's few voices to confirm (empty while cooling down or disabled).
    func speakerPrompts() async throws -> [SpeakerPrompt] {
        let object = try await jsonObject(.get, "v1/speaker-tag-prompts")
        return (object["prompts"] as? [[String: Any]] ?? []).compactMap(SpeakerMapper.prompt)
    }

    /// `POST v1/speaker-tag-prompts/shown`: starts the once-a-day cooldown.
    func markSpeakerPromptsShown(_ ids: [String]) async throws {
        _ = try await data(.post, "v1/speaker-tag-prompts/shown", body: json(["prompt_ids": Array(ids.prefix(10))]))
    }

    /// `POST v1/speaker-tag-prompts/dismiss`: closed without answering; Omi asks less often.
    func dismissSpeakerPrompts() async throws {
        _ = try await data(.post, "v1/speaker-tag-prompts/dismiss")
    }

    /// `POST v1/speaker-tag-prompts/answer`.
    func answerSpeakerPrompt(_ prompt: SpeakerPrompt, answer: SpeakerPromptAnswer) async throws {
        var fields: [String: Any] = [
            "prompt_id": prompt.id, "kind": prompt.kind.rawValue, "origin": prompt.origin,
            "conversation_id": prompt.conversationID, "speaker_id": prompt.speakerID,
            "segment_ids": Array(prompt.segmentIDs.prefix(50)), "answer": answer.wire,
        ]
        switch answer {
        case let .person(id): fields["person_id"] = id
        case let .newPerson(name): fields["name"] = name
        default: break
        }
        if let suggested = prompt.suggestedPersonID { fields["suggested_person_id"] = suggested }
        _ = try await data(.post, "v1/speaker-tag-prompts/answer", body: json(fields))
    }

    /// `GET v1/speaker-tag-prompts/clip`: up to 12 s of the user's own stored audio, as WAV bytes.
    func speakerClip(conversationID: String, start: Double, end: Double) async throws -> Data {
        let object = try await jsonObject(.get, "v1/speaker-tag-prompts/clip", query: [
            URLQueryItem(name: "conversation_id", value: conversationID),
            URLQueryItem(name: "start", value: String(format: "%.3f", start)),
            URLQueryItem(name: "end", value: String(format: "%.3f", min(end, start + 12))),
        ])
        guard let base64 = object["audio_base64"] as? String, let wav = Data(base64Encoded: base64) else {
            throw APIError.decoding("clip")
        }
        return wav
    }

    // MARK: Voice settings

    func voiceProfileSettings() async throws -> VoiceProfileSettings {
        try await SpeakerMapper.settings(jsonObject(.get, "v1/users/voice-profile-settings"))
    }

    func updateVoiceProfileSettings(asksToTag: Bool?, savesOtherVoices: Bool?) async throws -> VoiceProfileSettings {
        var fields: [String: Any] = ["source": "settings"]
        if let asksToTag { fields["speaker_tag_prompts_enabled"] = asksToTag }
        if let savesOtherVoices { fields["save_other_voice_profiles"] = savesOtherVoices }
        return try await SpeakerMapper.settings(jsonObject(.patch, "v1/users/voice-profile-settings", body: json(fields)))
    }

    func ignoredVoices() async throws -> [IgnoredVoice] {
        let object = try await jsonObject(.get, "v1/speaker-tag-prompts/ignored-voices")
        return (object["voices"] as? [[String: Any]] ?? []).compactMap(SpeakerMapper.ignoredVoice)
    }

    /// `DELETE v1/speaker-tag-prompts/ignored-voices/{conversation}/{speaker}`: Omi may ask about it again.
    func restoreIgnoredVoice(conversationID: String, speakerID: Int) async throws {
        _ = try await data(.delete, "v1/speaker-tag-prompts/ignored-voices/\(conversationID)/\(speakerID)")
    }

    // MARK: Helpers

    private func json(_ object: [String: Any]) throws -> Body {
        try .json(JSONSerialization.data(withJSONObject: object))
    }

    private func jsonObject(
        _ method: Method, _ path: String, query: [URLQueryItem] = [], body: Body = .none
    ) async throws -> [String: Any] {
        let data = try await data(method, path, query: query, body: body)
        return try (JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }
}

private struct PersonConversationsPage: Decodable {
    let items: [OmiAPI.Conversation]
}
