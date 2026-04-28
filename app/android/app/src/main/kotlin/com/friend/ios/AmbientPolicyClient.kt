package com.friend.ios

import okhttp3.OkHttpClient
import okhttp3.Request

class AmbientPolicyClient {
    private val client = OkHttpClient()

    fun fetchPolicy(policyUrl: String, bearerToken: String? = null): String {
        val builder = Request.Builder().url(policyUrl)
        if (!bearerToken.isNullOrBlank()) builder.header("Authorization", "Bearer $bearerToken")
        return client.newCall(builder.build()).execute().use { response ->
            if (!response.isSuccessful) throw IllegalStateException("Policy fetch failed: ${response.code}")
            response.body?.string() ?: ""
        }
    }
}
