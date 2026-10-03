package com.friend.ios.ble

import java.util.concurrent.atomic.AtomicBoolean

/** Claim delivery before calling a consumer that can throw or reenter. */
internal class OnceCompletion<T>(private val deliver: (T) -> Unit) : (T) -> Unit {
    private val delivered = AtomicBoolean(false)
    override fun invoke(value: T) {
        if (delivered.compareAndSet(false, true)) deliver(value)
    }
}
