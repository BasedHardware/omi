package com.friend.ios

import android.app.Application
import io.intercom.android.sdk.Intercom
import io.maido.intercom.IntercomFlutterPlugin

class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Intercom.initialize(this, BuildConfig.INTERCOM_ANDROID_API_KEY, BuildConfig.INTERCOM_APP_ID)
        IntercomFlutterPlugin.initSdk(this, appId = BuildConfig.INTERCOM_APP_ID, androidApiKey = BuildConfig.INTERCOM_ANDROID_API_KEY)
    }
}