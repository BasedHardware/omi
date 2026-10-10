package com.friend.ios.raybanmeta

import android.content.Context

/**
 * dev/prod flavors: the Meta Wearables toolkit is not part of this build, so
 * Ray-Ban Meta runs in the labeled audio-only (Bluetooth HFP) mode.
 */
internal object RayBanMetaDatBackendFactory {
    fun create(context: Context, events: RayBanMetaEventSink): RayBanMetaDatBackend? = null
}
