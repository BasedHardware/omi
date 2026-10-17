package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Conversation
import com.friend.ios.core.models.ConversationDisplay
import com.friend.ios.core.models.ConversationQuery
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.CancellationException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * Port of `DayConversationsStore` (`ConversationsStore+Display.swift`): one day's conversations,
 * paged, with the previous and next day (never past today).
 */
class DayConversationsStore internal constructor(
    private val api: APIClientProtocol,
    day: LocalDate,
    private val zone: ZoneId,
    private val display: ConversationDisplay,
) {
    enum class Phase { Loading, Loaded, Failed }

    var day: LocalDate by mutableStateOf(day)
        private set
    var phase: Phase by mutableStateOf(Phase.Loading)
        private set
    private var loaded: List<Conversation> by mutableStateOf(emptyList())
    var hasMore by mutableStateOf(false)
        private set
    var isLoadingMore by mutableStateOf(false)
        private set
    private val pageSize = 50

    /** Newest first; short ones hidden as on Home (discarded ones never come on this page). */
    val conversations: List<Conversation>
        get() = ConversationDisplay.oneRowPerCaptureGroup(loaded.filter(display::keeps)).sortedByDescending { it.date }

    fun canGoForward(now: Instant = Instant.now()): Boolean = day < now.atZone(zone).toLocalDate()

    suspend fun load() {
        if (loaded.isEmpty()) phase = Phase.Loading
        try {
            val page = fetch(0)
            loaded = page
            hasMore = page.size == pageSize
            phase = Phase.Loaded
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            phase = Phase.Failed
        }
    }

    suspend fun loadMore() {
        if (!hasMore || isLoadingMore || phase != Phase.Loaded) return
        isLoadingMore = true
        try {
            val page = try {
                fetch(loaded.size)
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                return
            }
            val known = loaded.map { it.id }.toSet()
            loaded = loaded + page.filter { it.id !in known }
            hasMore = page.size == pageSize
        } finally {
            isLoadingMore = false
        }
    }

    /** Moves by [days] (negative for earlier), then loads it. */
    suspend fun go(days: Long, now: Instant = Instant.now()) = show(day.plusDays(days), now)

    suspend fun show(day: LocalDate, now: Instant = Instant.now()) {
        val today = now.atZone(zone).toLocalDate()
        val target = if (day > today) today else day
        if (target == this.day) return
        this.day = target
        loaded = emptyList()
        hasMore = false
        load()
    }

    private suspend fun fetch(offset: Int): List<Conversation> {
        val start = day.atStartOfDay(zone).toInstant()
        val end = day.plusDays(1).atStartOfDay(zone).toInstant().minusSeconds(1)
        return api.conversations(pageSize, offset, ConversationQuery(start = start, end = end))
    }
}
