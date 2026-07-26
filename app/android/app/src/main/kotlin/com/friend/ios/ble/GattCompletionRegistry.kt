package com.friend.ios.ble

import java.util.concurrent.atomic.AtomicBoolean

/**
 * Identity of a callback-bearing characteristic operation.
 *
 * UUIDs are not sufficient: Android can deliver a callback from a retired
 * BluetoothGatt after a replacement session has started an operation against
 * the same characteristic. Session and characteristic instance IDs keep those
 * operations distinct; exact object identity is verified when taking an entry.
 */
internal data class GattCompletionKey(
    val address: String,
    val sessionId: Long,
    val serviceUuid: String,
    val characteristicUuid: String,
    val characteristicInstanceId: Int,
) {
    fun normalized(): GattCompletionKey =
        copy(
            address = address.uppercase(),
            serviceUuid = serviceUuid.lowercase(),
            characteristicUuid = characteristicUuid.lowercase(),
        )
}

/**
 * Thread-safe retained completion owner used directly by OmiBleManager.
 *
 * Completion callbacks are always invoked after releasing the registry lock.
 */
internal class GattCompletionRegistry<T> {
    private data class Entry<T>(
        val sessionToken: Any,
        val characteristicToken: Any,
        val completion: (Result<T>) -> Unit,
    )

    private val entries = mutableMapOf<GattCompletionKey, Entry<T>>()

    fun register(
        key: GattCompletionKey,
        sessionToken: Any,
        characteristicToken: Any,
        completion: (Result<T>) -> Unit,
    ): ((Result<T>) -> Unit)? =
        synchronized(entries) {
            entries.put(
                key.normalized(),
                Entry(sessionToken, characteristicToken, completion),
            )?.completion
        }

    fun takeMatching(
        key: GattCompletionKey,
        sessionToken: Any,
        characteristicToken: Any,
    ): ((Result<T>) -> Unit)? =
        synchronized(entries) {
            val normalized = key.normalized()
            val entry = entries[normalized] ?: return@synchronized null
            if (entry.sessionToken !== sessionToken || entry.characteristicToken !== characteristicToken) {
                return@synchronized null
            }
            entries.remove(normalized)?.completion
        }

    fun failSession(
        sessionId: Long,
        failure: () -> Throwable,
    ): Int {
        val completions =
            synchronized(entries) {
                val matching =
                    entries
                        .filterKeys { it.sessionId == sessionId }
                        .map { it.key to it.value.completion }
                matching.forEach { entries.remove(it.first) }
                matching.map { it.second }
            }

        completions.forEach { it(Result.failure(failure())) }
        return completions.size
    }

    internal fun pendingCount(): Int = synchronized(entries) { entries.size }
}

internal fun <T> onceGattCompletion(completion: (Result<T>) -> Unit): (Result<T>) -> Unit {
    val completed = AtomicBoolean(false)
    return { result ->
        if (completed.compareAndSet(false, true)) {
            completion(result)
        }
    }
}
