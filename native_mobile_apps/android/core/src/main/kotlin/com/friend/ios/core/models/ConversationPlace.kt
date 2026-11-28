package com.friend.ios.core.models

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Port of `ConversationPlace.swift`: where a conversation happened (backend
 * `models/geolocation.py`, the conversation's `geolocation`), and conversations grouped by place.
 * `GeolocationSnapshot` (sent with a recording) belongs to the capture port.
 */
data class ConversationLocation(
    val latitude: Double,
    val longitude: Double,
    /** Reverse-geocoded by the backend; null when geocoding failed or has not run yet. */
    val address: String? = null,
    val googlePlaceID: String? = null,
) {
    /** Finite and inside the backend's bounds (malformed points are dropped, as Flutter does). */
    val isValid: Boolean
        get() = latitude.isFinite() && longitude.isFinite() && latitude in -90.0..90.0 && longitude in -180.0..180.0

    /**
     * Area and city instead of the full street address (Flutter `GetGeolocationWidgets._getShortAddress`):
     * with three or more comma parts the third- and second-to-last, else the address as is.
     */
    val shortAddress: String?
        get() {
            val address = address?.trim()?.takeIf { it.isNotEmpty() } ?: return null
            val parts = address.split(",").map { it.trim() }
            if (parts.size >= 3) return "${parts[parts.size - 3]}, ${parts[parts.size - 2]}"
            if (parts.size == 2) return "${parts[0]}, ${parts[1]}"
            return address
        }

    /** Great-circle distance in metres. */
    fun distance(other: ConversationLocation): Double {
        val radius = 6_371_008.8
        val lat1 = latitude * Math.PI / 180
        val lat2 = other.latitude * Math.PI / 180
        val dLat = lat2 - lat1
        val dLon = (other.longitude - longitude) * Math.PI / 180
        val h = sin(dLat / 2) * sin(dLat / 2) + cos(lat1) * cos(lat2) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * radius * asin(min(1.0, sqrt(h)))
    }
}

/**
 * Conversations recorded at one place: points within 100 m of every other member
 * (Flutter `buildConversationMapGroups`).
 */
data class ConversationPlace(val location: ConversationLocation, val conversations: List<Conversation>) {
    /** Stable whatever order the conversations arrived in. */
    val id: String get() = conversations.map { it.id }.sorted().joinToString(",")

    companion object {
        const val clusterDistance = 100.0

        /**
         * Sorted by id before grouping so membership does not depend on paging order; each place is
         * anchored at its first member. Conversations without a valid location are left out.
         */
        fun group(conversations: List<Conversation>): List<ConversationPlace> {
            val located = conversations
                .mapNotNull { conversation -> conversation.location?.takeIf { it.isValid }?.let { conversation to it } }
                .sortedBy { it.first.id }
            val groups = mutableListOf<Pair<MutableList<ConversationLocation>, MutableList<Conversation>>>()
            for ((conversation, point) in located) {
                val group = groups.firstOrNull { group -> group.first.all { it.distance(point) <= clusterDistance } }
                if (group != null) {
                    group.first += point
                    group.second += conversation
                } else {
                    groups += mutableListOf(point) to mutableListOf(conversation)
                }
            }
            // The first point anchors the place.
            return groups.map { ConversationPlace(it.first[0], it.second) }
        }
    }
}
