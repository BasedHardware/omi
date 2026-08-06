package com.friend.ios.ble

internal data class NativeAudioSubscriptionTarget(
    val serviceUuid: String,
    val characteristicUuid: String,
)

internal data class NativeAudioSubscriptionTransition(
    val unsubscribe: NativeAudioSubscriptionTarget? = null,
    val subscribe: NativeAudioSubscriptionTarget? = null,
)

/**
 * Tracks only the audio CCCD enabled by the native background owner.
 *
 * Ownership is scoped to a concrete GATT object. A replacement GATT starts with
 * no CCCD state, so it must never inherit an "already subscribed" decision from
 * the retired session.
 */
internal class NativeAudioSubscriptionOwnership {
    private data class OwnedTarget(
        val sessionToken: Int,
        val target: NativeAudioSubscriptionTarget,
    )

    private val ownedTargets = mutableMapOf<String, OwnedTarget>()

    @Synchronized
    fun reconcile(
        address: String,
        sessionToken: Int,
        desired: NativeAudioSubscriptionTarget?,
    ): NativeAudioSubscriptionTransition {
        val key = address.uppercase()
        val owned = ownedTargets[key]

        if (owned?.sessionToken != sessionToken) {
            if (desired == null) {
                ownedTargets.remove(key)
                return NativeAudioSubscriptionTransition()
            }
            ownedTargets[key] = OwnedTarget(sessionToken, desired)
            return NativeAudioSubscriptionTransition(subscribe = desired)
        }

        if (owned.target == desired) return NativeAudioSubscriptionTransition()

        if (desired == null) {
            ownedTargets.remove(key)
            return NativeAudioSubscriptionTransition(unsubscribe = owned.target)
        }

        ownedTargets[key] = OwnedTarget(sessionToken, desired)
        return NativeAudioSubscriptionTransition(
            unsubscribe = owned.target,
            subscribe = desired,
        )
    }
}
