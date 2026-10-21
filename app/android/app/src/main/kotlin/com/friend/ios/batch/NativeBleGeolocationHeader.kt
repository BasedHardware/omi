package com.friend.ios.batch

import okhttp3.Request
import org.json.JSONObject

internal const val CONVERSATION_GEOLOCATION_HEADER = "X-Omi-Conversation-Geolocation"
internal const val CONVERSATION_GEOLOCATION_HEADER_MAX_BYTES = 4096

internal fun addConversationGeolocationHeader(builder: Request.Builder, rawGeolocation: String?): Request.Builder {
    if (rawGeolocation.isNullOrBlank() ||
        rawGeolocation.toByteArray(Charsets.UTF_8).size > CONVERSATION_GEOLOCATION_HEADER_MAX_BYTES
    ) {
        return builder
    }
    return try {
        JSONObject(rawGeolocation)
        builder.header(CONVERSATION_GEOLOCATION_HEADER, rawGeolocation)
    } catch (_: Exception) {
        builder
    }
}
