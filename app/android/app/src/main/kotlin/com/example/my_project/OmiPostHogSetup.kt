package com.friend.ios

import android.content.Context
import com.posthog.PostHogInternal
import com.posthog.android.PostHogAndroid
import com.posthog.android.PostHogAndroidConfig
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodChannel
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody

/** Only the SDK's billed flag paths are answered locally. Capture/replay/config pass through. */
class PostHogFlagRequestBlocker : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.url.encodedPath.trim('/') !in setOf("flags", "decide")) return chain.proceed(request)
        return Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK")
            .body("""{"featureFlags":{},"featureFlagPayloads":{},"flags":{}}"""
                .toResponseBody("application/json".toMediaType())).build()
    }
}

object OmiPostHogSetup {
    fun register(context: Context, messenger: BinaryMessenger) {
        MethodChannel(messenger, "com.omi/posthog_setup").setMethodCallHandler { call, result ->
            if (call.method != "setup") { result.notImplemented(); return@setMethodCallHandler }
            val token = call.argument<String>("projectToken")!!
            val host = call.argument<String>("host")!!
            val config = configuration(token, host,
                call.argument<Boolean>("captureApplicationLifecycleEvents") ?: false,
                call.argument<Boolean>("optOut") ?: false,
                call.argument<Boolean>("debug") ?: false)
            PostHogAndroid.setup(context.applicationContext, config)
            result.success(null)
        }
    }
    @OptIn(PostHogInternal::class)
    fun configuration(token: String, host: String, lifecycle: Boolean, optedOut: Boolean, debugging: Boolean): PostHogAndroidConfig =
        PostHogAndroidConfig(token, host).apply {
            captureApplicationLifecycleEvents = lifecycle
            captureScreenViews = false
            captureDeepLinks = false
            preloadFeatureFlags = false
            sendFeatureFlagEvent = false
            optOut = optedOut
            debug = debugging
            surveys = false
            sessionReplay = false
            sessionReplayConfig.captureLogcat = false
            sdkName = "posthog-flutter"
            sdkVersion = BuildConfig.POSTHOG_FLUTTER_VERSION
            httpClient = OkHttpClient.Builder().addInterceptor(PostHogFlagRequestBlocker()).build()
        }

}
