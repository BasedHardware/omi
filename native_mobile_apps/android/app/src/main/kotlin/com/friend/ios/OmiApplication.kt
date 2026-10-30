package com.friend.ios

import android.app.Application
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.auth.FirebaseAuth

class OmiApplication : Application() {
    lateinit var environment: AppEnvironment
        private set

    override fun onCreate() {
        super.onCreate()
        val configuration = AppEnvironment.configuration()
        if (configuration.isLocalDev) {
            // The local harness's Firebase project (iOS: GoogleService-Info-Local.plist). Release builds
            // read the real google-services.json instead.
            FirebaseApp.initializeApp(
                this,
                FirebaseOptions.Builder()
                    .setProjectId("demo-omi-local")
                    .setApplicationId("1:000000000000:android:0000000000000000")
                    .setApiKey("AIzaSyDEMOOMILOCALFAKEKEY00000000000000")
                    .setGcmSenderId("000000000000")
                    .build(),
            )
        } else {
            FirebaseApp.initializeApp(this)
        }
        configuration.authEmulator?.let { FirebaseAuth.getInstance().useEmulator(it.host, it.port) }
        environment = AppEnvironment(this, configuration)
    }
}
