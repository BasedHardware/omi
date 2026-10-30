package com.friend.ios.network.endpoints

import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Port of `APIClient+Notifications.swift`. */
interface NotificationsAPI {
    /**
     * `POST v1/users/fcm-token` (Flutter's `saveFcmTokenServer`). The backend files the token under
     * `<X-App-Platform>_<X-Device-Id-Hash>`, so sending Flutter's hash replaces that install's token.
     */
    suspend fun saveNotificationToken(token: String, timeZone: String, deviceIDHash: String?)
}

internal class NotificationsEndpoints(private val http: HttpCore) : NotificationsAPI {
    override suspend fun saveNotificationToken(token: String, timeZone: String, deviceIDHash: String?) {
        val body = buildJsonObject {
            put("fcm_token", token)
            put("time_zone", timeZone)
        }
        val headers = deviceIDHash?.let { mapOf("X-Device-Id-Hash" to it) }.orEmpty()
        http.data(Method.POST, "v1/users/fcm-token", body = Body.Json(body.toString()), headers = headers)
    }
}
