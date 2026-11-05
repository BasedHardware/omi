package com.friend.ios.service.stores

import android.content.SharedPreferences
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.ForYouItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.launch

/**
 * Port of `ForYouStore` (`AnnouncementsStore.swift`): Home "For you" (Flutter `home_for_you`):
 * short nudges from the proactivity feed with Helpful / Not helpful / Dismiss / Stop these.
 */
class ForYouStore(
    private val api: APIClientProtocol,
    /** "Stop these" producers; null keeps them in memory (tests). */
    private val defaults: SharedPreferences? = null,
    private val scope: CoroutineScope = MainScope(),
) {
    var items: List<ForYouItem> by mutableStateOf(emptyList())
        private set
    var lastError: String? by mutableStateOf(null)
        private set

    private val shown = mutableSetOf<String>()
    private var stoppedInMemory = setOf<String>()

    private var stopped: Set<String>
        get() = defaults?.getStringSet(stoppedKey, emptySet()) ?: stoppedInMemory
        set(value) {
            if (defaults != null) defaults.edit().putStringSet(stoppedKey, value).apply() else stoppedInMemory = value
        }

    /** Hidden when the feed is off, fails, or is empty. */
    suspend fun load() {
        val feed = try {
            api.forYouFeed()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            null
        }
        if (feed == null) {
            items = emptyList()
            return
        }
        val stopped = stopped
        items = feed.filter { it.producer !in stopped }
    }

    /** Once per card per launch. */
    fun markShown(item: ForYouItem) {
        if (!shown.add(item.id)) return
        scope.launch { runCatching { api.sendForYouFeedback(item.id, ForYouItem.Feedback.Shown) } }
    }

    suspend fun send(feedback: ForYouItem.Feedback, item: ForYouItem) {
        val index = items.indexOfFirst { it.id == item.id }
        if (index < 0) return
        val previous = items
        when (feedback) {
            ForYouItem.Feedback.Helpful, ForYouItem.Feedback.NotHelpful -> {
                if (items[index].feedback == feedback.rawValue) return
                items = items.toMutableList().apply { set(index, get(index).copy(feedback = feedback.rawValue)) }
            }
            ForYouItem.Feedback.Dismissed -> items = items.filter { it.id != item.id }
            ForYouItem.Feedback.StopThese -> {
                items = items.filter { it.producer != item.producer }
                stopped = stopped + item.producer
            }
            ForYouItem.Feedback.Shown, ForYouItem.Feedback.Opened -> Unit
        }
        lastError = null
        try {
            api.sendForYouFeedback(item.id, feedback)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            lastError = e.toString()
            // A thumb that did not reach the backend is shown as not given; hiding stays.
            if (feedback == ForYouItem.Feedback.Helpful || feedback == ForYouItem.Feedback.NotHelpful) items = previous
        }
    }

    companion object {
        const val stoppedKey = "omi.forYou.stoppedProducers"
    }
}
