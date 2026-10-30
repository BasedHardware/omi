package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.HealthSummary
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import java.time.Instant

/**
 * Port of `APIClient+Health.swift`. Apple Health on iOS, Health Connect here: the backend keeps the
 * Flutter key `apple_health` for both (`routers/integrations.py`; Flutter `integrations.dart`).
 * Connected state is `GET v1/integrations/apple_health`; disconnect is `DELETE v1/integrations/apple_health`.
 */
interface HealthAPI {
    /**
     * `PUT v1/integrations/apple-health/sync`: the summary the chat answers health questions from.
     * Returns the server's `synced_at`.
     */
    suspend fun syncAppleHealth(summary: HealthSummary): Instant?

    /**
     * `PUT v1/integrations/apple_health` with `{}` (`connected` defaults to true): Flutter's
     * `saveConnection` after the first sync.
     */
    suspend fun markAppleHealthConnected()
}

internal class HealthEndpoints(private val http: HttpCore) : HealthAPI {
    override suspend fun syncAppleHealth(summary: HealthSummary): Instant? {
        val response = http.jsonObject(Method.PUT, "v1/integrations/apple-health/sync", json = summary.syncBody)
        if (response.string("status") != "ok") throw APIError.Decoding("apple health sync status")
        return BackendDate.parse(response.string("synced_at"))
    }

    override suspend fun markAppleHealthConnected() {
        http.data(Method.PUT, "v1/integrations/apple_health", body = Body.Json("{}"))
    }
}
