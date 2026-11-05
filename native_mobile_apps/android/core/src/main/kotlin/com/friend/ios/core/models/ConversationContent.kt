package com.friend.ios.core.models

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * A calendar meeting Omi did not capture (`GET v1/calendar/capture-gaps`): accepted, timed, and
 * no kept conversation overlaps it.
 */
data class CaptureGap(
    val id: String,
    val title: String,
    val start: Instant,
    val end: Instant,
) {
    companion object {
        /** The gaps by local day (start of day), each day's in time order. */
        fun byDay(gaps: List<CaptureGap>, zone: ZoneId = ZoneId.systemDefault()): Map<LocalDate, List<CaptureGap>> =
            gaps.groupBy { it.start.atZone(zone).toLocalDate() }
                .toSortedMap()
                .mapValues { (_, day) -> day.sortedBy { it.start } }
    }
}

/** A folder as the editor fills it in: name, emoji, color (`#RRGGBB`), description. */
data class FolderDraft(
    val name: String = "",
    val icon: String = "📁",
    val color: String = colors[0],
    val description: String = "",
) {
    /** The name and description without surrounding spaces; null when the name is empty. */
    val trimmed: FolderDraft?
        get() {
            val name = name.trim()
            if (name.isEmpty()) return null
            return FolderDraft(name = name, icon = icon, color = color, description = description.trim())
        }

    companion object {
        /** The Flutter app's folder colors (`folderColors`), in its order. */
        val colors = listOf(
            "#3B82F6", "#EF4444", "#10B981", "#8B5CF6", "#F59E0B", "#06B6D4", "#EC4899", "#6366F1", "#F97316", "#6B7280",
        )

        /** The Flutter app's folder emoji (`folderIconStrings`), in its order. */
        val icons = listOf(
            "📁", "💼", "🏠", "📚", "👨‍👩‍👧‍👦", "❤️", "🎮", "✈️", "🏥", "🛒", "💰", "🎵", "🎨", "📝", "💬", "🌎", "🛠️", "🍔", "🏆", "🔒",
        )
    }
}
