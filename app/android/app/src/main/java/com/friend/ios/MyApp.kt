package com.friend.ios

import android.app.Application
import io.maido.intercom.IntercomFlutterPlugin

class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (BuildConfig.INTERCOM_APP_ID.isNotEmpty() && BuildConfig.INTERCOM_ANDROID_API_KEY.isNotEmpty()) {
            IntercomFlutterPlugin.initSdk(this, appId = BuildConfig.INTERCOM_APP_ID, androidApiKey = BuildConfig.INTERCOM_ANDROID_API_KEY)
        }
    }
}