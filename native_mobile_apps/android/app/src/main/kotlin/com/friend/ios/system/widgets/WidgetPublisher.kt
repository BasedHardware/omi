package com.friend.ios.system.widgets

import android.content.Context
import android.util.Log
import androidx.glance.appwidget.updateAll
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `WidgetPublisher.swift`: writes the widgets' snapshots and updates only the widgets whose
 * snapshot changed, coalesced: a burst of changes (a task list loading) costs one update.
 */
class WidgetPublisher(private val context: Context, private val scope: CoroutineScope, private val store: WidgetStore = WidgetStore(context)) {
    private val pending = mutableSetOf<WidgetKind>()
    private var flush: Job? = null

    fun publish(device: DeviceSnapshot?) {
        if (store.write(device)) reload(WidgetKind.Battery)
    }

    fun publish(upNext: UpNextSnapshot?) {
        if (store.write(upNext)) reload(WidgetKind.UpNext)
    }

    fun publish(latest: LatestSnapshot?) {
        if (store.write(latest)) reload(WidgetKind.Latest)
    }

    /** Signed out: the widgets show nothing of the account. */
    fun clear() {
        store.clear().forEach(::reload)
    }

    private fun reload(kind: WidgetKind) {
        pending += kind
        if (flush != null) return
        flush = scope.launch {
            delay(COALESCING_MS)
            val kinds = pending.toList()
            pending.clear()
            flush = null
            for (kind in kinds) {
                runCatching {
                    when (kind) {
                        WidgetKind.Battery -> OmiBatteryWidget().updateAll(context)
                        WidgetKind.UpNext -> OmiUpNextWidget().updateAll(context)
                        WidgetKind.Latest -> OmiLatestWidget().updateAll(context)
                    }
                }.onFailure { Log.w("omi.widgets", "update failed: $it") }
            }
        }
    }

    companion object {
        const val COALESCING_MS = 2_000L
    }
}
