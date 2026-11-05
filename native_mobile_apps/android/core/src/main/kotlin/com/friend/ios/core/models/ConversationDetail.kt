package com.friend.ios.core.models

import java.time.Instant

/** Port of `ConversationDetail.swift`: everything the conversation detail renders. */
data class ConversationDetail(
    val conversation: Conversation,
    /** Action items extracted into the summary (the canonical tasks come from TasksStore). */
    val summaryActionItems: List<String>,
    val transcript: List<Line>,
    /**
     * The summary as Markdown: the first app's result, else the overview, else the structured
     * sections (the Flutter app's `ConversationSummarySelection`).
     */
    val summary: String = conversation.overview,
    /** The gist in two or three sentences (`structured.short_summary`), when the backend kept it. */
    val gist: String? = null,
    /** App results after the one shown as the summary. */
    val otherSummaries: List<AppSummary> = emptyList(),
    /** Key points (`structured.insights`). */
    val keyPoints: List<String> = emptyList(),
    val events: List<Event> = emptyList(),
    /** Audio was stored for this conversation (`audio_files`). */
    val hasAudio: Boolean = false,
    /** The app whose result is shown as the summary (null: Omi's own summary). */
    val summaryAppID: String? = null,
    /** The summary shown is Omi's own (no app result), the one an edit rewrites in place. */
    val summaryIsOmiOwn: Boolean = true,
    val calendarEvent: CalendarEventLink? = null,
    val photos: List<ConversationPhoto> = emptyList(),
    /** Other devices' recordings of the same moment, this one included (empty below two). */
    val recordings: List<CaptureRecording> = emptyList(),
    /** The stored audio pieces, oldest first (start times for playing several in order). */
    val audioParts: List<AudioPart> = emptyList(),
    /** Speakers Omi could count (`speaker_resolution` resolved or capture); null when it could not. */
    val participantSpeakerIDs: List<Int>? = null,
    /**
     * What each extracted action item was based on, keyed by its normalized description
     * (`ConversationDigest.normalized`): the cited transcript segments and the one-line context.
     */
    val actionItemSources: Map<String, ActionItemSource> = emptyMap(),
    /**
     * The notes' sections with the transcript segments each cites (`structured.sections`), in
     * order: the transcript's chapters.
     */
    val chapters: List<Chapter> = emptyList(),
) {
    data class Line(
        val id: Int,
        val speaker: String,
        val isUser: Boolean,
        val text: String,
        /** Seconds. */
        val start: Double,
        /** The backend segment id (editing, speaker labeling), speaker number and named person. */
        val segmentID: String? = null,
        val speakerID: Int? = null,
        val personID: String? = null,
    ) {
        /** The same line, said by the user or by a person (null for nobody named). */
        fun relabeled(isUser: Boolean, personID: String?): Line = copy(isUser = isUser, personID = if (isUser) null else personID)
    }

    /** A summary another app (a summary template) wrote for this conversation. */
    data class AppSummary(val appID: String?, val content: String)

    /** A calendar event Omi found in the conversation. */
    data class Event(
        val title: String,
        val description: String,
        val start: Instant?,
        /** Minutes. */
        val duration: Int,
        /** Already added to a calendar (`created`). */
        val isCreated: Boolean = false,
    )

    data class Chapter(val heading: String, val segmentIDs: List<String>)

    data class ActionItemSource(val context: String, val segmentIDs: List<String>)

    /** The transcript as plain text, one "Speaker: words" line each (copy and share). */
    val transcriptText: String get() = transcript.joinToString("\n") { "${it.speaker}: ${it.text}" }

    /** Lines containing [matching] (case and diacritics ignored), in order. */
    fun lines(matching: String): List<Int> {
        val query = fold(matching.trim())
        if (query.isEmpty()) return emptyList()
        return transcript.filter { fold(it.text).contains(query) }.map { it.id }
    }

    companion object {
        /** Case and diacritics folded (`.caseInsensitive, .diacriticInsensitive`). */
        fun fold(text: String): String =
            java.text.Normalizer.normalize(text, java.text.Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()
    }
}
