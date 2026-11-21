package com.friend.ios.core.models

/** Port of `Announcement` (`APIClient+Discover.swift`): what's new after an update. */
data class Announcement(val id: String, val title: String, val kind: Kind) {
    sealed interface Kind {
        /** One version's changes. */
        data class Changelog(val version: String?, val changes: List<Change>) : Kind
        /** A feature walkthrough, one page per step. */
        data class Feature(val steps: List<Change>) : Kind
        /** A message with an optional button (`navigate:/route` or `url:https://...`). */
        data class Message(val body: String, val imageURL: String?, val buttonTitle: String?, val buttonURL: String?) : Kind
    }

    data class Change(val emoji: String?, val title: String, val text: String, val imageURL: String? = null) {
        val id: String get() = title + text
    }
}
