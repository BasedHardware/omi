package com.friend.ios.ble

/**
 * Lazily owns a resource while allowing policy transitions to stop only an
 * already-created resource. A disabled policy must not construct a dormant
 * resource merely to stop it.
 */
internal class LazyResourceHandle<T>(private val factory: () -> T) {
    private val lock = Any()
    private var value: T? = null

    fun getOrCreate(): T = synchronized(lock) {
        value ?: factory().also { value = it }
    }

    fun stopIfInitialized(stop: (T) -> Unit): Boolean {
        val current = synchronized(lock) { value } ?: return false
        stop(current)
        return true
    }

    fun clear() {
        synchronized(lock) {
            value = null
        }
    }
}
