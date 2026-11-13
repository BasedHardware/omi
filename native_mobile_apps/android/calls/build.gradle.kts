// Phone calls (and-calls): mirrors omi-native's App/PhoneCalls. Twilio Voice places the call, a
// self-managed Telecom ConnectionService is the CallKit counterpart, and a custom Twilio audio
// device taps both sides for the live transcript. The audio device is the Flutter app's native
// Kotlin (MIT, `app/android/.../phonecalls/`), its MethodChannel layer replaced by Kotlin interfaces.
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
}

android {
    namespace = "com.friend.ios.phonecalls"
    compileSdk = 36
    defaultConfig {
        minSdk = 29
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    // PhoneCallEngine (the store's view of a call) and MicrophonePermission (:audio, via :service).
    implementation(project(":service"))
    implementation(libs.twilio.voice)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
}
