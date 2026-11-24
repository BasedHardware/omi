package com.friend.ios.analytics

import com.friend.ios.PostHogFlagRequestBlocker
import com.friend.ios.OmiPostHogSetup
import com.friend.ios.BuildConfig
import com.posthog.PostHogInternal
import org.junit.Assert.assertFalse
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.Protocol
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test

class PostHogFlagRequestBlockerTest {
    @OptIn(PostHogInternal::class)
    @Test fun `first setup preserves Flutter attribution and disables flag preloads`() {
        val config = OmiPostHogSetup.configuration("test", "https://posthog.invalid", false, true, false)
        assertEquals("posthog-flutter", config.sdkName)
        assertEquals(BuildConfig.POSTHOG_FLUTTER_VERSION, config.sdkVersion)
        assertEquals(true, config.optOut)
        assertFalse(config.surveys)
        assertFalse(config.preloadFeatureFlags)
        assertFalse(config.sendFeatureFlagEvent)
        assertEquals(PostHogFlagRequestBlocker::class.java, config.httpClient!!.interceptors.single().javaClass)
    }

    @Test fun `flags stay local while capture replay and config reach transport`() {
        val sent = mutableListOf<String>()
        val client = OkHttpClient.Builder().addInterceptor(PostHogFlagRequestBlocker())
            .addInterceptor { chain ->
                sent.add(chain.request().url.encodedPath)
                Response.Builder().request(chain.request()).protocol(Protocol.HTTP_1_1)
                    .code(200).message("OK").body("{}".toResponseBody()).build()
            }.build()
        for (path in listOf("/flags/?v=2", "/decide/?v=3", "/batch/", "/s/", "/array/test/config")) {
            client.newCall(Request.Builder().url("https://posthog.invalid$path").build()).execute().use {
                assertEquals(200, it.code)
                if (path.startsWith("/flags") || path.startsWith("/decide")) {
                    assertEquals("{\"featureFlags\":{},\"featureFlagPayloads\":{},\"flags\":{}}", it.body!!.string())
                }
            }
        }
        assertEquals(listOf("/batch/", "/s/", "/array/test/config"), sent)
    }
}
