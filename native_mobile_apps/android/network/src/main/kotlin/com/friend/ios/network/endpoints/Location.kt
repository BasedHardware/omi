package com.friend.ios.network.endpoints

import com.friend.ios.core.models.GeolocationSnapshot
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method

/** Port of `APIClient+Location.swift`. */
interface LocationAPI {
    /** `PATCH v1/users/geolocation`: the user's last place (Flutter `updateUserGeolocation`). */
    suspend fun updateUserGeolocation(snapshot: GeolocationSnapshot)
}

internal class LocationEndpoints(private val http: HttpCore) : LocationAPI {
    override suspend fun updateUserGeolocation(snapshot: GeolocationSnapshot) {
        http.data(Method.PATCH, "v1/users/geolocation", body = Body.Json(snapshot.jsonObject.toString()))
    }
}
