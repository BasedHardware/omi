package com.friend.ios.ble

import java.util.ArrayDeque

/**
 * Identity of one asynchronous Android GATT operation.
 *
 * Android permits only one outstanding GATT operation per client. Matching the
 * callback to this identity prevents a late callback from releasing an
 * unrelated command.
 */
internal data class GattOperationKey(
    val address: String,
    val kind: GattOperationKind,
    val target: String = "",
) {
    fun normalized(): GattOperationKey = copy(
        address = address.uppercase(),
        target = target.lowercase(),
    )
}

internal enum class GattOperationKind {
    DISCOVER_SERVICES,
    REQUEST_MTU,
    READ_CHARACTERISTIC,
    WRITE_CHARACTERISTIC,
    WRITE_WITHOUT_RESPONSE,
    WRITE_DESCRIPTOR,
    READ_RSSI,
}

internal enum class GattOperationFailure {
    REJECTED,
    TIMED_OUT,
    CANCELLED,
    EXCEPTION,
}

internal enum class GattWriteMode {
    WITH_RESPONSE,
    WITHOUT_RESPONSE,
}

internal fun preferredGattWriteMode(
    supportsWrite: Boolean,
    supportsWriteWithoutResponse: Boolean,
): GattWriteMode? =
    when {
        supportsWrite -> GattWriteMode.WITH_RESPONSE
        supportsWriteWithoutResponse -> GattWriteMode.WITHOUT_RESPONSE
        else -> null
    }

/**
 * Small, platform-independent state machine for Android's one-operation GATT
 * contract. Production supplies Handler-backed dispatch/scheduling; JVM tests
 * use deterministic fakes.
 */
internal class GattOperationQueue(
    private val dispatch: (() -> Unit) -> Unit,
    private val schedule: (delayMillis: Long, task: () -> Unit) -> (() -> Unit),
    private val timeoutMillis: Long,
) {
    private data class Entry(
        val key: GattOperationKey,
        val start: () -> Boolean,
        val onFailure: (GattOperationFailure) -> Unit,
        var cancelTimeout: (() -> Unit)? = null,
    )

    private val queued = ArrayDeque<Entry>()
    private var current: Entry? = null
    private var callbackDepth = 0

    fun enqueue(
        key: GattOperationKey,
        start: () -> Boolean,
        onFailure: (GattOperationFailure) -> Unit = {},
    ) {
        synchronized(this) {
            queued.addLast(Entry(key.normalized(), start, onFailure))
        }
        processNext()
    }

    fun contains(key: GattOperationKey): Boolean {
        val normalized = key.normalized()
        return synchronized(this) {
            current?.key == normalized || queued.any { it.key == normalized }
        }
    }

    fun isActive(key: GattOperationKey): Boolean {
        val normalized = key.normalized()
        return synchronized(this) {
            current?.key == normalized
        }
    }

    /**
     * Completes only the currently active matching operation. [onSuccess] runs
     * before the next command can start, so per-operation callback state can be
     * safely removed without a same-characteristic successor overwriting it.
     */
    fun complete(key: GattOperationKey, onSuccess: () -> Unit = {}): Boolean {
        val normalized = key.normalized()
        val entry = synchronized(this) {
            current?.takeIf { it.key == normalized }?.also {
                current = null
                callbackDepth++
            }
        } ?: return false

        entry.cancelTimeout?.invoke()
        try {
            onSuccess()
        } finally {
            synchronized(this) {
                callbackDepth--
            }
            processNext()
        }
        return true
    }

    fun cancelAddress(address: String) {
        val normalizedAddress = address.uppercase()
        val cancelled = mutableListOf<Entry>()

        synchronized(this) {
            current?.takeIf { it.key.address == normalizedAddress }?.let {
                current = null
                cancelled.add(it)
            }

            val iterator = queued.iterator()
            while (iterator.hasNext()) {
                val entry = iterator.next()
                if (entry.key.address == normalizedAddress) {
                    iterator.remove()
                    cancelled.add(entry)
                }
            }
            if (cancelled.isNotEmpty()) callbackDepth++
        }

        try {
            for (entry in cancelled) {
                entry.cancelTimeout?.invoke()
                try {
                    entry.onFailure(GattOperationFailure.CANCELLED)
                } catch (_: Exception) {
                    // One caller must not prevent the remaining operations
                    // from learning that their peripheral disconnected.
                }
            }
        } finally {
            if (cancelled.isNotEmpty()) {
                synchronized(this) {
                    callbackDepth--
                }
            }
            processNext()
        }
    }

    internal fun pendingCount(): Int = synchronized(this) {
        queued.size + if (current == null) 0 else 1
    }

    private fun processNext() {
        val entry = synchronized(this) {
            if (current != null || callbackDepth > 0 || queued.isEmpty()) return
            queued.removeFirst().also { current = it }
        }

        dispatch {
            if (!isCurrent(entry)) return@dispatch

            val cancelTimeout = schedule(timeoutMillis) {
                fail(entry, GattOperationFailure.TIMED_OUT)
            }
            val accepted = synchronized(this) {
                if (current === entry) {
                    entry.cancelTimeout = cancelTimeout
                    true
                } else {
                    false
                }
            }
            if (!accepted) {
                cancelTimeout()
                return@dispatch
            }

            val started = try {
                entry.start()
            } catch (_: Exception) {
                fail(entry, GattOperationFailure.EXCEPTION)
                return@dispatch
            }
            if (!started) {
                fail(entry, GattOperationFailure.REJECTED)
            }
        }
    }

    private fun isCurrent(entry: Entry): Boolean = synchronized(this) {
        current === entry
    }

    private fun fail(entry: Entry, reason: GattOperationFailure) {
        val removed = synchronized(this) {
            if (current !== entry) {
                false
            } else {
                current = null
                callbackDepth++
                true
            }
        }
        if (!removed) return

        entry.cancelTimeout?.invoke()
        try {
            entry.onFailure(reason)
        } finally {
            synchronized(this) {
                callbackDepth--
            }
            processNext()
        }
    }
}
