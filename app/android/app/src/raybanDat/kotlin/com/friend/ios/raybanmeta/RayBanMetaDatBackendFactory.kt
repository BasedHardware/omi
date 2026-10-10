package com.friend.ios.raybanmeta

import android.content.Context

/** raybanDat flavor: camera/photo capture through the Meta Wearables toolkit. */
internal object RayBanMetaDatBackendFactory {
    fun create(context: Context, events: RayBanMetaEventSink): RayBanMetaDatBackend? =
        MwdatBackend(context.applicationContext, events)
}
