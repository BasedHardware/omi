package com.friend.ios.core.models

import java.time.Instant

// Port of `ConversationExtras.swift`.

/** The Google Calendar event a conversation is linked to (`conversation.calendar_event`). */
data class CalendarEventLink(
    val eventID: String,
    val title: String,
    /** Display names (the owner left out), and the addresses "Share with attendees" writes to. */
    val attendees: List<String>,
    val attendeeEmails: List<String>,
    val start: Instant,
    val end: Instant,
    /** Opens the event in Google Calendar. */
    val htmlLink: String?,
) {
    /** `mailto:` to every attendee with "Notes: <title>" as subject (Flutter `calendar_event_sheets`). */
    fun shareURL(subject: String): String? {
        if (attendeeEmails.isEmpty()) return null
        val encoded = java.net.URLEncoder.encode(subject, "UTF-8").replace("+", "%20")
        return "mailto:${attendeeEmails.joinToString(",")}?subject=$encoded"
    }
}

/** An event from the user's Google Calendar, offered when linking a conversation. */
data class CalendarEventCandidate(
    val id: String,
    val title: String,
    val start: Instant,
    val end: Instant,
    val attendees: List<String>,
) {
    companion object {
        /** The event Flutter marks "Suggested": the biggest overlap of at least five minutes or half the event. */
        fun suggested(events: List<CalendarEventCandidate>, start: Instant, end: Instant): CalendarEventCandidate? =
            events.mapNotNull { event ->
                val overlap = (minOf(event.end, end).toEpochMilli() - maxOf(event.start, start).toEpochMilli()) / 1000.0
                val length = (event.end.toEpochMilli() - event.start.toEpochMilli()) / 1000.0
                if (overlap > 0 && (overlap >= 300 || (length > 0 && overlap >= length / 2))) event to overlap else null
            }.maxByOrNull { it.second }?.first
    }
}

/** A photo taken during the conversation (Omi Glass, `conversation.photos`). */
data class ConversationPhoto(
    val id: String,
    /** Inline image bytes; when empty the image is fetched by `id` (`storage_id` photos). */
    val data: ByteArray?,
    val description: String?,
    val isDiscarded: Boolean,
    val isStored: Boolean,
) {
    /** Omi is still describing it. */
    val isDescribing: Boolean get() = !isDiscarded && description == null

    override fun equals(other: Any?): Boolean = other is ConversationPhoto && other.id == id && other.description == description &&
        other.isDiscarded == isDiscarded && other.isStored == isStored && (other.data?.contentEquals(data) ?: (data == null))

    override fun hashCode(): Int = id.hashCode()
}

/** A screenshot of what was on screen during a meeting (`v1/conversations/{id}/screenshots`). */
data class ConversationScreenshot(
    val id: String,
    val caption: String,
    val imageURL: String?,
    val thumbnailURL: String?,
    val capturedAt: Instant?,
)

/**
 * Another device's recording of the same moment (`conversation.capture_group`); each is a
 * conversation of its own.
 */
data class CaptureRecording(
    val id: String,
    /** `omi`, `phone`, `desktop`, `apple_watch` ... */
    val source: String?,
    val start: Instant?,
    val end: Instant?,
    val isCurrent: Boolean,
) {
    companion object {
        /**
         * The group as Flutter's `CaptureGroupPresentation.recordings`: unique members plus the
         * current conversation, by start (unknown last, then id); empty below two.
         */
        fun list(members: List<CaptureRecording>, current: String, source: String?, start: Instant?, end: Instant?): List<CaptureRecording> {
            val seen = HashSet<String>()
            val all = members.filter { seen.add(it.id) }.map { it.copy(isCurrent = it.id == current) }.toMutableList()
            if (current !in seen) all += CaptureRecording(current, source, start, end, isCurrent = true)
            if (all.size <= 1) return emptyList()
            return all.sortedWith { lhs, rhs ->
                val left = lhs.start
                val right = rhs.start
                when {
                    left != null && right != null && left != right -> left.compareTo(right)
                    left != null && right == null -> -1
                    left == null && right != null -> 1
                    else -> lhs.id.compareTo(rhs.id)
                }
            }
        }
    }
}

/** One stored piece of a conversation's audio (`audio_files`), and where it can be played. */
data class AudioPart(
    val id: String,
    val status: Status,
    /** Signed, playable without auth headers. */
    val url: String?,
    /** Seconds. */
    val duration: Double,
    val startedAt: Instant? = null,
    /** `audio/mpeg` or `audio/wav`. */
    val contentType: String? = null,
) {
    enum class Status(val rawValue: String) { Cached("cached"), Pending("pending"), Unavailable("unavailable") }

    val isWAV: Boolean
        get() = contentType == "audio/wav" || url?.substringBefore('?')?.substringAfterLast('.', "")?.lowercase() == "wav"
}

/**
 * Who took part: "You", the people named in the transcript, unnamed voices Omi could count, else
 * the calendar attendees (Flutter `conversation_detail_meta.dart`).
 */
data class Participants(
    val names: List<String>,
    /** People beyond `names` Omi heard but could not name. */
    val unnamed: Int,
    /** Omi could not count the unnamed voices ("+ others"). */
    val uncounted: Boolean,
) {
    val isEmpty: Boolean get() = names.isEmpty()

    /** Everyone after the first name. */
    val others: Int get() = names.size - 1 + unnamed
}

/** [you] is the word for the user; [personName] names a person id (null when unknown). */
fun ConversationDetail.participants(you: String, personName: (String) -> String?): Participants {
    val names = mutableListOf<String>()
    if (transcript.any { it.isUser }) names += you
    val unnamedSpeakers = HashSet<Int>()
    for (line in transcript) {
        if (line.isUser) continue
        val person = line.personID
        val name = person?.let(personName)
        if (person != null && name != null) {
            if (name !in names) names += name
        } else {
            line.speakerID?.let { unnamedSpeakers += it }
        }
    }
    var unnamed = 0
    var uncounted = false
    val countable = participantSpeakerIDs
    if (countable != null) {
        unnamed = countable.toSet().intersect(unnamedSpeakers).size
    } else if (unnamedSpeakers.isNotEmpty()) {
        uncounted = true
    }
    val event = calendarEvent
    if ((names.isEmpty() || names == listOf(you)) && event != null && event.attendees.isNotEmpty()) {
        return Participants(names + event.attendees.map(::attendeeName), unnamed = 0, uncounted = false)
    }
    return Participants(names, unnamed, uncounted && names.isNotEmpty())
}

/** An email becomes its capitalised local part, a name its first word. */
fun attendeeName(value: String): String {
    val at = value.indexOf('@')
    if (at >= 0) {
        val local = value.substring(0, at)
        return local.take(1).uppercase() + local.drop(1)
    }
    return value.split(" ").firstOrNull { it.isNotEmpty() } ?: value
}

/**
 * Why a summary did not help, or what was wrong with the recording (`mobile_feedback.v1` reasons
 * for `summary_helpfulness` and `recording_quality`).
 */
enum class SummaryFeedbackReason(val rawValue: String) {
    Inaccurate("summary_inaccurate"),
    Incomplete("summary_incomplete"),
    Irrelevant("summary_irrelevant"),
    WrongContext("summary_wrong_context"),
    Other("summary_other"),
    MissingAudio("recording_missing_audio"),
    PoorTranscription("recording_poor_transcription"),
    WrongSpeaker("recording_wrong_speaker"),
    DelayedOrStuck("recording_delayed_or_stuck"),
    FragmentedOrDuplicated("recording_fragmented_or_duplicated"),
    RecordingOther("recording_other");

    companion object {
        /** The reasons one kind of prompt offers. */
        fun reasons(kind: ConversationFeedbackKind): List<SummaryFeedbackReason> = when (kind) {
            ConversationFeedbackKind.Summary -> listOf(Inaccurate, Incomplete, Irrelevant, WrongContext, Other)
            ConversationFeedbackKind.Recording -> listOf(MissingAudio, PoorTranscription, WrongSpeaker, DelayedOrStuck, FragmentedOrDuplicated, RecordingOther)
        }
    }
}

/**
 * What "Was this helpful?" asks about (`mobile_feedback.v1` `kind`): the summary, or how the
 * recording and its transcript came out.
 */
enum class ConversationFeedbackKind(val rawValue: String) {
    Summary("summary_helpfulness"),
    Recording("recording_quality"),
}

/** A summary template the user writes: a name and the prompt the app runs on each conversation. */
data class SummaryTemplateDraft(val name: String, val prompt: String, val isPublic: Boolean = false) {
    enum class Problem { NameMissing, NameTooShort, PromptMissing, PromptTooShort }

    /** Flutter's form rules: a name of three characters, a prompt of ten. */
    val problem: Problem?
        get() {
            val name = name.trim()
            val prompt = prompt.trim()
            return when {
                name.isEmpty() -> Problem.NameMissing
                name.codePointCount(0, name.length) < 3 -> Problem.NameTooShort
                prompt.isEmpty() -> Problem.PromptMissing
                prompt.codePointCount(0, prompt.length) < 10 -> Problem.PromptTooShort
                else -> null
            }
        }
}

/** Which conversations the list asks the backend for (`GET v1/conversations`). */
data class ConversationQuery(
    val filter: ConversationFilter = ConversationFilter.All,
    val includeDiscarded: Boolean = false,
    /** Inclusive bounds (the one-day page). */
    val start: Instant? = null,
    val end: Instant? = null,
)

/**
 * What the conversation list hides on the device (Flutter "Conversation display"): discarded
 * conversations unless shown, and short ones under a threshold.
 */
data class ConversationDisplay(
    val showsDiscarded: Boolean = false,
    val showsShort: Boolean = false,
    /** Seconds; 0 hides nothing. */
    val shortThreshold: Int = 0,
) {
    /** The list keeps this conversation. */
    fun keeps(conversation: Conversation): Boolean {
        if (conversation.isDiscarded && !showsDiscarded) return false
        val duration = conversation.duration
        if (!showsShort && shortThreshold > 0 && duration != null && duration < shortThreshold) return false
        return true
    }

    /** The threshold the list hides below, null when every length shows. */
    val hidesShorterThan: Int? get() = if (!showsShort && shortThreshold > 0) shortThreshold else null

    companion object {
        /**
         * One row per capture group (Flutter `CaptureGroupPresentation`): the group's primary
         * recording when it is loaded, else the first one; the others open from its page.
         */
        fun oneRowPerCaptureGroup(list: List<Conversation>): List<Conversation> {
            val shown = HashMap<String, String>()
            for (conversation in list) {
                val group = conversation.captureGroupID ?: continue
                if (shown[group] == null || conversation.id == conversation.captureGroupPrimaryID) shown[group] = conversation.id
            }
            return list.filter { conversation -> conversation.captureGroupID?.let { shown[it] == conversation.id } ?: true }
        }
    }
}
