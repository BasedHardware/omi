import Foundation
import OmiCore

enum ConversationMapper {
    static func map(_ dto: OmiAPI.Conversation) -> Conversation {
        let structured = dto.structured
        return Conversation(
            id: dto.id,
            title: structured.title.flatMap { $0.isEmpty ? nil : $0 } ?? "",
            overview: structured.overview ?? "",
            emoji: structured.emoji.flatMap { $0.isEmpty ? nil : $0 },
            category: structured.category?.rawValue,
            createdAt: BackendDate.parse(dto.createdAt) ?? .distantPast,
            startedAt: BackendDate.parse(dto.startedAt),
            finishedAt: BackendDate.parse(dto.finishedAt),
            status: status(dto.status),
            isStarred: dto.starred ?? false,
            actionItemCount: structured.actionItems?.count ?? 0,
            folderID: dto.folderId,
            visibility: visibility(dto.visibility),
            isLocked: dto.isLocked ?? false,
            summaryRetryable: dto.summaryRetryable ?? false,
            location: dto.geolocation.map {
                ConversationLocation(latitude: $0.latitude, longitude: $0.longitude, address: $0.address, googlePlaceID: $0.googlePlaceId)
            },
            isDiscarded: dto.discarded ?? false,
            captureGroupID: (dto.captureGroup?.members?.count ?? 0) > 1 ? dto.captureGroup?.id : nil,
            captureGroupPrimaryID: dto.captureGroup?.primaryId,
            people: people(structured.participants ?? [], event: dto.calendarEvent)
        )
    }

    static func status(_ status: OmiAPI.ConversationStatus?) -> Conversation.Status {
        switch status {
        case .in_progress: .inProgress
        case .processing: .processing
        case .merging: .merging
        case .completed, nil: .completed
        case .failed: .failed
        case ._unknown: .unknown
        }
    }

    static func visibility(_ visibility: OmiAPI.ConversationVisibility?) -> Conversation.Visibility {
        switch visibility {
        case .shared: .shared
        case .public_: .public
        case .private_, ._unknown, nil: .private
        }
    }

    static func detail(_ dto: OmiAPI.Conversation) -> ConversationDetail {
        let lines = transcript(dto.transcriptSegments ?? [])
        let structured = dto.structured
        let apps = (dto.appsResults ?? [])
            .map { ConversationDetail.AppSummary(appID: $0.appId, content: $0.content.trimmingCharacters(in: .whitespacesAndNewlines)) }
            .filter { !$0.content.isEmpty }
        let events = (structured.events ?? []).map { event in
            ConversationDetail.Event(
                title: event.title, description: event.description_ ?? "",
                start: BackendDate.parse(event.start), duration: event.duration ?? 30, isCreated: event.created ?? false
            )
        }
        let conversation = map(dto)
        var detail = ConversationDetail(
            conversation: conversation,
            summaryActionItems: (structured.actionItems ?? []).map(\.description_).filter { !$0.isEmpty },
            transcript: lines,
            summary: apps.first?.content ?? summary(overview: structured.overview, sections: structured.sections ?? []),
            // Only for Omi's own summary: an app's result has no gist of its own. The gist comes with
            // the generated sections; an edited summary drops them, and its old gist with them.
            gist: apps.isEmpty && !(structured.sections ?? []).isEmpty ? gist(structured.shortSummary) : nil,
            otherSummaries: Array(apps.dropFirst()),
            keyPoints: (structured.insights ?? []).map(\.text).filter { !$0.isEmpty },
            // Indexes stay the backend's (`PATCH …/events` addresses events by position).
            events: events,
            hasAudio: !(dto.audioFiles ?? []).isEmpty || dto.conversationAudio != nil,
            summaryAppID: apps.first?.appID,
            summaryIsOmiOwn: apps.isEmpty,
            calendarEvent: dto.calendarEvent.flatMap(calendarEvent),
            photos: photos(dto.photos ?? []),
            recordings: recordings(dto, conversation: conversation),
            audioParts: audioParts(dto.audioFiles ?? []),
            participantSpeakerIDs: dto.speakerResolution.flatMap { $0.status == "unavailable" ? nil : $0.participantSpeakerIds ?? [] }
        )
        detail.actionItemSources = actionItemSources(structured.actionItems ?? [])
        detail.chapters = chapters(structured.sections ?? [])
        detail.speakersUnresolved = dto.speakerResolution?.status == "unavailable"
        return detail
    }

    static func transcript(_ segments: [OmiAPI.TranscriptSegment]) -> [ConversationDetail.Line] {
        segments.enumerated().map { index, segment in
            ConversationDetail.Line(
                id: index,
                speaker: segment.isUser ? "You" : speakerName(segment),
                isUser: segment.isUser,
                text: segment.text,
                start: segment.start,
                segmentID: segment.id,
                speakerID: segment.speakerId,
                personID: segment.personId,
                end: segment.end,
                translations: (segment.translations ?? []).map(\.text).filter {
                    !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0 != segment.text
                }
            )
        }
    }

    /// The stored audio pieces, oldest first.
    static func audioParts(_ files: [OmiAPI.AudioFile]) -> [AudioPart] {
        files
            .map { AudioPart(id: $0.id, status: .unavailable, url: nil, duration: $0.duration, startedAt: BackendDate.parse($0.startedAt)) }
            .sorted { ($0.startedAt ?? .distantFuture) < ($1.startedAt ?? .distantFuture) }
    }

    /// The notes' sections that cite transcript segments: the transcript's chapters.
    static func chapters(_ sections: [OmiAPI.Section]) -> [ConversationDetail.Chapter] {
        sections.compactMap { section in
            let heading = section.heading.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !heading.isEmpty, let ids = section.sourceSegmentIds, !ids.isEmpty else { return nil }
            return ConversationDetail.Chapter(heading: heading, segmentIDs: ids)
        }
    }

    /// Each extracted action item's context and cited segments, keyed by its description.
    static func actionItemSources(_ items: [OmiAPI.ActionItem]) -> [String: ConversationDetail.ActionItemSource] {
        var sources: [String: ConversationDetail.ActionItemSource] = [:]
        for item in items where !item.description_.isEmpty {
            let source = ConversationDetail.ActionItemSource(context: item.context ?? "", segmentIDs: item.sourceSegmentIds ?? [])
            if source.context.isEmpty, source.segmentIDs.isEmpty { continue }
            sources[ConversationDigest.normalized(item.description_)] = source
        }
        return sources
    }

    /// Inline bytes when the photo carries them; stored ones are fetched by id.
    static func photos(_ photos: [OmiAPI.ConversationPhoto]) -> [ConversationPhoto] {
        photos.enumerated().map { index, photo in
            ConversationPhoto(
                id: photo.id ?? "photo-\(index)",
                data: photo.base64.isEmpty ? nil : Data(base64Encoded: photo.base64, options: .ignoreUnknownCharacters),
                description: photo.description_.flatMap { $0.isEmpty ? nil : $0 },
                isDiscarded: photo.discarded ?? false,
                isStored: photo.storageId != nil
            )
        }
    }

    static func calendarEvent(_ dto: OmiAPI.CalendarEventLink) -> CalendarEventLink? {
        guard let start = BackendDate.parse(dto.startTime), let end = BackendDate.parse(dto.endTime) else { return nil }
        return CalendarEventLink(
            eventID: dto.eventId, title: dto.title, attendees: dto.attendees ?? [], attendeeEmails: dto.attendeeEmails ?? [],
            start: start, end: end, htmlLink: dto.htmlLink.flatMap(URL.init(string:))
        )
    }

    static func recordings(_ dto: OmiAPI.Conversation, conversation: Conversation) -> [CaptureRecording] {
        let members = (dto.captureGroup?.members ?? []).map {
            CaptureRecording(
                id: $0.id, source: $0.source, start: BackendDate.parse($0.startedAt), end: BackendDate.parse($0.finishedAt),
                isCurrent: false
            )
        }
        return CaptureRecording.list(
            members: members, current: conversation.id, source: dto.source?.rawValue,
            start: conversation.startedAt ?? conversation.createdAt, end: conversation.finishedAt
        )
    }

    static func gist(_ text: String?) -> String? {
        let gist = (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return gist.isEmpty ? nil : gist
    }

    /// The overview, else the sections as Markdown (`## heading` + body; heading-only sections dropped).
    static func summary(overview: String?, sections: [OmiAPI.Section]) -> String {
        let overview = (overview ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !overview.isEmpty { return overview }
        return sections.compactMap { section -> String? in
            let body = section.bodyMarkdown.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !body.isEmpty else { return nil }
            let heading = section.heading.trimmingCharacters(in: .whitespacesAndNewlines)
            return heading.isEmpty ? body : "## \(heading)\n\n\(body)"
        }
        .joined(separator: "\n\n")
    }

    static func speakerName(_ segment: OmiAPI.TranscriptSegment) -> String {
        if let id = segment.speakerId { return "Speaker \(id + 1)" }
        return segment.speaker ?? "Speaker"
    }
}
